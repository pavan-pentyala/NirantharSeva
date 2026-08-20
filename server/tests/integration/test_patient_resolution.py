"""D13/ADR-009: create_referral resolves the patient it names instead of
requiring one to already exist. Exact match on (normalized_name,
village_org_id) — the actor's own org unit, never a payload field, since
the design's Screen 2 shows "Village: yours" and never a picked village
(see app/sync/push.py's _resolve_patient). Not fuzzy, and this is the one
call site Phase 6 replaces — see the ADR for why.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import text

from app.db import async_session_factory

DEVICE_TIME = datetime(2026, 8, 20, 9, 0, tzinfo=UTC).isoformat()


def _create_op(entity_id, patient_name, lamport, **extra_payload):
    payload = {"patient_name": patient_name, "reason": "fever", "priority": "normal"}
    payload.update(extra_payload)
    return {
        "op_id": str(uuid.uuid4()),
        "entity": "referral",
        "entity_id": str(entity_id),
        "operation": "create_referral",
        "payload": payload,
        "lamport": lamport,
        "device_time": DEVICE_TIME,
    }


async def _push_accepted(client, headers, device_id, op):
    resp = await client.post(
        "/sync/push", json={"device_id": device_id, "ops": [op]}, headers=headers
    )
    result = resp.json()["results"][0]
    assert result["status"] == "accepted", result
    return result


async def _patient_id_for(entity_id):
    async with async_session_factory() as session:
        result = await session.execute(
            text("SELECT patient_id FROM referral WHERE id=:id"), {"id": entity_id}
        )
        return result.scalar_one()


async def _patient_count(name):
    async with async_session_factory() as session:
        result = await session.execute(
            text("SELECT COUNT(*) FROM patient WHERE name = :name"), {"name": name}
        )
        return result.scalar_one()


async def test_same_name_same_village_resolves_to_one_patient_row(client, auth_headers):
    name = "Test Dedup Patient Alpha"
    first_entity, second_entity = uuid.uuid4(), uuid.uuid4()

    await _push_accepted(client, auth_headers, "d-asha-a-1", _create_op(first_entity, name, 1))
    await _push_accepted(client, auth_headers, "d-asha-a-2", _create_op(second_entity, name, 2))

    first_patient = await _patient_id_for(first_entity)
    second_patient = await _patient_id_for(second_entity)
    assert first_patient == second_patient
    assert await _patient_count(name) == 1


async def test_same_name_different_village_resolves_to_two_patient_rows(
    client, auth_headers, asha_b_auth_headers
):
    name = "Test Dedup Patient Beta"
    village_a_entity, village_b_entity = uuid.uuid4(), uuid.uuid4()

    await _push_accepted(client, auth_headers, "d-asha-a", _create_op(village_a_entity, name, 1))
    await _push_accepted(
        client, asha_b_auth_headers, "d-asha-b", _create_op(village_b_entity, name, 2)
    )

    village_a_patient = await _patient_id_for(village_a_entity)
    village_b_patient = await _patient_id_for(village_b_entity)
    assert village_a_patient != village_b_patient
    assert await _patient_count(name) == 2


async def test_create_referral_with_age_sex_phone_persists_them_on_the_patient_row(
    client, auth_headers
):
    entity_id = uuid.uuid4()
    op = _create_op(entity_id, "Test New Patient Gamma", 1, age=29, sex="F", phone="9800099999")
    await _push_accepted(client, auth_headers, "d-asha-a", op)

    patient_id = await _patient_id_for(entity_id)
    async with async_session_factory() as session:
        row = await session.execute(
            text("SELECT age, sex, phone FROM patient WHERE id=:id"), {"id": patient_id}
        )
        r = row.one()
        assert r.age == 29
        assert r.sex == "F"
        assert r.phone == "9800099999"


async def test_patient_id_still_works_when_given_explicitly(client, auth_headers):
    """ADR-009 adds patient_name; it does not remove patient_id (see the
    ADR's "already has to name a patient" reasoning). Pre-Phase-4 callers
    naming an existing patient by id still work."""
    async with async_session_factory() as session, session.begin():
        pid = uuid.uuid4()
        await session.execute(
            text(
                """INSERT INTO patient (id, name, normalized_name, created_at)
                   VALUES (:id, 'Existing Patient', 'existing patient', :now)"""
            ),
            {"id": pid, "now": datetime(2026, 8, 20, 9, 0, tzinfo=UTC)},
        )

    entity_id = uuid.uuid4()
    op = {
        "op_id": str(uuid.uuid4()),
        "entity": "referral",
        "entity_id": str(entity_id),
        "operation": "create_referral",
        "payload": {"patient_id": str(pid), "reason": "fever", "priority": "normal"},
        "lamport": 1,
        "device_time": DEVICE_TIME,
    }
    await _push_accepted(client, auth_headers, "d-asha-a", op)
    assert await _patient_id_for(entity_id) == pid


async def test_create_referral_with_neither_patient_id_nor_patient_name_is_rejected(
    client, auth_headers
):
    entity_id = uuid.uuid4()
    op = {
        "op_id": str(uuid.uuid4()),
        "entity": "referral",
        "entity_id": str(entity_id),
        "operation": "create_referral",
        "payload": {"reason": "fever", "priority": "normal"},
        "lamport": 1,
        "device_time": DEVICE_TIME,
    }
    resp = await client.post(
        "/sync/push", json={"device_id": "d-asha-a", "ops": [op]}, headers=auth_headers
    )
    result = resp.json()["results"][0]
    assert result["status"] == "rejected"
    assert result["detail"]["reason"] == "patient_id or patient_name is required"
