"""POST the same batch five times: row created once, five identical
responses. This is I1 — the receipt is claimed once, replays return the
stored answer without re-executing."""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from app.db import async_session_factory


def _batch(op_id, entity_id, value=42, lamport=17, device_id="d-1"):
    return {
        "device_id": device_id,
        "ops": [
            {
                "op_id": str(op_id),
                "entity": "toy",
                "entity_id": str(entity_id),
                "operation": "set_value",
                "payload": {"value": value},
                "lamport": lamport,
                "device_time": datetime(2026, 8, 10, 9, 0, tzinfo=UTC).isoformat(),
            }
        ],
    }


async def test_same_batch_posted_five_times_creates_row_once(client, auth_headers):
    op_id = uuid.uuid4()
    entity_id = uuid.uuid4()
    body = _batch(op_id, entity_id)

    responses = []
    for _ in range(5):
        resp = await client.post("/sync/push", json=body, headers=auth_headers)
        assert resp.status_code == 200
        responses.append(resp.json())

    first = responses[0]
    for r in responses[1:]:
        assert r == first

    async with async_session_factory() as session:
        count = await session.execute(
            text("SELECT COUNT(*) FROM toy_event WHERE op_id = :id"), {"id": op_id}
        )
        assert count.scalar_one() == 1


async def test_five_identical_pushes_result_in_one_toy_row(client, auth_headers):
    op_id = uuid.uuid4()
    entity_id = uuid.uuid4()
    body = _batch(op_id, entity_id, value=99)

    for _ in range(5):
        await client.post("/sync/push", json=body, headers=auth_headers)

    async with async_session_factory() as session:
        result = await session.execute(
            text("SELECT value FROM toy WHERE id = :id"), {"id": entity_id}
        )
        assert result.scalar_one() == 99


@pytest.mark.parametrize("bad_field", ["operation", "entity"])
async def test_unsupported_op_is_rejected_and_not_recorded(client, auth_headers, bad_field):
    op_id = uuid.uuid4()
    entity_id = uuid.uuid4()
    body = _batch(op_id, entity_id)
    body["ops"][0][bad_field] = "nonsense"

    resp = await client.post("/sync/push", json=body, headers=auth_headers)
    assert resp.status_code == 200
    result = resp.json()["results"][0]
    assert result["status"] == "rejected"
    assert result["server_seq"] is None

    async with async_session_factory() as session:
        count = await session.execute(
            text("SELECT COUNT(*) FROM toy_event WHERE op_id = :id"), {"id": op_id}
        )
        assert count.scalar_one() == 0
