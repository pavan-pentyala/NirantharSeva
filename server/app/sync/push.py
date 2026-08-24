"""The push handler — encodes I1. See plan §5.3 and docs/decisions/ADR-002.md.

One transaction per op, not per batch, so a rejection does not roll back its
neighbours. The receipt is claimed before the work and finalised with the
work in the same transaction, so a crash anywhere leaves either nothing or
everything applied. A replay never re-executes — it returns the stored
answer, so the client sees an identical response the second time.

See docs/decisions/ADR-003.md for the conflict policy and
app/domain/states.py for the state machine apply_operation dispatches into.

Phase 2.2 (docs/decisions/ADR-006.md): who is acting comes from the
authenticated Actor, resolved server-side — never from op.payload. A
device cannot be trusted to name its own role, org, or user id.

Phase 4.3: the toy model (Phase 1's one-field scaffold, D1/D7) is dropped —
migration 0006, docs/PHASE4_PLAN.md's P4.3. `entity="referral"` is the only
entity this module has ever handled since; `actor` is no longer optional,
since every op now needs one.

Phase 6 (P6.2, ADR-009): `_resolve_patient`'s `patient_name` path now
calls app/linkage/pipeline.py's `resolve()` instead of a bare exact match.
A `review_queue` outcome still creates the referral and a provisional
patient in this same transaction — an ASHA's offline write never blocks on
a nurse's decision (docs/PHASE6_PLAN.md "Traps"). The identity-review
queue itself is decided over REST, not through this module (ADR-013).
"""

import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.scoping import SUBTREE_CTE, subtree_params
from app.clock import Clock
from app.config import get_settings
from app.db import acquire_seq_lock
from app.domain.actor import Actor
from app.domain.states import State, may
from app.instrumentation.logging import get_logger
from app.linkage.normalize import normalize
from app.linkage.pipeline import resolve
from app.schemas.sync import Op, OpResult, OpStatus
from app.sync.conflicts import decide
from app.sync.event_log import insert_referral_event, replay_referral
from app.sync.lamport import merge_lamport

_logger = get_logger(__name__)


@dataclass
class Outcome:
    status: OpStatus
    server_seq: int | None
    detail: dict[str, Any] | None


def _decode_detail(value: Any) -> dict[str, Any] | None:
    """The asyncpg jsonb codec used via raw text() queries round-trips as a
    string, not a dict — see the comment on the receipt UPDATE below."""
    if value is None:
        return None
    if isinstance(value, str):
        return json.loads(value)
    return value


async def handle_push(
    session_factory: async_sessionmaker[AsyncSession],
    device_id: str,
    ops: Sequence[Op],
    clock: Clock,
    run_id: str | None,
    actor: Actor,
) -> tuple[list[OpResult], int]:
    results: list[OpResult] = []

    for op in ops:  # one transaction PER OP, not per batch
        async with session_factory() as s, s.begin():
            # 1. Claim the op_id. Atomic; wins the race against a concurrent retry.
            claimed = await s.execute(
                text(
                    """INSERT INTO sync_receipt(op_id, received_at, result, detail)
                       VALUES (:id, :received_at, 'in_progress', NULL)
                       ON CONFLICT (op_id) DO NOTHING
                       RETURNING op_id"""
                ),
                {"id": op.op_id, "received_at": clock.now()},
            )
            if claimed.first() is None:
                # Replay. Return the stored result verbatim; apply nothing.
                prior = await s.execute(
                    text("SELECT result, detail, server_seq FROM sync_receipt WHERE op_id=:id"),
                    {"id": op.op_id},
                )
                r = prior.one()
                results.append(
                    OpResult(
                        op_id=op.op_id,
                        status=r.result,
                        server_seq=r.server_seq,
                        detail=_decode_detail(r.detail),
                    )
                )
                continue

            # 2. Serialise sequence assignment (ADR-002).
            await acquire_seq_lock(s)

            # 3. Validate + apply.
            outcome = await apply_operation(s, op, device_id, clock, run_id, actor)

            # 4. Record the real result — SAME transaction as the effect.
            # detail is JSONB; the asyncpg driver's jsonb codec encodes/decodes
            # strings, not Python dicts, when there is no Core column type to
            # do that conversion — text() queries have no such type info, so
            # this dumps/loads by hand at the raw-SQL boundary.
            await s.execute(
                text(
                    """UPDATE sync_receipt
                       SET result=:r, detail=CAST(:d AS jsonb), server_seq=:q WHERE op_id=:id"""
                ),
                {
                    "r": outcome.status,
                    "d": json.dumps(outcome.detail) if outcome.detail is not None else None,
                    "q": outcome.server_seq,
                    "id": op.op_id,
                },
            )
            results.append(
                OpResult(
                    op_id=op.op_id,
                    status=outcome.status,
                    server_seq=outcome.server_seq,
                    detail=outcome.detail,
                )
            )

    # Read after all per-op transactions above have committed, so this sees
    # every event this batch just wrote. Merged with the batch's own lamports
    # as a safety net (plan §5.4's client-side formula, mirrored server-side).
    async with session_factory() as s:
        max_row = await s.execute(text("SELECT COALESCE(MAX(lamport), 0) AS m FROM referral_event"))
        db_max = max_row.scalar_one()

    server_lamport = merge_lamport(db_max, [op.lamport for op in ops])
    return results, server_lamport


