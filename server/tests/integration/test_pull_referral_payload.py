"""D14/ADR-010: the referral branch's pulled payload carries a snapshot —
patient_name, age, sex, reason, priority, target_org_name — not just the
from_state/to_state/actor fields the sync engine itself needs. Joined
inside pull.py's own subquery, before LIMIT (see that module's docstring).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import text

from app.db import async_session_factory

DEVICE_TIME = datetime(2026, 8, 20, 9, 0, tzinfo=UTC).isoformat()


async def _cursor_before() -> int:
    async with async_session_factory() as session:
        result = await session.execute(text("SELECT COALESCE(MAX(seq), 0) FROM referral_event"))
        return result.scalar_one()


async def test_pulled_create_referral_event_payload_carries_the_referral_snapshot(
    client, auth_headers
):
    cursor_before = await _cursor_before()

    async with async_session_factory() as session:
        target_org = await session.execute(
            text("SELECT id FROM org_unit WHERE name = 'PHC Ramnagar'")
        )
        target_org_id = target_org.scalar_one()

    entity_id = uuid.uuid4()
    op = {
        "op_id": str(uuid.uuid4()),
        "entity": "referral",
        "entity_id": str(entity_id),
        "operation": "create_referral",
        "payload": {
            "patient_name": "Test Pull Payload Patient",
            "age": 34,
            "sex": "F",
            "reason": "fever, referred for evaluation",
            "priority": "urgent",
            "target_org_id": str(target_org_id),
        },
        "lamport": 1,
        "device_time": DEVICE_TIME,
    }
    resp = await client.post(
        "/sync/push", json={"device_id": "d-asha-a", "ops": [op]}, headers=auth_headers
    )
    assert resp.json()["results"][0]["status"] == "accepted"

    pull = await client.get(f"/sync/pull?since={cursor_before}&limit=1000", headers=auth_headers)
    events = pull.json()["events"]
    created = next(e for e in events if e["op_id"] == op["op_id"])

    assert created["payload"]["patient_name"] == "Test Pull Payload Patient"
    assert created["payload"]["age"] == 34
    assert created["payload"]["sex"] == "F"
    assert created["payload"]["reason"] == "fever, referred for evaluation"
    assert created["payload"]["priority"] == "urgent"
    assert created["payload"]["target_org_name"] == "PHC Ramnagar"


async def test_pulled_transition_event_payload_repeats_the_same_snapshot(client, auth_headers):
    cursor_before = await _cursor_before()

    entity_id = uuid.uuid4()
    create_op = {
        "op_id": str(uuid.uuid4()),
        "entity": "referral",
        "entity_id": str(entity_id),
        "operation": "create_referral",
        "payload": {
            # No word in common with the previous test's "Test Pull
            # Payload Patient" — sharing three of four words (as "... Two"
            # would) scores 100 via rapidfuzz's token_set_ratio (a subset
            # of tokens is a perfect match under that metric), which would
            # silently reuse that test's patient via fuzzy_auto instead of
            # creating this test's own, now that create_referral resolves
            # patients through the real fuzzy pipeline (P6.2). See
            # observation 44, docs/PHASE2_OBSERVATIONS.md.
            "patient_name": "Transition Snapshot Person",
            "reason": "cough",
            "priority": "routine",
        },
        "lamport": 1,
        "device_time": DEVICE_TIME,
    }
    transition_op = {
        "op_id": str(uuid.uuid4()),
        "entity": "referral",
        "entity_id": str(entity_id),
        "operation": "transition",
        "payload": {"from_state": "CREATED", "to_state": "IN_TRANSIT"},
        "lamport": 2,
        "device_time": DEVICE_TIME,
    }
    for op in (create_op, transition_op):
        resp = await client.post(
            "/sync/push", json={"device_id": "d-asha-a", "ops": [op]}, headers=auth_headers
        )
        assert resp.json()["results"][0]["status"] == "accepted"

    pull = await client.get(f"/sync/pull?since={cursor_before}&limit=1000", headers=auth_headers)
    events = pull.json()["events"]
    transitioned = next(e for e in events if e["op_id"] == transition_op["op_id"])

    # Append-only stream — a transition event repeats the patient snapshot
    # it never carried in its own payload (ADR-010's accepted cost).
    assert transitioned["payload"]["patient_name"] == "Transition Snapshot Person"
    assert transitioned["payload"]["reason"] == "cough"
    assert transitioned["payload"]["priority"] == "routine"
    assert transitioned["payload"]["age"] is None
    assert transitioned["payload"]["sex"] is None
    assert transitioned["payload"]["target_org_name"] is None
