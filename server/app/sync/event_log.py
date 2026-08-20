"""The row-to-replay-tuple mapping and the per-referral ordered fetch,
shared by app/sync/push.py, app/verify_replay.py, the referral timeline
endpoint, and tests/property/test_referral_replay.py. See
docs/PHASE3_PLAN.md, "The shared extraction".

In app/sync/, not app/domain/ — this module imports SQLAlchemy, and
app/domain/states.py's own docstring promises no database imports. The
api -> sync import the timeline endpoint creates mirrors the sync -> api
import push.py already has for app/api/scoping.py.

Deliberately NOT shared: the query. The per-referral query here
(`WHERE referral_id = ? ORDER BY seq ASC`, which hits idx_event_referral
exactly) and app/verify_replay.py's single bulk scan are different access
patterns — building the bulk scan out of this function in a loop is an
N+1: two round trips at fixture size, thousands after Phase 7's cohort
generator. Share triple() and the fold; keep the two queries separate on
purpose.

insert_referral_event is the one write in this otherwise read-only module —
extracted from app/sync/push.py so app/domain/escalation.py's sweep (Phase
5, a write with no client Op to shape it) does not duplicate the INSERT
text. push.py's _append_referral_event still owns the Op-shaped call site;
this is the raw insert underneath it.
"""

import json
import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Row
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.states import State, replay_state

Triple = tuple[State | None, State, int, str]


def triple(row: Row) -> Triple:
    """The one place a referral_event row becomes a replay tuple. Row must
    expose from_state, to_state, lamport, op_id."""
    return (
        State(row.from_state) if row.from_state else None,
        State(row.to_state),
        row.lamport,
        str(row.op_id),
    )


async def fetch_triples(session: AsyncSession, referral_id: uuid.UUID) -> Sequence[Triple]:
    """referral_id's events in commit order (seq ASC) — the order
    replay_state is defined on. Hits idx_event_referral(referral_id, seq)
    exactly."""
    result = await session.execute(
        text(
            """SELECT from_state, to_state, lamport, op_id FROM referral_event
               WHERE referral_id=:id ORDER BY seq ASC"""
        ),
        {"id": referral_id},
    )
    return [triple(r) for r in result]


async def replay_referral(
    session: AsyncSession, referral_id: uuid.UUID
) -> tuple[State | None, int, str | None]:
    """Fold referral_id's event log with replay_state. Returns all three
    values, not just the state — decide() needs the lamport and the
    sync_conflict insert needs the winning op_id."""
    return replay_state(await fetch_triples(session, referral_id))


async def insert_referral_event(
    session: AsyncSession,
    *,
    referral_id: uuid.UUID,
    from_state: str | None,
    to_state: str,
    actor_user_id: uuid.UUID | None,
    actor_role: str,
    device_time: datetime,
    server_time: datetime,
    lamport: int,
    op_id: uuid.UUID,
    device_id: str,
    payload: dict[str, Any] | None,
    run_id: str | None,
) -> int:
    """The one INSERT INTO referral_event in the codebase. Caller holds
    acquire_seq_lock (docs/decisions/ADR-002.md) and is inside the one
    transaction that also writes this event's effect (I1) — this function
    does neither; it only writes the row."""
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
            "actor_user_id": actor_user_id,
            "actor_role": actor_role,
            "device_time": device_time,
            "server_time": server_time,
            "lamport": lamport,
            "op_id": op_id,
            "device_id": device_id,
            "payload": json.dumps(payload) if payload is not None else None,
            "run_id": run_id,
        },
    )
    return inserted.scalar_one()
