"""GET /referrals/{id}/timeline — every event, tagged advanced, agreeing
with the cache and the I3 verifier's fold. docs/decisions/ADR-008.md.
"""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from app.db import async_session_factory

DEVICE_TIME = datetime(2026, 8, 10, 9, 0, tzinfo=UTC).isoformat()


@pytest.fixture
async def patient_id():
    pid = uuid.uuid4()
    async with async_session_factory() as session, session.begin():
        await session.execute(
            text(
                """INSERT INTO patient (id, name, normalized_name, created_at)
                   VALUES (:id, 'Timeline Test Patient', 'timeline test patient', :now)"""
            ),
            {"id": pid, "now": datetime(2026, 8, 10, 9, 0, tzinfo=UTC)},
        )
    return pid


def _create_op(entity_id, patient, lamport):
    return {
        "op_id": str(uuid.uuid4()),
        "entity": "referral",
        "entity_id": str(entity_id),
        "operation": "create_referral",
        "payload": {"patient_id": str(patient), "reason": "fever", "priority": "normal"},
        "lamport": lamport,
        "device_time": DEVICE_TIME,
    }


def _transition_op(entity_id, from_state, to_state, lamport):
    return {
        "op_id": str(uuid.uuid4()),
        "entity": "referral",
        "entity_id": str(entity_id),
        "operation": "transition",
        "payload": {"from_state": from_state, "to_state": to_state},
        "lamport": lamport,
        "device_time": DEVICE_TIME,
    }


async def _push(client, headers, device_id, op):
    resp = await client.post(
        "/sync/push", json={"device_id": device_id, "ops": [op]}, headers=headers
    )
    assert resp.status_code == 200
    return resp.json()["results"][0]


async def test_timeline_returns_every_event_in_seq_order_with_advanced_flags(
    client, auth_headers, anm_auth_headers, patient_id
):
    entity_id = uuid.uuid4()
    create = await _push(client, auth_headers, "d-asha", _create_op(entity_id, patient_id, 1))
    assert create["status"] == "accepted"
    accepted = await _push(
        client, auth_headers, "d-asha", _transition_op(entity_id, "CREATED", "IN_TRANSIT", 2)
    )
    assert accepted["status"] == "accepted"
    # A stale write, then a genuine conflict — the two non-advancing rows
    # of the conflict table (docs/decisions/ADR-003.md), both surfaced by
    # advanced=false.
    stale_op = _transition_op(entity_id, "CREATED", "IN_TRANSIT", 1)
    stale = await _push(client, anm_auth_headers, "d-anm-stale", stale_op)
    assert stale["status"] == "accepted_stale"
    conflict_op = _transition_op(entity_id, "CREATED", "IN_TRANSIT", 5)
    conflict = await _push(client, anm_auth_headers, "d-anm-conflict", conflict_op)
    assert conflict["status"] == "conflict"

    resp = await client.get(f"/referrals/{entity_id}/timeline", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()

    assert body["referral_id"] == str(entity_id)
    assert body["current_state"] == "IN_TRANSIT"
    assert body["replayed_state"] == "IN_TRANSIT"
    assert [e["op_id"] for e in body["events"]] == [
        create["op_id"],
        accepted["op_id"],
        stale["op_id"],
        conflict["op_id"],
    ]
    assert [e["seq"] for e in body["events"]] == sorted(e["seq"] for e in body["events"])
    assert [e["advanced"] for e in body["events"]] == [True, True, False, False]


async def test_timeline_404s_for_asha_a_against_village_b_referral(
    client, auth_headers, asha_b_auth_headers, patient_id
):
    entity_id = uuid.uuid4()
    result = await _push(
        client, asha_b_auth_headers, "d-asha-b", _create_op(entity_id, patient_id, 1)
    )
    assert result["status"] == "accepted"

    resp = await client.get(f"/referrals/{entity_id}/timeline", headers=auth_headers)
    assert resp.status_code == 404


async def test_timeline_404s_for_an_unknown_referral_id(client, auth_headers):
    resp = await client.get(f"/referrals/{uuid.uuid4()}/timeline", headers=auth_headers)
    assert resp.status_code == 404


async def test_timeline_request_is_recorded_in_request_timing(client, auth_headers, patient_id):
    entity_id = uuid.uuid4()
    await _push(client, auth_headers, "d-asha", _create_op(entity_id, patient_id, 1))

    resp = await client.get(f"/referrals/{entity_id}/timeline", headers=auth_headers)
    assert resp.status_code == 200

    async with async_session_factory() as session:
        result = await session.execute(
            text(
                """SELECT status, duration_ms FROM request_timing
                   WHERE endpoint = :endpoint
                   ORDER BY id DESC LIMIT 1"""
            ),
            {"endpoint": f"/referrals/{entity_id}/timeline"},
        )
        row = result.mappings().one()

    assert row["status"] == 200
    assert row["duration_ms"] is not None
