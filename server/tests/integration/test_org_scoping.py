"""Org-subtree visibility (read side, D5/ADR-005) and write-path lockdown
(D6/ADR-006). Plan §6.5's fourth exit criterion, completed in P2.2.
"""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from app.db import async_session_factory
from app.seed import REFERRALS, _stable_id

DEVICE_TIME = datetime(2026, 8, 10, 9, 0, tzinfo=UTC).isoformat()


@pytest.fixture
async def patient_id():
    pid = uuid.uuid4()
    async with async_session_factory() as session, session.begin():
        await session.execute(
            text(
                """INSERT INTO patient (id, name, normalized_name, created_at)
                   VALUES (:id, 'Scoping Test Patient', 'scoping test patient', :now)"""
            ),
            {"id": pid, "now": datetime(2026, 8, 10, 9, 0, tzinfo=UTC)},
        )
    return pid


def _create_op(entity_id, patient, lamport, **extra_payload):
    payload = {"patient_id": str(patient), "reason": "fever", "priority": "normal"}
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


async def _event_count(entity_id):
    async with async_session_factory() as session:
        result = await session.execute(
            text("SELECT COUNT(*) FROM referral_event WHERE referral_id=:id"), {"id": entity_id}
        )
        return result.scalar_one()


async def test_asha_a_gets_404_on_village_b_referral(
    client, auth_headers, asha_b_auth_headers, patient_id
):
    entity_id = uuid.uuid4()
    result = await _push(
        client, asha_b_auth_headers, "d-asha-b", _create_op(entity_id, patient_id, 1)
    )
    assert result["status"] == "accepted"

    resp = await client.get(f"/referrals/{entity_id}", headers=auth_headers)
    assert resp.status_code == 404


