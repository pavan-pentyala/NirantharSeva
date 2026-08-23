"""The escalation sweep. docs/IMPLEMENTATION_PLAN.md §9.1, docs/PHASE5_PLAN.md
P5.1 (D17, D22) — follow PHASE5_PLAN.md's "Traps" section, not the plan's raw
snippet, which has three known errors that section corrects.

Finds every live referral that has sat in its current state longer than its
sla_profile's (SLA_SCALE-scaled) window, and escalates it: one `escalation`
row, one SYSTEM `ESCALATED` referral_event, and `referral.current_state`
moved to ESCALATED — all three in **one transaction per referral, not per
sweep** (same reasoning as push.py's one-transaction-per-op), so one
referral failing does not roll back its neighbours.

I5 (no double escalation) is enforced by `uq_escalation_open`, a partial
unique index on (referral_id, breached_state) WHERE resolved_at IS NULL —
not by a Python check. `ON CONFLICT ... DO NOTHING RETURNING id` is the
actual gate below: if it returns nothing, this referral is already
escalated and open, and no event is written. Delete the "already escalated"
re-check a few lines below and this still holds — that check is a cheap
race-window narrower, not the mechanism.

Runs from app/scheduler/run.py, a *second* writer process, separate from
the API (plan §2.3, so E4's fault injection can kill it independently) — so
every event append here takes acquire_seq_lock first, same as push.py, or
the pull cursor can silently skip events (docs/decisions/ADR-002.md).

Never calls datetime.now(). Takes the injected Clock, same as everything
else (docs/decisions/ADR-001.md) — CI greps for this.
"""

import uuid
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clock import Clock
from app.config import get_settings
from app.db import acquire_seq_lock
from app.domain.states import Role, State
from app.instrumentation.logging import get_logger
from app.realtime import ESCALATION_CHANNEL
from app.sync.event_log import insert_referral_event, replay_referral

_logger = get_logger(__name__)
_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "nirantharseva.escalation")

# secs, not hours=>, so max_hours * SLA_SCALE can be fractional (a demo runs
# SLA_SCALE small enough to breach a 24h window in seconds) without an
# int-parameter cast in make_interval.
#
# CAST(:sla_scale AS double precision) is load-bearing, not decoration:
# without it, asyncpg's prepared-statement protocol infers :sla_scale's
# type from its *first* use (s.max_hours * :sla_scale, s.max_hours being
# integer) and resolves it as integer — silently truncating any SLA_SCALE
# between 0 and 1 to 0, which makes make_interval's result exactly zero and
# every referral "breached" the instant it's created, whatever the real
# window was supposed to be. SLA_SCALE=1.0 (the production default) hides
# this completely (round(1.0) == 1), which is exactly why it survived
# app/domain/escalation.py's own test suite — see
# docs/OBSERVATIONS.md for the fractional-scale test this bug
# needed and the ones already there didn't cover.
_BREACH_QUERY = """
    SELECT r.id, r.current_state, s.escalate_to_role, s.version
    FROM referral r
    JOIN sla_profile s ON s.state = r.current_state AND s.active
    WHERE r.current_state NOT IN ('CLOSED', 'LOST', 'ESCALATED')
      AND r.state_entered_at
          + make_interval(secs => s.max_hours * CAST(:sla_scale AS double precision) * 3600)
          < :now
"""


def _event_op_id(referral_id: uuid.UUID, breached_state: str, triggered_at: datetime) -> uuid.UUID:
    """Deterministic, the scripts/demo_walk.py pattern — but keyed on
    triggered_at too, not just (referral, breached_state) as
    docs/PHASE5_PLAN.md's trap literally describes. A referral can
    legitimately re-breach the SAME state after an earlier escalation on it
    resolves (D22): TRANSITIONS[ESCALATED] never returns directly to the
    breached state, so the SLA window has to elapse again first, which
    means triggered_at genuinely differs between the two escalations — and
    it is what tells their events apart. Without it, the second ESCALATED
    event's op_id would collide with the first's, and since
    referral_event.op_id is NOT NULL UNIQUE, the second escalation would
    either crash the sweep or (with ON CONFLICT DO NOTHING) silently write
    no event at all — an escalation row with nothing in the log to justify
    it, which is exactly what I3 forbids."""
    return uuid.uuid5(_NAMESPACE, f"{referral_id}:{breached_state}:{triggered_at.isoformat()}")


async def sweep(session_factory: async_sessionmaker[AsyncSession], clock: Clock) -> list[uuid.UUID]:
    """One sweep pass. Returns the ids of referrals newly escalated by this
    call (not ones already open from an earlier sweep)."""
    now = clock.now()
    settings = get_settings()
    escalated: list[uuid.UUID] = []

    async with session_factory() as read_session:
        breach_rows = (
            await read_session.execute(
                text(_BREACH_QUERY), {"now": now, "sla_scale": settings.sla_scale}
            )
        ).all()

    for row in breach_rows:
        referral_id = row.id
        breached_state = row.current_state
        async with session_factory() as s, s.begin():
            await acquire_seq_lock(s)

            # Re-check under the lock: the scan above ran without it held,
            # and a concurrent client push (the other writer this lock
            # serialises against) may have already moved this referral on.
            current = (
                await s.execute(
                    text("SELECT current_state FROM referral WHERE id=:id"), {"id": referral_id}
                )
            ).first()
            if current is None or current.current_state != breached_state:
                continue

            inserted = await s.execute(
                text(
                    """INSERT INTO escalation
                         (id, referral_id, breached_state, triggered_at, sla_profile_version)
                       VALUES (:id, :referral_id, :breached_state, :now, :version)
                       ON CONFLICT (referral_id, breached_state) WHERE resolved_at IS NULL
                       DO NOTHING
                       RETURNING id"""
                ),
                {
                    "id": uuid.uuid4(),
                    "referral_id": referral_id,
                    "breached_state": breached_state,
                    "now": now,
                    "version": row.version,
                },
            )
            if inserted.first() is None:
                # I5 enforced by the index, not by this check — a
                # concurrent writer (or an overlapping sweep) already
                # opened one. Delete the "already escalated" re-check above
                # and this line is still what stops a second event.
                continue

            _, current_lamport, _ = await replay_referral(s, referral_id)

            await insert_referral_event(
                s,
                referral_id=referral_id,
                from_state=breached_state,
                to_state=State.ESCALATED.value,
                actor_user_id=None,
                actor_role=Role.SYSTEM.value,
                device_time=now,
                server_time=now,
                lamport=current_lamport + 1,
                op_id=_event_op_id(referral_id, breached_state, now),
                device_id="scheduler",
                payload=None,
                run_id=settings.run_id,
            )

            await s.execute(
                text("UPDATE referral SET current_state=:to, state_entered_at=:now WHERE id=:id"),
                {"to": State.ESCALATED.value, "now": now, "id": referral_id},
            )

            # D18/ADR-011: NOTIFY inside this transaction, not after it —
            # Postgres queues a transactional NOTIFY and only delivers it
            # once the transaction commits, which is exactly "after the
            # transaction that inserts the escalation row commits" without
            # a second connection or a second round trip. A rollback (the
            # continue branches above) never reaches this line, so a
            # skipped duplicate never notifies either.
            await s.execute(text(f"NOTIFY {ESCALATION_CHANNEL}"))

            escalated.append(referral_id)
            _logger.info("referral escalated by sweep", extra={"referral_id": str(referral_id)})

    return escalated