async def apply_operation(
    session: AsyncSession,
    op: Op,
    device_id: str,
    clock: Clock,
    run_id: str | None,
    actor: Actor,
) -> Outcome:
    if op.entity == "referral" and op.operation == "create_referral":
        return await _apply_create_referral(session, op, device_id, clock, run_id, actor)
    if op.entity == "referral" and op.operation == "transition":
        return await _apply_referral_transition(session, op, device_id, clock, run_id, actor)
    return Outcome(
        status="rejected",
        server_seq=None,
        detail={"reason": f"unsupported entity/operation: {op.entity}/{op.operation}"},
    )


async def _append_referral_event(
    session: AsyncSession,
    *,
    referral_id: uuid.UUID,
    from_state: str | None,
    to_state: str,
    actor: Actor,
    op: Op,
    device_id: str,
    server_time: Any,
    run_id: str | None,
) -> int:
    # actor_user_id and actor_role come from the caller's server-verified
    # identity, never from op.payload — a device cannot be trusted to name
    # its own role, org, or user (docs/decisions/ADR-006.md).
    return await insert_referral_event(
        session,
        referral_id=referral_id,
        from_state=from_state,
        to_state=to_state,
        actor_user_id=actor.user_id,
        actor_role=actor.role.value,
        device_time=op.device_time,
        server_time=server_time,
        lamport=op.lamport,
        op_id=op.op_id,
        device_id=device_id,
        payload=op.payload,
        run_id=run_id,
    )


def _warn_if_payload_claims_org_identity(op: Op, actor: Actor) -> None:
    """D6: origin_org_id/origin_user_id in the payload are ignored, not
    rejected — rejecting would turn a stale offline client into a
    data-loss path. Logged so a disagreement is visible without being
    fatal."""
    claimed_org = op.payload.get("origin_org_id")
    if claimed_org is not None and str(claimed_org) != str(actor.org_unit_id):
        _logger.warning(
            "op payload claims a different origin_org_id than the actor's; ignoring it",
            extra={"op_id": str(op.op_id)},
        )
    claimed_user = op.payload.get("origin_user_id")
    if claimed_user is not None and str(claimed_user) != str(actor.user_id):
        _logger.warning(
            "op payload claims a different origin_user_id than the actor's; ignoring it",
            extra={"op_id": str(op.op_id)},
        )


async def _insert_patient_alias(
    session: AsyncSession,
    *,
    patient_id: uuid.UUID,
    raw_name: str,
    match_method: str,
    match_score: float,
) -> None:
    await session.execute(
        text(
            """INSERT INTO patient_alias
                 (id, patient_id, raw_name, normalized_alias, match_method, match_score)
               VALUES
                 (:id, :patient_id, :raw_name, :normalized_alias, :match_method, :match_score)"""
        ),
        {
            "id": uuid.uuid4(),
            "patient_id": patient_id,
            "raw_name": raw_name,
            "normalized_alias": normalize(raw_name),
            "match_method": match_method,
            "match_score": match_score,
        },
    )


