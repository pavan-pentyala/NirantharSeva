"""The push handler — encodes I1. See plan §5.3 and docs/decisions/ADR-002.md.

One transaction per op, not per batch, so a rejection does not roll back its
neighbours. The receipt is claimed before the work and finalised with the
work in the same transaction, so a crash anywhere leaves either nothing or
everything applied. A replay never re-executes — it returns the stored
answer, so the client sees an identical response the second time.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clock import Clock
from app.db import acquire_seq_lock
from app.schemas.sync import Op, OpResult, OpStatus
from app.sync.lamport import merge_lamport


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

            # 3. Validate + apply. In P2 this becomes the state machine guard.
            outcome = await apply_operation(s, op, device_id, clock, run_id)

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
        max_row = await s.execute(text("SELECT COALESCE(MAX(lamport), 0) AS m FROM toy_event"))
        db_max = max_row.scalar_one()

    server_lamport = merge_lamport(db_max, [op.lamport for op in ops])
    return results, server_lamport


async def apply_operation(
    session: AsyncSession,
    op: Op,
    device_id: str,
    clock: Clock,
    run_id: str | None,
) -> Outcome:
    """Toy model: one supported operation, "set_value" on entity "toy".

    Concurrent writes are resolved as a Lamport-clock last-writer-wins
    register: after appending this event, the winner for the entity is
    whichever event has the highest (lamport, device_id), independent of
    arrival order. That is what makes the final state the same regardless
    of the order a valid op set is applied in — see tests/property.
    """
    if op.entity != "toy" or op.operation != "set_value":
        return Outcome(
            status="rejected",
            server_seq=None,
            detail={"reason": f"unsupported entity/operation: {op.entity}/{op.operation}"},
        )

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
