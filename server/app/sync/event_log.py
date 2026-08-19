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
"""

import uuid
from collections.abc import Sequence

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