async def _insert_identity_review(
    session: AsyncSession,
    *,
    new_patient_id: uuid.UUID,
    candidate_patient_id: uuid.UUID,
    score: float,
    method: str,
    now: Any,
    run_id: str | None,
) -> None:
    """`ON CONFLICT (new_patient_id, candidate_patient_id) WHERE status =
    'pending' DO NOTHING` is the actual gate against a duplicate open pair
    — `uq_identity_review_open` (migration 0007), I5's sibling for
    identity. This call site can never exercise a real collision on its
    own: `new_patient_id` is always freshly INSERTed by the caller a few
    lines above, so no two calls from here ever share one. The mechanism
    is proven directly instead, by calling this function itself twice with
    the same ids — see tests/integration/test_identity_review_dedup.py,
    the same shape as P5.1's uq_escalation_open proof."""
    await session.execute(
        text(
            """INSERT INTO identity_review
                 (id, new_patient_id, candidate_patient_id, score, method, created_at, run_id)
               VALUES
                 (:id, :new_patient_id, :candidate_patient_id, :score, :method, :now, :run_id)
               ON CONFLICT (new_patient_id, candidate_patient_id) WHERE status = 'pending'
               DO NOTHING"""
        ),
        {
            "id": uuid.uuid4(),
            "new_patient_id": new_patient_id,
            "candidate_patient_id": candidate_patient_id,
            "score": score,
            "method": method,
            "now": now,
            "run_id": run_id,
        },
    )


async def _resolve_patient(
    session: AsyncSession,
    op: Op,
    actor: Actor,
    now: Any,
    run_id: str | None,
) -> uuid.UUID | Outcome:
    """Resolve the patient a create_referral op names, or say why it can't
    be. ADR-009's one named call site; app/linkage/pipeline.py's resolve()
    replaces the old bare exact match as of P6.2.

    Two payload shapes, tried in order:
    - `patient_id`: the patient must already exist (pre-Phase-4 behaviour,
      still supported — ADR-009 adds a second path, it does not remove
      this one).
    - `patient_name` (+ optional age, sex, phone): resolved via the
      blocked fuzzy-match pipeline, scoped to the actor's own org unit —
      the design's Screen 2 shows "Village: yours", never a picked
      village. `exact`/`alias` reuse the match. `fuzzy_auto` reuses the
      match too, and records the spelling as a new alias. `review_queue`
      and `new_patient` both create a new provisional patient row — the
      former also queues an identity_review row; the write is never
      blocked on a nurse's decision either way.
    """
    patient_id = op.payload.get("patient_id")
    if patient_id:
        exists = await session.execute(
            text("SELECT 1 FROM patient WHERE id=:id"), {"id": patient_id}
        )
        if exists.first() is None:
            return Outcome("rejected", None, {"reason": "unknown_patient"})
        return uuid.UUID(str(patient_id))

    name = op.payload.get("patient_name")
    if not name:
        return Outcome("rejected", None, {"reason": "patient_id or patient_name is required"})

    village_org_id = actor.org_unit_id
    phone = op.payload.get("phone")
    resolution = await resolve(
        session, get_settings(), raw_name=name, phone=phone, village_org_id=village_org_id
    )

    if resolution.method in ("exact", "alias"):
        return resolution.patient_id

    if resolution.method == "fuzzy_auto":
        await _insert_patient_alias(
            session,
            patient_id=resolution.patient_id,
            raw_name=name,
            match_method=resolution.method,
            match_score=resolution.score,
        )
        return resolution.patient_id

    # review_queue or new_patient: neither has an existing patient to
    # reuse, so a new provisional row is created either way.
    new_patient_id = uuid.uuid4()
    await session.execute(
        text(
            """INSERT INTO patient
                 (id, name, normalized_name, phone, village_org_id, age, sex,
                  created_by, created_at)
               VALUES
                 (:id, :name, :normalized_name, :phone, :village_org_id, :age, :sex,
                  :created_by, :now)"""
        ),
        {
            "id": new_patient_id,
            "name": name,
            "normalized_name": normalize(name),
            "phone": phone,
            "village_org_id": village_org_id,
            "age": op.payload.get("age"),
            "sex": op.payload.get("sex"),
            "created_by": actor.user_id,
            "now": now,
        },
    )

    if resolution.method == "review_queue":
        await _insert_identity_review(
            session,
            new_patient_id=new_patient_id,
            candidate_patient_id=resolution.candidate_id,
            score=resolution.score,
            method=resolution.method,
            now=now,
            run_id=run_id,
        )

    return new_patient_id


