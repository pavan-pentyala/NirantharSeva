"""I1, stated as a property instead of five identical POSTs. docs/PHASE7_PLAN.md
P7.2 (D32), docs/decisions/ADR-003.md.

`tests/integration/test_push_idempotent.py` already proves one retry
pattern: the same single batch, posted five times. That is one shape, not
"arbitrary retry". Here, Hypothesis draws a legal state walk (same
strategy as `tests/property/test_referral_replay.py`) and an arbitrary
retry/duplication/re-interleaving pattern over the ops that walk produces:
each op can be resent any number of extra times, in any order, as long as
every op's FIRST application still lands in the walk's own causal order —
retries of an already-applied op can land anywhere *after* that, including
after every other op has already been applied once. This is deliberately
NOT op-permutation invariance (D32 records why that would be false by
design: ADR-003 decides coherence on `from_state`, so an op genuinely
arriving before its predecessor's first application is *correctly*
rejected or conflicted, not a bug). What must hold regardless of the
retry/duplication pattern: the final `current_state`, the replayed state,
and — the part a single hand-picked retry can't show — that every `op_id`
appears in `referral_event` exactly once, no matter how many times it was
resent.

Same fresh-engine-per-example pattern as `test_referral_replay.py` —
`app.db`'s module-level engine is bound to whichever event loop first used
it, and asyncpg connections cannot cross loops, so reusing it across many
Hypothesis examples (each its own `asyncio.run()`) would break.
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

DEVICE_TIME = datetime(2026, 8, 12, 9, 0, tzinfo=UTC)

# Same table test_referral_replay.py uses — one human-permitted role per
# state, enough to walk the machine without ever needing Role.SYSTEM.
_ROLE_FOR_STATE = {
    State.CREATED: Role.ASHA,
    State.IN_TRANSIT: Role.ASHA,
    State.ARRIVED: Role.MO,
    State.TREATED: Role.MO,
    State.BACK_REFERRED: Role.MO,
    State.CLOSED: Role.ASHA,
}
_USERNAME_FOR_ROLE = {Role.ASHA: "asha_a", Role.MO: "mo1"}
_MAX_EXTRA_RETRIES_PER_OP = 3


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


def _build_ops(path: list[State], entity_id: uuid.UUID, patient_id: uuid.UUID) -> list[Op]:
    ops = [
        Op(
            op_id=uuid.uuid4(),
            entity="referral",
            entity_id=entity_id,
            operation="create_referral",
            payload={"patient_id": str(patient_id), "reason": "fever", "priority": "normal"},
            lamport=1,
            device_time=DEVICE_TIME,
        )
    ]
    for i, (frm, to) in enumerate(zip(path, path[1:], strict=False), start=2):
        ops.append(
            Op(
                op_id=uuid.uuid4(),
                entity="referral",
                entity_id=entity_id,
                operation="transition",
                payload={"from_state": frm.value, "to_state": to.value},
                lamport=i,
                device_time=DEVICE_TIME,
            )
        )
    return ops


def _role_for_op(op: Op) -> Role:
    if op.operation == "create_referral":
        return Role.ASHA
    return _ROLE_FOR_STATE[State(op.payload["to_state"])]


async def _run_with_retries(path: list[State], send_order: list[int]) -> tuple:
    """send_order is a list of indices into the ops list built from `path`
    (length >= len(ops), each index 0..len(ops)-1 appearing at least once,
    in first-occurrence order matching `path`'s own order — see the
    strategy in the test below for how that's guaranteed). Returns
    (cached_state, replayed_state, per_op_event_counts, n_ops)."""
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
                       VALUES (:id, 'Retry Sequence Fixture Human',
                               'retry sequence fixture human', :now)"""
                ),
                {"id": patient_id, "now": DEVICE_TIME},
            )

        ops = _build_ops(path, entity_id, patient_id)

        for idx in send_order:
            op = ops[idx]
            actor = await _actor_for(session_factory, _role_for_op(op))
            await handle_push(session_factory, "d-1", [op], RealClock(), None, actor)

        async with session_factory() as s:
            cache_row = await s.execute(
                text("SELECT current_state FROM referral WHERE id=:id"), {"id": entity_id}
            )
            cached_state = State(cache_row.scalar_one())

            replayed_state, _, _ = await replay_referral(s, entity_id)

            counts = (
                await s.execute(
                    text(
                        "SELECT op_id, COUNT(*) AS n FROM referral_event "
                        "WHERE referral_id = :id GROUP BY op_id"
                    ),
                    {"id": entity_id},
                )
            ).all()

        return cached_state, replayed_state, {row.op_id: row.n for row in counts}, len(ops)
    finally:
        await engine.dispose()


@given(data=st.data())
@hyp_settings(max_examples=20, deadline=None)
def test_arbitrary_retry_yields_the_same_state_and_one_event_row_per_op_id(data):
    # 1. A legal walk — identical strategy to test_referral_replay.py.
    path = [State.CREATED]
    steps = data.draw(st.integers(min_value=0, max_value=5))
    for _ in range(steps):
        options = sorted(TRANSITIONS[path[-1]] - {State.ESCALATED}, key=lambda s: s.value)
        if not options:
            break
        path.append(data.draw(st.sampled_from(options)))
    n_ops = 1 + (len(path) - 1)  # one create + one op per transition

    # 2. An arbitrary retry/duplication pattern: each op gets 0-3 EXTRA
    # resends, and those extras are shuffled into any order — but every
    # op's first send stays in original (causal) order, or the walk itself
    # would not legally complete and this would stop testing retries.
    extra_counts = data.draw(
        st.lists(
            st.integers(min_value=0, max_value=_MAX_EXTRA_RETRIES_PER_OP),
            min_size=n_ops,
            max_size=n_ops,
        )
    )
    retries_pool = [i for i, n in enumerate(extra_counts) for _ in range(n)]
    shuffled_retries = data.draw(st.permutations(retries_pool))
    send_order = list(range(n_ops)) + list(shuffled_retries)

    cached_state, replayed_state, event_counts, n_ops_built = asyncio.run(
        _run_with_retries(path, send_order)
    )
    assert n_ops_built == n_ops

    assert cached_state == path[-1]
    assert replayed_state == path[-1]
    assert cached_state == replayed_state

    # I1, as a property: however many times an op was resent, it appears
    # in referral_event exactly once.
    assert len(event_counts) == n_ops, event_counts
    assert all(n == 1 for n in event_counts.values()), event_counts
