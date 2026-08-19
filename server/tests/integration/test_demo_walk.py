"""Mirrors scripts/demo_walk.py's walk through the real /sync/push, so its
exact shape — and its idempotency on a second run — is pinned in CI.
docs/PHASE3_PLAN.md D12, docs/decisions/ADR-008.md.

scripts/demo_walk.py itself is not imported here: it is dev tooling that
needs a live server over httpx and is deliberately outside testpaths
(docs/PHASE3_PLAN.md trap 10 — it must not be pytest-collected either).
This test reimplements the same eight-step table against the ASGI test
client instead.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import text

from app.db import async_session_factory
from app.seed import _stable_id as _seed_stable_id

DEVICE_TIME = datetime(2026, 8, 19, 9, 0, tzinfo=UTC).isoformat()

# Same table as scripts/demo_walk.py's STEPS — see that file for why each
# expected status follows from the conflict table (docs/decisions/ADR-003.md).
STEPS = [
    ("asha_a", "demo-phone-a", None, "CREATED", 10, "accepted"),
    ("asha_a", "demo-phone-a", "CREATED", "IN_TRANSIT", 11, "accepted"),
    ("asha_a", "demo-phone-c", "CREATED", "IN_TRANSIT", 5, "accepted_stale"),
    ("anm1", "demo-phone-b", "CREATED", "IN_TRANSIT", 20, "conflict"),
    ("mo1", "demo-phone-d", "IN_TRANSIT", "ARRIVED", 30, "accepted"),
    ("mo1", "demo-phone-d", "ARRIVED", "TREATED", 31, "accepted"),
    ("mo1", "demo-phone-d", "TREATED", "BACK_REFERRED", 32, "accepted"),
    ("asha_a", "demo-phone-a", "BACK_REFERRED", "CLOSED", 33, "accepted"),
]


def _op(entity_id, op_id, from_state, to_state, lamport, patient_id):
    if from_state is None:
        operation, payload = (
            "create_referral",
            {
                "patient_id": str(patient_id),
                "reason": "fever, referred for evaluation",
                "priority": "normal",
            },
        )
    else:
        operation, payload = "transition", {"from_state": from_state, "to_state": to_state}
    return {
        "op_id": str(op_id),
        "entity": "referral",
        "entity_id": str(entity_id),
        "operation": operation,
        "payload": payload,
        "lamport": lamport,
        "device_time": DEVICE_TIME,
    }


async def _login(client, username):
    resp = await client.post("/auth/login", json={"username": username, "password": "dev"})
    return {"authorization": f"Bearer {resp.json()['access_token']}"}


async def _run_walk(client, entity_id, op_ids, patient_id):
    tokens = {}
    statuses = []
    for (user, device, frm, to, lamport, _expected), op_id in zip(STEPS, op_ids, strict=True):
        if user not in tokens:
            tokens[user] = await _login(client, user)
        op = _op(entity_id, op_id, frm, to, lamport, patient_id)
        resp = await client.post(
            "/sync/push", json={"device_id": device, "ops": [op]}, headers=tokens[user]
        )
        assert resp.status_code == 200
        statuses.append(resp.json()["results"][0]["status"])
    return statuses


async def _counts(entity_id):
    async with async_session_factory() as session:
        events = (
            await session.execute(
                text("SELECT COUNT(*) FROM referral_event WHERE referral_id=:id"),
                {"id": entity_id},
            )
        ).scalar_one()
        conflicts = (
            await session.execute(
                text("SELECT COUNT(*) FROM sync_conflict WHERE entity_id=:id"), {"id": entity_id}
            )
        ).scalar_one()
        return events, conflicts


async def test_demo_walk_shape_is_pinned_and_idempotent_on_a_second_run(client):
    entity_id = uuid.uuid4()
    op_ids = [uuid.uuid4() for _ in STEPS]
    patient_id = _seed_stable_id("patient:Lakshmi Devi")
    expected = [status for *_, status in STEPS]

    first = await _run_walk(client, entity_id, op_ids, patient_id)
    assert first == expected
    assert await _counts(entity_id) == (8, 1)

    async with async_session_factory() as session:
        conflict_row = (
            await session.execute(
                text("SELECT winning_op_id, losing_op_id FROM sync_conflict WHERE entity_id=:id"),
                {"id": entity_id},
            )
        ).one()
    assert str(conflict_row.winning_op_id) == str(op_ids[1])  # step 2, accepted
    assert str(conflict_row.losing_op_id) == str(op_ids[3])  # step 4, the conflict

    # Second run, identical op_ids: I1's replay path returns each stored
    # result and applies nothing — this is a proof of I1, not a guard.
    second = await _run_walk(client, entity_id, op_ids, patient_id)
    assert second == expected
    assert await _counts(entity_id) == (8, 1)
