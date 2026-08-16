"""Hypothesis property tests for the sync core. See plan §11.2 ("Op-
permutation invariance; idempotency under arbitrary retry") and §5.6, which
singles out the permutation test as worth a paragraph in Chapter 4.

Each example gets its own short-lived engine bound to its own asyncio.run()
event loop. The module-level app.db engine is bound to whichever loop first
used it, and asyncpg connections cannot cross event loops, so reusing it
here across many Hypothesis examples would break.
"""

import asyncio
import random
import uuid
from datetime import UTC, datetime

from hypothesis import given
from hypothesis import settings as hyp_settings
from hypothesis import strategies as st
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.clock import RealClock
from app.config import get_settings
from app.schemas.sync import Op
from app.sync.push import handle_push

DEVICE_TIME = datetime(2026, 8, 10, 9, 0, tzinfo=UTC)

_spec = st.fixed_dictionaries(
    {
        "device_id": st.sampled_from(["d-1", "d-2", "d-3", "d-4"]),
        "lamport": st.integers(min_value=0, max_value=50),
        "value": st.integers(min_value=-1000, max_value=1000),
    }
)

# Unique (device_id, lamport) pairs: the LWW winner is decided by
# (lamport, device_id) alone. A duplicate pair would fall through to a
# seq-order tiebreak, which is deliberately order-dependent (see push.py) —
# excluded here so this test is only checking the guarantee that is meant
# to be order-independent.
op_set_strategy = st.lists(
    _spec, min_size=2, max_size=6, unique_by=lambda s: (s["device_id"], s["lamport"])
)


def _expected_winner(specs: list[dict]) -> int:
    return max(specs, key=lambda s: (s["lamport"], s["device_id"]))["value"]


async def _apply_in_order(specs: list[dict], entity_id: uuid.UUID) -> tuple[int, int]:
    """Push each spec as its own batch, in the given order, to a fresh
    engine. Returns (final toy.value, number of toy_event rows recorded)."""
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        for spec in specs:
            op = Op(
                op_id=uuid.uuid4(),
                entity="toy",
                entity_id=entity_id,
                operation="set_value",
                payload={"value": spec["value"]},
                lamport=spec["lamport"],
                device_time=DEVICE_TIME,
            )
            await handle_push(session_factory, spec["device_id"], [op], RealClock(), None)

        async with session_factory() as s:
            value_row = await s.execute(
                text("SELECT value FROM toy WHERE id=:id"), {"id": entity_id}
            )
            count_row = await s.execute(
                text("SELECT COUNT(*) FROM toy_event WHERE toy_id=:id"), {"id": entity_id}
            )
            return value_row.scalar_one(), count_row.scalar_one()
    finally:
        await engine.dispose()


@given(specs=op_set_strategy, seed=st.integers(min_value=0, max_value=2**31 - 1))
@hyp_settings(max_examples=15, deadline=None)
def test_final_state_is_the_same_regardless_of_application_order(specs, seed):
    """For any permutation of a valid op set, the final server state is the
    same. Three orderings — as generated, reversed, and one shuffle — each
    applied to their own fresh entity, must converge to the same value."""
    rng = random.Random(seed)
    shuffled = list(specs)
    rng.shuffle(shuffled)
    orderings = [specs, list(reversed(specs)), shuffled]

    expected = _expected_winner(specs)

    for ordering in orderings:
        entity_id = uuid.uuid4()
        value, event_count = asyncio.run(_apply_in_order(ordering, entity_id))
        assert value == expected
        assert event_count == len(specs)


async def _apply_and_retry(specs: list[dict], entity_id: uuid.UUID, seed: int):
    settings = get_settings()
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        ops = [
            Op(
                op_id=uuid.uuid4(),
                entity="toy",
                entity_id=entity_id,
                operation="set_value",
                payload={"value": spec["value"]},
                lamport=spec["lamport"],
                device_time=DEVICE_TIME,
            )
            for spec in specs
        ]
        first_results, first_lamport = await handle_push(
            session_factory, "d-retry", ops, RealClock(), None
        )

        retry_ops = list(ops)
        random.Random(seed).shuffle(retry_ops)
        retry_results, retry_lamport = await handle_push(
            session_factory, "d-retry", retry_ops, RealClock(), None
        )

        async with session_factory() as s:
            count_row = await s.execute(
                text("SELECT COUNT(*) FROM toy_event WHERE toy_id=:id"), {"id": entity_id}
            )
            event_count = count_row.scalar_one()

        return first_results, first_lamport, retry_results, retry_lamport, event_count
    finally:
        await engine.dispose()


@given(specs=op_set_strategy, seed=st.integers(min_value=0, max_value=2**31 - 1))
@hyp_settings(max_examples=15, deadline=None)
def test_retry_batch_is_idempotent_regardless_of_retry_order(specs, seed):
    """Resubmitting the same op_ids, even reshuffled, never re-executes —
    each op's stored receipt is replayed verbatim (I1), so the retry's
    per-op results match the first submission's exactly and no extra
    events are recorded."""
    entity_id = uuid.uuid4()
    first_results, first_lamport, retry_results, retry_lamport, event_count = asyncio.run(
        _apply_and_retry(specs, entity_id, seed)
    )

    by_op_id_first = {r.op_id: r for r in first_results}
    by_op_id_retry = {r.op_id: r for r in retry_results}

    assert by_op_id_first.keys() == by_op_id_retry.keys()
    for op_id, first in by_op_id_first.items():
        retry = by_op_id_retry[op_id]
        assert retry.status == first.status
        assert retry.server_seq == first.server_seq
        assert retry.detail == first.detail

    assert retry_lamport == first_lamport
    assert event_count == len(specs)
