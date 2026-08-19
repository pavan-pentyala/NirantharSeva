"""A referral traversing CREATED -> ... -> CLOSED through the real API,
guard violations writing no event, and a conflict writing both rows without
moving current_state. Plan §6.5, docs/decisions/ADR-003.md.
"""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from app.db import async_session_factory

DEVICE_TIME = datetime(2026, 8, 10, 9, 0, tzinfo=UTC).isoformat()


@pytest.fixture
async def patient_id():
    """Referral.patient_id is a real FK (plan's own example, PHASE2_PLAN.md
    "Foreign keys are declared..."). Phase 2.2's seed script doesn't exist
    yet, so tests insert their own minimal patient row directly."""
    pid = uuid.uuid4()
    async with async_session_factory() as session, session.begin():
        await session.execute(
            text(
                """INSERT INTO patient (id, name, normalized_name, created_at)
                   VALUES (:id, 'Test Patient', 'test patient', :now)"""
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


async def _push_accepted(client, headers, device_id, op):
    result = await _push(client, headers, device_id, op)
    assert result["status"] == "accepted", result
    return result


async def _referral_row(entity_id):
    async with async_session_factory() as session:
        result = await session.execute(
            text("SELECT current_state FROM referral WHERE id=:id"), {"id": entity_id}
        )
        return result.first()


async def _event_count(entity_id):
    async with async_session_factory() as session:
        result = await session.execute(
            text("SELECT COUNT(*) FROM referral_event WHERE referral_id=:id"), {"id": entity_id}
        )
        return result.scalar_one()


async def test_referral_traverses_created_to_closed_with_the_right_role_at_each_step(
    client, auth_headers, mo_auth_headers, patient_id
):
    entity_id = uuid.uuid4()
    asha, mo = (client, auth_headers, "d-asha"), (client, mo_auth_headers, "d-mo")

    await _push_accepted(*asha, _create_op(entity_id, patient_id, 1))
    await _push_accepted(*asha, _transition_op(entity_id, "CREATED", "IN_TRANSIT", 2))
    await _push_accepted(*mo, _transition_op(entity_id, "IN_TRANSIT", "ARRIVED", 3))
    await _push_accepted(*mo, _transition_op(entity_id, "ARRIVED", "TREATED", 4))
    await _push_accepted(*mo, _transition_op(entity_id, "TREATED", "BACK_REFERRED", 5))
    await _push_accepted(*asha, _transition_op(entity_id, "BACK_REFERRED", "CLOSED", 6))

    row = await _referral_row(entity_id)
    assert row.current_state == "CLOSED"
    assert await _event_count(entity_id) == 6


async def test_anm_is_also_permitted_to_move_created_to_in_transit(
    client, anm_auth_headers, patient_id
):
    entity_id = uuid.uuid4()
    await _push(client, anm_auth_headers, "d-anm", _create_op(entity_id, patient_id, 1))
    result = await _push(
        client, anm_auth_headers, "d-anm", _transition_op(entity_id, "CREATED", "IN_TRANSIT", 2)
    )
    assert result["status"] == "accepted"


async def test_role_not_permitted_on_create_is_rejected_and_writes_no_event(
    client, mo_auth_headers, patient_id
):
    entity_id = uuid.uuid4()
    result = await _push(client, mo_auth_headers, "d-mo", _create_op(entity_id, patient_id, 1))
    assert result["status"] == "rejected"
    assert result["detail"]["reason"] == "role_not_permitted"
    assert await _event_count(entity_id) == 0
    assert await _referral_row(entity_id) is None


async def test_role_not_permitted_on_transition_is_rejected_and_writes_no_event(
    client, auth_headers, patient_id
):
    entity_id = uuid.uuid4()
    await _push(client, auth_headers, "d-asha", _create_op(entity_id, patient_id, 1))
    await _push_accepted(
        client, auth_headers, "d-asha", _transition_op(entity_id, "CREATED", "IN_TRANSIT", 2)
    )

    # ASHA may not write ARRIVED — that's MO's.
    result = await _push(
        client, auth_headers, "d-asha", _transition_op(entity_id, "IN_TRANSIT", "ARRIVED", 3)
    )
    assert result["status"] == "rejected"
    assert result["detail"]["reason"] == "role_not_permitted"
    assert await _event_count(entity_id) == 2


async def test_illegal_transition_is_rejected_and_writes_no_event(
    client, auth_headers, mo_auth_headers, patient_id
):
    entity_id = uuid.uuid4()
    await _push(client, auth_headers, "d-asha", _create_op(entity_id, patient_id, 1))

    # MO is permitted to write BACK_REFERRED in general (isolates this from
    # role_not_permitted) — but CREATED -> BACK_REFERRED is not a legal
    # transition.
    result = await _push(
        client, mo_auth_headers, "d-mo", _transition_op(entity_id, "CREATED", "BACK_REFERRED", 2)
    )
    assert result["status"] == "rejected"
    assert result["detail"]["reason"] == "illegal_transition"
    assert await _event_count(entity_id) == 1


async def test_transition_on_unknown_referral_is_rejected(client, auth_headers):
    entity_id = uuid.uuid4()  # never created
    result = await _push(
        client, auth_headers, "d-asha", _transition_op(entity_id, "CREATED", "IN_TRANSIT", 1)
    )
    assert result["status"] == "rejected"
    assert result["detail"]["reason"] == "unknown_referral"


async def test_create_referral_with_unknown_patient_is_rejected(client, auth_headers):
    entity_id = uuid.uuid4()
    result = await _push(client, auth_headers, "d-asha", _create_op(entity_id, uuid.uuid4(), 1))
    assert result["status"] == "rejected"
    assert result["detail"]["reason"] == "unknown_patient"


async def test_create_referral_twice_with_different_op_ids_is_rejected_already_exists(
    client, auth_headers, patient_id
):
    entity_id = uuid.uuid4()
    first = await _push(client, auth_headers, "d-asha", _create_op(entity_id, patient_id, 1))
    assert first["status"] == "accepted"

    second = await _push(client, auth_headers, "d-asha", _create_op(entity_id, patient_id, 2))
    assert second["status"] == "rejected"
    assert second["detail"]["reason"] == "already_exists"
    assert await _event_count(entity_id) == 1


async def test_conflict_writes_both_rows_and_leaves_current_state_untouched(
    client, auth_headers, anm_auth_headers, patient_id
):
    entity_id = uuid.uuid4()
    await _push(client, auth_headers, "d-asha", _create_op(entity_id, patient_id, 1))
    accepted = await _push(
        client, auth_headers, "d-asha", _transition_op(entity_id, "CREATED", "IN_TRANSIT", 2)
    )
    assert accepted["status"] == "accepted"

    # A different device, unaware of the transition above, independently
    # believed the referral was still CREATED — and its own lamport ran
    # ahead in the meantime (it did other work it hasn't synced yet). Same
    # target state, but the disagreement is not explained by lag.
    conflicting_op = _transition_op(entity_id, "CREATED", "IN_TRANSIT", 5)
    result = await _push(client, anm_auth_headers, "d-anm", conflicting_op)
    assert result["status"] == "conflict"

    row = await _referral_row(entity_id)
    assert row.current_state == "IN_TRANSIT"  # unchanged by the conflict
    assert await _event_count(entity_id) == 3  # create + accepted + conflicting, none deleted (I6)

    async with async_session_factory() as session:
        conflict_row = await session.execute(
            text("SELECT winning_op_id, losing_op_id FROM sync_conflict WHERE entity_id=:id"),
            {"id": entity_id},
        )
        c = conflict_row.one()
        assert str(c.winning_op_id) == accepted["op_id"]
        assert str(c.losing_op_id) == conflicting_op["op_id"]


async def test_i3_divergence_is_logged_not_asserted_and_the_request_still_succeeds(
    client, auth_headers, patient_id
):
    """Hardening (docs/decisions/ADR-007.md): a current_state cache that
    disagrees with the replayed event log used to crash the write path
    with a bare AssertionError — an unhandled 500 that rolled back a
    legitimate write because of pre-existing corruption. It is now a
    structured ERROR log, and the request completes normally. The real
    detector for this condition is app/verify_replay.py, not this path."""
    entity_id = uuid.uuid4()
    await _push_accepted(client, auth_headers, "d-asha", _create_op(entity_id, patient_id, 1))

    # Corrupt the cache directly, bypassing the event log entirely — the
    # exact condition I3 forbids.
    async with async_session_factory() as session, session.begin():
        await session.execute(
            text("UPDATE referral SET current_state = 'IN_TRANSIT' WHERE id=:id"),
            {"id": entity_id},
        )

    result = await _push(
        client, auth_headers, "d-asha", _transition_op(entity_id, "CREATED", "IN_TRANSIT", 2)
    )
    # The corrupted cache (IN_TRANSIT) disagrees with from_state (CREATED),
    # and the incoming lamport (2) beats the log's replayed lamport (1) —
    # row 5 of the conflict table, same as a genuine two-device conflict.
    # The point of this test is that this decision is reached at all,
    # rather than the request 500ing.
    assert result["status"] == "conflict"
