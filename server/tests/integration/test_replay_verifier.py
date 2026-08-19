"""app/verify_replay.py — I3 checked over every referral in the database,
not a sampled subset. docs/decisions/ADR-007.md, docs/PHASE3_PLAN.md.
"""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from app.db import async_session_factory
from app.verify_replay import verify_all

DEVICE_TIME = datetime(2026, 8, 10, 9, 0, tzinfo=UTC)


@pytest.fixture
async def patient_id():
    pid = uuid.uuid4()
    async with async_session_factory() as session, session.begin():
        await session.execute(
            text(
                """INSERT INTO patient (id, name, normalized_name, created_at)
                   VALUES (:id, 'Verifier Test Patient', 'verifier test patient', :now)"""
            ),
            {"id": pid, "now": DEVICE_TIME},
        )
    return pid


async def test_verify_all_reports_ok_for_the_whole_database(client, auth_headers):
    # No corruption anywhere at this point — the seeded district plus
    # whatever earlier tests in this session wrote, all real writes
    # through the real engine, must replay clean.
    report = await verify_all()
    assert report.ok, report.mismatches
    assert report.referrals_checked > 0
    assert report.events_checked > 0


async def test_verify_all_detects_a_corrupted_cache(client, auth_headers, patient_id):
    entity_id = uuid.uuid4()
    resp = await client.post(
        "/sync/push",
        json={
            "device_id": "d-verify",
            "ops": [
                {
                    "op_id": str(uuid.uuid4()),
                    "entity": "referral",
                    "entity_id": str(entity_id),
                    "operation": "create_referral",
                    "payload": {
                        "patient_id": str(patient_id),
                        "reason": "fever",
                        "priority": "normal",
                    },
                    "lamport": 1,
                    "device_time": DEVICE_TIME.isoformat(),
                }
            ],
        },
        headers=auth_headers,
    )
    assert resp.json()["results"][0]["status"] == "accepted"

    # Corrupt the cache directly, bypassing the event log entirely — the
    # exact condition I3 forbids. A referral this test created itself,
    # never a seeded one (docs/PHASE3_PLAN.md trap 6) — corrupting a
    # seeded referral would poison test_org_scoping.py's assertions.
    async with async_session_factory() as session, session.begin():
        await session.execute(
            text("UPDATE referral SET current_state = 'IN_TRANSIT' WHERE id=:id"),
            {"id": entity_id},
        )

    try:
        report = await verify_all()
        mismatch = next(m for m in report.mismatches if m.referral_id == entity_id)
        assert mismatch.cached_state == "IN_TRANSIT"
        assert mismatch.replayed_state == "CREATED"
        assert mismatch.reason == "cache_diverged_from_log"
    finally:
        # Restored so this poisoned row can't fail the "reports ok for the
        # whole database" test if it runs afterwards in the same session.
        async with async_session_factory() as session, session.begin():
            await session.execute(
                text("UPDATE referral SET current_state = 'CREATED' WHERE id=:id"),
                {"id": entity_id},
            )


async def test_verify_all_reports_a_zero_event_referral_as_a_violation(
    client, auth_headers, patient_id
):
    entity_id = uuid.uuid4()
    # Written directly, bypassing app/sync/push.py entirely, so the
    # referral row has no matching referral_event row at all — the one
    # case replay_state([]) cannot distinguish from "nothing to check".
    async with async_session_factory() as session, session.begin():
        asha = (
            await session.execute(
                text("SELECT id, org_unit_id FROM app_user WHERE name = 'asha_a'")
            )
        ).one()
        await session.execute(
            text(
                """INSERT INTO referral
                     (id, patient_id, origin_user_id, origin_org_id, target_org_id,
                      reason, priority, current_state, state_entered_at,
                      sla_profile_id, created_device_time, created_server_time)
                   VALUES
                     (:id, :patient_id, :user_id, :org_id, :org_id,
                      'fever', 'normal', 'CREATED', :now, NULL, :now, :now)"""
            ),
            {
                "id": entity_id,
                "patient_id": patient_id,
                "user_id": asha.id,
                "org_id": asha.org_unit_id,
                "now": DEVICE_TIME,
            },
        )

    try:
        report = await verify_all()
        mismatch = next(m for m in report.mismatches if m.referral_id == entity_id)
        assert mismatch.reason == "zero_events"
        assert mismatch.replayed_state is None
        assert mismatch.cached_state == "CREATED"
    finally:
        async with async_session_factory() as session, session.begin():
            await session.execute(text("DELETE FROM referral WHERE id=:id"), {"id": entity_id})
