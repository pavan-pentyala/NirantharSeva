"""The push handler — encodes I1. See plan §5.3 and docs/decisions/ADR-002.md.

One transaction per op, not per batch, so a rejection does not roll back its
neighbours. The receipt is claimed before the work and finalised with the
work in the same transaction, so a crash anywhere leaves either nothing or
everything applied. A replay never re-executes — it returns the stored
answer, so the client sees an identical response the second time.

Phase 2.1 adds the referral entity alongside the toy model (D1: toy stays
frozen, unchanged). See docs/decisions/ADR-003.md for the conflict policy
and app/domain/states.py for the state machine apply_operation dispatches
into.

Phase 2.2 (docs/decisions/ADR-006.md): who is acting comes from the
authenticated Actor, resolved server-side — never from op.payload. A
device cannot be trusted to name its own role, org, or user id.
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
from app.db import acquire_seq_lock
from app.domain.actor import Actor
from app.domain.states import State, may
from app.instrumentation.logging import get_logger
from app.schemas.sync import Op, OpResult, OpStatus
from app.sync.conflicts import decide
from app.sync.event_log import replay_referral
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
    actor: Actor | None = None,
) -> tuple[list[OpResult], int]:
    # actor is only required for entity="referral" ops (D6/ADR-006) — toy
    # pushes (D1, frozen) never read it, so it stays optional here rather
    # than forcing every toy-only caller (tests/property/test_permutation.py,
    # tests/integration/test_pull_cursor.py) to fabricate one.
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
        max_row = await s.execute(
            text(
                """SELECT GREATEST(
                     (SELECT COALESCE(MAX(lamport), 0) FROM toy_event),
                     (SELECT COALESCE(MAX(lamport), 0) FROM referral_event)
                   ) AS m"""
            )
        )
        db_max = max_row.scalar_one()

    server_lamport = merge_lamport(db_max, [op.lamport for op in ops])
    return results, server_lamport


async def apply_operation(
    session: AsyncSession,
    op: Op,
    device_id: str,
    clock: Clock,
    run_id: str | None,
    actor: Actor | None = None,
) -> Outcome:
    if op.entity == "toy" and op.operation == "set_value":
        return await _apply_toy_set_value(session, op, device_id, clock, run_id)
    if op.entity == "referral" and op.operation == "create_referral":
        return await _apply_create_referral(session, op, device_id, clock, run_id, actor)
    if op.entity == "referral" and op.operation == "transition":
        return await _apply_referral_transition(session, op, device_id, clock, run_id, actor)
    return Outcome(
        status="rejected",
        server_seq=None,
        detail={"reason": f"unsupported entity/operation: {op.entity}/{op.operation}"},
    )


async def _apply_toy_set_value(
    session: AsyncSession,
    op: Op,
    device_id: str,
    clock: Clock,
    run_id: str | None,
) -> Outcome:
    """Toy model: one supported operation, "set_value" on entity "toy".
    Unchanged since Phase 1.1 — frozen per D1.

    Concurrent writes are resolved as a Lamport-clock last-writer-wins
    register: after appending this event, the winner for the entity is
    whichever event has the highest (lamport, device_id), independent of
    arrival order. That is what makes the final state the same regardless
    of the order a valid op set is applied in — see tests/property.
    """
    value = op.payload.get("value")
    if not isinstance(value, int) or isinstance(value, bool):
        return Outcome(
            status="rejected",
            server_seq=None,
            detail={"reason": "payload.value must be an integer"},
        )

    existing = await session.execute(
        text("SELECT value FROM toy WHERE id=:id"), {"id": op.entity_id}
    )
    existing_row = existing.first()
    server_time = clock.now()

    inserted = await session.execute(
        text(
            """INSERT INTO toy_event
                 (toy_id, old_value, new_value, op_id, device_id, lamport,
                  device_time, server_time, run_id)
               VALUES
                 (:toy_id, :old_value, :new_value, :op_id, :device_id, :lamport,
                  :device_time, :server_time, :run_id)
               RETURNING seq"""
        ),
        {
            "toy_id": op.entity_id,
            "old_value": existing_row.value if existing_row else None,
            "new_value": value,
            "op_id": op.op_id,
            "device_id": device_id,
            "lamport": op.lamport,
            "device_time": op.device_time,
            "server_time": server_time,
            "run_id": run_id,
        },
    )
    seq = inserted.scalar_one()

    winner = await session.execute(
        text(
            """SELECT new_value, op_id
               FROM toy_event
               WHERE toy_id = :toy_id
               ORDER BY lamport DESC, device_id DESC, seq DESC
               LIMIT 1"""
        ),
        {"toy_id": op.entity_id},
    )
    w = winner.one()

    if existing_row is None:
        await session.execute(
            text(
                """INSERT INTO toy (id, value, updated_at, run_id)
                   VALUES (:id, :value, :updated_at, :run_id)"""
            ),
            {
                "id": op.entity_id,
                "value": w.new_value,
                "updated_at": server_time,
                "run_id": run_id,
            },
        )
    else:
        await session.execute(
            text(
                """UPDATE toy SET value=:value, updated_at=:updated_at, run_id=:run_id
                   WHERE id=:id"""
            ),
            {
                "value": w.new_value,
                "updated_at": server_time,
                "run_id": run_id,
                "id": op.entity_id,
            },
        )

    status: OpStatus = "accepted" if w.op_id == op.op_id else "accepted_stale"
    return Outcome(status=status, server_seq=seq, detail=None)


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
    inserted = await session.execute(
        text(
            """INSERT INTO referral_event
                 (id, referral_id, from_state, to_state, actor_user_id, actor_role,
                  device_time, server_time, lamport, op_id, device_id, payload, run_id)
               VALUES
                 (:id, :referral_id, :from_state, :to_state, :actor_user_id, :actor_role,
                  :device_time, :server_time, :lamport, :op_id, :device_id,
                  CAST(:payload AS jsonb), :run_id)
               RETURNING seq"""
        ),
        {
            "id": uuid.uuid4(),
            "referral_id": referral_id,
            "from_state": from_state,
            "to_state": to_state,
            "actor_user_id": actor.user_id,
            "actor_role": actor.role.value,
            "device_time": op.device_time,
            "server_time": server_time,
            "lamport": op.lamport,
            "op_id": op.op_id,
            "device_id": device_id,
            "payload": json.dumps(op.payload),
            "run_id": run_id,
        },
    )
    return inserted.scalar_one()


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

    patient_id = op.payload.get("patient_id")
    if not patient_id:
        return Outcome("rejected", None, {"reason": "patient_id is required"})
    patient_exists = await session.execute(
        text("SELECT 1 FROM patient WHERE id=:id"), {"id": patient_id}
    )
    if patient_exists.first() is None:
        return Outcome("rejected", None, {"reason": "unknown_patient"})

    _warn_if_payload_claims_org_identity(op, actor)

    now = clock.now()
    await session.execute(
        text(
            """INSERT INTO referral
                 (id, patient_id, origin_user_id, origin_org_id, target_org_id,
                  reason, priority, current_state, state_entered_at,
                  sla_profile_id, created_device_time, created_server_time)
               VALUES
                 (:id, :patient_id, :origin_user_id, :origin_org_id, :target_org_id,
                  :reason, :priority, 'CREATED', :now, NULL, :device_time, :now)"""
        ),
        {
            "id": op.entity_id,
            "patient_id": patient_id,
            "origin_user_id": actor.user_id,
            "origin_org_id": actor.org_unit_id,
            "target_org_id": op.payload.get("target_org_id"),
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
