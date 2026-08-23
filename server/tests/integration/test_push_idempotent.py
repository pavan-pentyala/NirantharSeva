"""POST the same batch five times: event created once, five identical
responses. This is I1 — the receipt is claimed once, replays return the
stored answer without re-executing. Ported from the toy model to referral
create_referral ops at Phase 4.3 (D1/D7 — the toy model was dropped)."""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from app.db import async_session_factory


def _batch(op_id, entity_id, patient_name="Idempotent Test Patient", lamport=17, device_id="d-1"):
    return {
        "device_id": device_id,
        "ops": [
            {
                "op_id": str(op_id),
                "entity": "referral",
                "entity_id": str(entity_id),
                "operation": "create_referral",
                "payload": {"patient_name": patient_name, "reason": "fever", "priority": "normal"},
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
            text("SELECT COUNT(*) FROM referral_event WHERE op_id = :id"), {"id": op_id}
        )
        assert count.scalar_one() == 1


async def test_five_identical_pushes_result_in_one_referral_row(client, auth_headers):
    op_id = uuid.uuid4()
    entity_id = uuid.uuid4()
    # A name with no word in common with test_same_batch_posted_five_times_
    # creates_row_once's "Idempotent Test Patient" — sharing three of four
    # words (as "... Two" would) scores 100 via rapidfuzz's
    # token_set_ratio (a subset of tokens is a perfect match under that
    # metric), which — now that create_referral resolves patients through
    # the real fuzzy pipeline (P6.2) rather than an exact match — would
    # silently reuse that other test's patient instead of creating this
    # test's own. See observation 44, docs/OBSERVATIONS.md.
    body = _batch(op_id, entity_id, patient_name="Repeat Push Second Patient")

    for _ in range(5):
        await client.post("/sync/push", json=body, headers=auth_headers)

    async with async_session_factory() as session:
        result = await session.execute(
            text(
                """SELECT p.name FROM referral r JOIN patient p ON p.id = r.patient_id
                   WHERE r.id = :id"""
            ),
            {"id": entity_id},
        )
        assert result.scalar_one() == "Repeat Push Second Patient"

        referral_count = await session.execute(
            text("SELECT COUNT(*) FROM referral WHERE id = :id"), {"id": entity_id}
        )
        assert referral_count.scalar_one() == 1


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
            text("SELECT COUNT(*) FROM referral_event WHERE op_id = :id"), {"id": op_id}
        )
        assert count.scalar_one() == 0