async def _apply_create_referral(
    session: AsyncSession,
    op: Op,
    device_id: str,
    clock: Clock,
    run_id: str | None,
    actor: Actor,
) -> Outcome:
    if not may(actor.role, State.CREATED):
        return Outcome("rejected", None, {"reason": "role_not_permitted"})

    existing = await session.execute(
        text("SELECT 1 FROM referral WHERE id=:id"), {"id": op.entity_id}
    )
    if existing.first() is not None:
        # A genuine op_id collision, not a replay (I1's receipt already
        # intercepts replays before apply_operation is ever called).
        return Outcome("rejected", None, {"reason": "already_exists"})

    _warn_if_payload_claims_org_identity(op, actor)

    raw_target_org_id = op.payload.get("target_org_id")
    target_org_id: uuid.UUID | None = None
    if raw_target_org_id is not None:
        try:
            target_org_id = uuid.UUID(str(raw_target_org_id))
        except ValueError:
            return Outcome("rejected", None, {"reason": "invalid_target_org_id"})
        if not await _target_org_is_ancestor_of_origin(session, target_org_id, actor.org_unit_id):
            return Outcome("rejected", None, {"reason": "invalid_target_org_id"})

    now = clock.now()
    resolved_patient = await _resolve_patient(session, op, actor, now, run_id)
    if isinstance(resolved_patient, Outcome):
        return resolved_patient
    patient_id = resolved_patient

    await session.execute(
        text(
            """INSERT INTO referral
                 (id, patient_id, origin_user_id, origin_org_id, target_org_id,
                  reason, priority, current_state, state_entered_at,
                  created_device_time, created_server_time)
               VALUES
                 (:id, :patient_id, :origin_user_id, :origin_org_id, :target_org_id,
                  :reason, :priority, 'CREATED', :now, :device_time, :now)"""
        ),
        {
            "id": op.entity_id,
            "patient_id": patient_id,
            "origin_user_id": actor.user_id,
            "origin_org_id": actor.org_unit_id,
            "target_org_id": target_org_id,
            "reason": op.payload.get("reason"),
            "priority": op.payload.get("priority"),
            "now": now,
            "device_time": op.device_time,
        },
    )

    seq = await _append_referral_event(
        session,
        referral_id=op.entity_id,
        from_state=None,
        to_state=State.CREATED.value,
        actor=actor,
        op=op,
        device_id=device_id,
        server_time=now,
        run_id=run_id,
    )
    return Outcome("accepted", seq, None)


async def _target_org_is_ancestor_of_origin(
    session: AsyncSession, target_org_id: uuid.UUID, origin_org_id: uuid.UUID
) -> bool:
    """P7.3 B1: referrals travel up the tree (ADR-005 point 1), so a
    target that is not a real ancestor of the origin — a nonexistent org,
    a lateral facility, or anything downward — is invalid. Self-inclusive
    (origin_org_id counts as its own ancestor here), same convention as
    SUBTREE_CTE."""
    query = """
        WITH RECURSIVE ancestors AS (
          SELECT id, parent_id FROM org_unit WHERE id = :origin_org_id
          UNION ALL
          SELECT o.id, o.parent_id FROM org_unit o JOIN ancestors a ON o.id = a.parent_id
        )
        SELECT 1 FROM ancestors WHERE id = :target_org_id
    """
    result = await session.execute(
        text(query), {"origin_org_id": origin_org_id, "target_org_id": target_org_id}
    )
    return result.first() is not None


async def _actor_can_see_referral_origin(
    session: AsyncSession, actor: Actor, origin_org_id: uuid.UUID
) -> bool:
    query = f"{SUBTREE_CTE}\nSELECT 1 FROM subtree WHERE id = :origin_org_id"
    params = {**subtree_params(actor.org_unit_id), "origin_org_id": origin_org_id}
    result = await session.execute(text(query), params)
    return result.first() is not None