async def test_asha_a_sees_her_own_referral(client, auth_headers, patient_id):
    entity_id = uuid.uuid4()
    result = await _push(client, auth_headers, "d-asha-a", _create_op(entity_id, patient_id, 1))
    assert result["status"] == "accepted"

    resp = await client.get(f"/referrals/{entity_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == str(entity_id)


async def test_village_b_referral_absent_from_asha_a_list(
    client, auth_headers, asha_b_auth_headers, patient_id
):
    entity_id = uuid.uuid4()
    await _push(client, asha_b_auth_headers, "d-asha-b", _create_op(entity_id, patient_id, 1))

    resp = await client.get("/referrals?limit=200", headers=auth_headers)
    assert resp.status_code == 200
    ids = {r["id"] for r in resp.json()["referrals"]}
    assert str(entity_id) not in ids


async def test_asha_a_cannot_see_village_b_events_via_pull_but_does_see_her_own(
    client, auth_headers, asha_b_auth_headers, patient_id
):
    """The single most load-bearing test in Phase 2 (ADR-005). Asserts both
    directions in the same test — asserting absence alone cannot tell
    'correctly scoped' from 'completely broken'."""
    village_a_entity = uuid.uuid4()
    village_b_entity = uuid.uuid4()
    await _push(client, auth_headers, "d-asha-a", _create_op(village_a_entity, patient_id, 1))
    await _push(
        client, asha_b_auth_headers, "d-asha-b", _create_op(village_b_entity, patient_id, 2)
    )

    resp = await client.get("/sync/pull?since=0&limit=1000", headers=auth_headers)
    assert resp.status_code == 200
    referral_ids = {e["entity_id"] for e in resp.json()["events"] if e["entity_type"] == "referral"}
    assert str(village_a_entity) in referral_ids
    assert str(village_b_entity) not in referral_ids


async def test_anm_sees_both_villages_mo_sees_everything_below(
    client, auth_headers, asha_b_auth_headers, anm_auth_headers, mo_auth_headers, patient_id
):
    village_a_entity = uuid.uuid4()
    village_b_entity = uuid.uuid4()
    await _push(client, auth_headers, "d-asha-a", _create_op(village_a_entity, patient_id, 1))
    await _push(
        client, asha_b_auth_headers, "d-asha-b", _create_op(village_b_entity, patient_id, 2)
    )

    for headers in (anm_auth_headers, mo_auth_headers):
        resp = await client.get("/referrals?limit=200", headers=headers)
        assert resp.status_code == 200
        ids = {r["id"] for r in resp.json()["referrals"]}
        assert str(village_a_entity) in ids
        assert str(village_b_entity) in ids


async def test_create_referral_payload_claiming_another_org_still_lands_in_actors_org(
    client, auth_headers, patient_id
):
    entity_id = uuid.uuid4()
    fake_org = str(uuid.uuid4())
    result = await _push(
        client,
        auth_headers,
        "d-asha-a",
        _create_op(
            entity_id, patient_id, 1, origin_org_id=fake_org, origin_user_id=str(uuid.uuid4())
        ),
    )
    assert result["status"] == "accepted"

    async with async_session_factory() as session:
        row = (
            await session.execute(
                text("SELECT origin_org_id FROM referral WHERE id=:id"), {"id": entity_id}
            )
        ).one()
    assert str(row.origin_org_id) != fake_org

    # Visible to asha_a via her own org — proving the real origin is her
    # org unit, not the one the payload claimed.
    resp = await client.get(f"/referrals/{entity_id}", headers=auth_headers)
    assert resp.status_code == 200


async def test_transition_outside_actors_subtree_is_rejected_and_writes_zero_events(
    client, auth_headers, asha_b_auth_headers, patient_id
):
    entity_id = uuid.uuid4()
    await _push(client, asha_b_auth_headers, "d-asha-b", _create_op(entity_id, patient_id, 1))

    result = await _push(
        client, auth_headers, "d-asha-a", _transition_op(entity_id, "CREATED", "IN_TRANSIT", 2)
    )
    assert result["status"] == "rejected"
    assert result["detail"]["reason"] == "outside_org_scope"
    assert await _event_count(entity_id) == 1  # only the create; nothing appended by the reject


async def test_create_referral_rejects_a_target_org_that_does_not_exist(
    client, auth_headers, patient_id
):
    """P7.3 B1 — a target that isn't a real org unit at all."""
    entity_id = uuid.uuid4()
    result = await _push(
        client,
        auth_headers,
        "d-asha-a",
        _create_op(entity_id, patient_id, 1, target_org_id=str(uuid.uuid4())),
    )
    assert result["status"] == "rejected"
    assert result["detail"]["reason"] == "invalid_target_org_id"
    assert await _event_count(entity_id) == 0


async def test_create_referral_rejects_a_lateral_target_org(client, auth_headers, patient_id):
    """P7.3 B1 — Village B is a real org unit but not an ancestor of
    asha_a's own org (Village A): referrals only travel up (ADR-005)."""
    async with async_session_factory() as session:
        village_b_id = (
            await session.execute(text("SELECT id FROM org_unit WHERE name = 'Village B'"))
        ).scalar_one()

    entity_id = uuid.uuid4()
    result = await _push(
        client,
        auth_headers,
        "d-asha-a",
        _create_op(entity_id, patient_id, 1, target_org_id=str(village_b_id)),
    )
    assert result["status"] == "rejected"
    assert result["detail"]["reason"] == "invalid_target_org_id"
    assert await _event_count(entity_id) == 0


async def test_create_referral_accepts_a_target_org_above_the_immediate_parent(
    client, auth_headers, patient_id
):
    """P7.3 B1/B2 — CHC Bishunpur is two levels above Village A (via
    Sub-centre Kotwali and PHC Ramnagar), not the immediate parent, and is
    still a valid target since the ancestor check walks the whole chain."""
    async with async_session_factory() as session:
        chc_id = (
            await session.execute(text("SELECT id FROM org_unit WHERE name = 'CHC Bishunpur'"))
        ).scalar_one()

    entity_id = uuid.uuid4()
    result = await _push(
        client,
        auth_headers,
        "d-asha-a",
        _create_op(entity_id, patient_id, 1, target_org_id=str(chc_id)),
    )
    assert result["status"] == "accepted"

    async with async_session_factory() as session:
        row = (
            await session.execute(
                text("SELECT target_org_id FROM referral WHERE id=:id"), {"id": entity_id}
            )
        ).one()
    assert row.target_org_id == chc_id


async def test_seeded_target_org_is_always_an_ancestor_of_origin_org(client):
    """Machine-checks ADR-005's assumption that origin-only filtering is
    correct for the D4 fixture: the target is always reached by ordinary
    subtree ascent from the origin. Scoped to the seeded referral ids only —
    other tests in this session create referrals with no target_org_id at
    all, which would otherwise be a false failure here, not a real one."""
    seeded_ids = [_stable_id(r["key"]) for r in REFERRALS]
    async with async_session_factory() as session:
        rows = (
            await session.execute(
                text("SELECT id, origin_org_id, target_org_id FROM referral WHERE id = ANY(:ids)"),
                {"ids": seeded_ids},
            )
        ).all()
        assert len(rows) == len(REFERRALS), "expected every seeded referral to exist"
        for row in rows:
            ancestors = {row.origin_org_id}
            current = row.origin_org_id
            while True:
                parent = (
                    await session.execute(
                        text("SELECT parent_id FROM org_unit WHERE id = :id"), {"id": current}
                    )
                ).scalar_one_or_none()
                if parent is None:
                    break
                ancestors.add(parent)
                current = parent
            assert row.target_org_id in ancestors, (
                f"referral {row.id}: target_org_id {row.target_org_id} is not an ancestor "
                f"of origin_org_id {row.origin_org_id}"
            )
