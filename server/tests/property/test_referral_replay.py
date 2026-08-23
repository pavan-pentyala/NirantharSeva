"""I3: for a random legal transition sequence, current_state replayed from
the event log equals the cached value. Plan §6.5, docs/decisions/ADR-003.md.

Fresh-engine-per-example: app.db's module-level engine is bound to
whichever event loop first used it, and asyncpg connections cannot cross
loops, so reusing it across many Hypothesis examples (each its own
asyncio.run()) would break. tests/property/test_push_idempotency.py
(docs/PHASE7_PLAN.md P7.2, D32) reuses the same pattern and the same walk
strategy, for arbitrary retry rather than replay-vs-cache agreement.

Calls handle_push() directly — no client, no login, no JWT — so it builds
its own Actor by looking up the seeded asha_a / mo1 rows (server/app/seed.py)
by name, exactly like get_current_user does against a real request. This
test has no reference to authentication otherwise, which is exactly why
it is in scope for docs/decisions/ADR-006.md's actor-threading change (see
docs/PHASE2_PLAN.md, "the one that gets missed").
"""

import asyncio
import uuid
from datetime import UTC, datetime

from hypothesis import given
from hypothesis import settings as hyp_settings
from hypothesis import strategies as st
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.clock import RealClock
from app.config import get_settings
from app.domain.actor import Actor
from app.domain.states import TRANSITIONS, Role, State
from app.schemas.sync import Op
from app.sync.event_log import replay_referral
from app.sync.push import handle_push

DEVICE_TIME = datetime(2026, 8, 10, 9, 0, tzinfo=UTC)

# One human-permitted role per state, per app/domain/states.py GUARDS —
# enough to walk the machine without ever needing Role.SYSTEM (which no
# human op can legally submit; ESCALATED/LOST are excluded from the walk).
_ROLE_FOR_STATE = {
    State.CREATED: Role.ASHA,
    State.IN_TRANSIT: Role.ASHA,
    State.ARRIVED: Role.MO,
    State.TREATED: Role.MO,
    State.BACK_REFERRED: Role.MO,
    State.CLOSED: Role.ASHA,
}
_USERNAME_FOR_ROLE = {Role.ASHA: "asha_a", Role.MO: "mo1"}


async def _actor_for(session_factory: async_sessionmaker[AsyncSession], role: Role) -> Actor:
    username = _USERNAME_FOR_ROLE[role]
    async with session_factory() as s:
        row = (
            await s.execute(
                text("SELECT id, org_unit_id FROM app_user WHERE name = :name"),
                {"name": username},
            )
        ).one()
    return Actor(user_id=row.id, role=role, org_unit_id=row.org_unit_id)


async def _run_walk(path: list[State]) -> tuple[State | None, State | None]:
    """Pushes `path` as a chain of create_referral + transition ops against
    a fresh engine. Returns (cached_current_state, replayed_current_state)."""
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        entity_id = uuid.uuid4()
        patient_id = uuid.uuid4()
        async with session_factory() as s, s.begin():
            await s.execute(
                text(
                    """INSERT INTO patient (id, name, normalized_name, created_at)
                       VALUES (:id, 'Test Patient', 'test patient', :now)"""
                ),
                {"id": patient_id, "now": DEVICE_TIME},
            )

        asha_actor = await _actor_for(session_factory, Role.ASHA)
        create_op = Op(
            op_id=uuid.uuid4(),
            entity="referral",
            entity_id=entity_id,
            operation="create_referral",
            payload={"patient_id": str(patient_id), "reason": "fever", "priority": "normal"},
            lamport=1,
            device_time=DEVICE_TIME,
        )
        await handle_push(session_factory, "d-1", [create_op], RealClock(), None, asha_actor)

        for i, (frm, to) in enumerate(zip(path, path[1:], strict=False), start=2):
            op = Op(
                op_id=uuid.uuid4(),
                entity="referral",
                entity_id=entity_id,
                operation="transition",
                payload={"from_state": frm.value, "to_state": to.value},
                lamport=i,
                device_time=DEVICE_TIME,
            )
            actor = await _actor_for(session_factory, _ROLE_FOR_STATE[to])
            results, _ = await handle_push(session_factory, "d-1", [op], RealClock(), None, actor)
            assert results[0].status == "accepted", results[0]

        async with session_factory() as s:
            cache_row = await s.execute(
                text("SELECT current_state FROM referral WHERE id=:id"), {"id": entity_id}
            )
            cached_state = State(cache_row.scalar_one())

            replayed_state, _, _ = await replay_referral(s, entity_id)

        return cached_state, replayed_state
    finally:
        await engine.dispose()


@given(data=st.data())
@hyp_settings(max_examples=20, deadline=None)
def test_replayed_state_matches_cached_state_for_a_random_legal_walk(data):
    path = [State.CREATED]
    steps = data.draw(st.integers(min_value=0, max_value=5))
    for _ in range(steps):
        options = sorted(TRANSITIONS[path[-1]] - {State.ESCALATED}, key=lambda s: s.value)
        if not options:
            break
        path.append(data.draw(st.sampled_from(options)))

    cached_state, replayed_state = asyncio.run(_run_walk(path))

    assert cached_state == path[-1]
    assert replayed_state == path[-1]
    assert cached_state == replayed_state