async def _apply_referral_transition(
    session: AsyncSession,
    op: Op,
    device_id: str,
    clock: Clock,
    run_id: str | None,
    actor: Actor,
) -> Outcome:
    referral_row = await session.execute(
        text("SELECT current_state, origin_org_id FROM referral WHERE id=:id"),
        {"id": op.entity_id},
    )
    row = referral_row.first()
    if row is None:
        # ADR-003 "Gap 2" — not one of the five table rows.
        return Outcome("rejected", None, {"reason": "unknown_referral"})
    current_state = State(row.current_state)

    # D6/ADR-006: does this actor have any authority over this referral at
    # all — checked before the op's own coherence, alongside ADR-003's
    # rows 1 and 2, and before any lamport reasoning. Writes no event.
    if not await _actor_can_see_referral_origin(session, actor, row.origin_org_id):
        return Outcome("rejected", None, {"reason": "outside_org_scope"})

    from_state_raw = op.payload.get("from_state")
    to_state_raw = op.payload.get("to_state")
    if from_state_raw is None or to_state_raw is None:
        return Outcome("rejected", None, {"reason": "from_state and to_state are required"})
    try:
        from_state = State(from_state_raw)
        to_state = State(to_state_raw)
    except ValueError:
        return Outcome("rejected", None, {"reason": "unknown_state"})

    replayed_state, current_lamport, winning_op_id = await replay_referral(session, op.entity_id)
    # Live I3 alarm, not a substitute for the cache: the log and the cache
    # must already agree, or something upstream already broke I3. Logged
    # rather than raising (docs/decisions/ADR-007.md) — an AssertionError
    # here would roll back a legitimate write because of pre-existing
    # corruption, and python -O strips a bare `assert` statement outright.
    # The write continues with the cached current_state;
    # app/verify_replay.py is the real detector for this condition.
    if replayed_state != current_state:
        _logger.error(
            "current_state cache disagrees with the replayed event log — I3 violated",
            extra={"referral_id": str(op.entity_id), "op_id": str(op.op_id)},
        )

    decision = decide(
        actor_role=actor.role,
        from_state=from_state,
        to_state=to_state,
        current_state=current_state,
        incoming_lamport=op.lamport,
        current_lamport=current_lamport,
    )

    if decision.status == "rejected":
        return Outcome("rejected", None, {"reason": decision.reason})

    now = clock.now()
    seq = await _append_referral_event(
        session,
        referral_id=op.entity_id,
        from_state=from_state.value,
        to_state=to_state.value,
        actor=actor,
        op=op,
        device_id=device_id,
        server_time=now,
        run_id=run_id,
    )

    if decision.status == "accepted":
        await session.execute(
            text("UPDATE referral SET current_state=:to, state_entered_at=:now WHERE id=:id"),
            {"to": to_state.value, "now": now, "id": op.entity_id},
        )
        if from_state == State.ESCALATED:
            # D22: resolving on exit, in the SAME transaction as the event
            # append (I1). uq_escalation_open only blocks a SECOND open row
            # for the same (referral_id, breached_state) — without this, a
            # referral could never escalate twice, and the bug stays
            # invisible until a long demo. At most one escalation is open
            # per referral at a time (the sweep never escalates a referral
            # already in ESCALATED), so this needs no breached_state match.
            await session.execute(
                text(
                    """UPDATE escalation SET resolved_at=:now
                       WHERE referral_id=:id AND resolved_at IS NULL"""
                ),
                {"now": now, "id": op.entity_id},
            )
    elif decision.status == "conflict":
        # I6: the losing write is never deleted — it is already in
        # referral_event, appended above. This records the pair.
        await session.execute(
            text(
                """INSERT INTO sync_conflict
                     (id, entity_type, entity_id, field, winning_op_id, losing_op_id,
                      detected_at, run_id)
                   VALUES (:id, 'referral', :entity_id, 'current_state', :winning, :losing,
                           :now, :run_id)"""
            ),
            {
                "id": uuid.uuid4(),
                "entity_id": op.entity_id,
                "winning": winning_op_id,
                "losing": op.op_id,
                "now": now,
                "run_id": run_id,
            },
        )

    return Outcome(decision.status, seq, None)
