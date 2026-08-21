"""ADR-009's one wired call site, end to end through the real /sync/push —
docs/PHASE6_PLAN.md P6.2 exit criteria, the three threshold bands. Runs
against the real IDENTITY_AUTO_ACCEPT=92.0 / IDENTITY_REVIEW_FLOOR=80.0
(docker-compose.yml's defaults), so every name pair below is a REAL
rapidfuzz score in the band its test name claims, not an adjusted
Settings object — verified once, by hand, against app/linkage/scoring.py
directly, not asserted here (that would test rapidfuzz, not this wiring).

Every existing/query pair here shares no word with app.seed's fixture
("Lakshmi Devi", "Ramesh Kumar" — both in Village A) or with any other
pair in this file, for the reason observation 44
(docs/PHASE2_OBSERVATIONS.md) documents: token_set_ratio scores on shared
words regardless of which test wrote them, and this file's tests all run
against the same live Village A with no per-test rollback.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import text

from app.db import async_session_factory
from app.seed import _stable_id as _seed_stable_id

VILLAGE_A = _seed_stable_id("org:Village A")
DEVICE_TIME = datetime(2026, 8, 21, 9, 0, tzinfo=UTC).isoformat()


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


async def _insert_existing_patient(name: str) -> uuid.UUID:
    patient_id = uuid.uuid4()
    async with async_session_factory() as s, s.begin():
        await s.execute(
            text(
                """INSERT INTO patient (id, name, normalized_name, village_org_id, created_at)
                   VALUES (:id, :name, :norm, :village_org_id, :now)"""
            ),
            {
                "id": patient_id,
                "name": name,
                "norm": name.strip().lower(),
                "village_org_id": VILLAGE_A,
                "now": datetime(2026, 1, 1, tzinfo=UTC),
            },
        )
    return patient_id


async def _patient_id_for(entity_id) -> uuid.UUID:
    async with async_session_factory() as session:
        result = await session.execute(
            text("SELECT patient_id FROM referral WHERE id=:id"), {"id": entity_id}
        )
        return result.scalar_one()


async def _aliases_for(patient_id: uuid.UUID) -> list:
    async with async_session_factory() as session:
        result = await session.execute(
            text(
                "SELECT raw_name, match_method, match_score FROM patient_alias WHERE patient_id=:id"
            ),
            {"id": patient_id},
        )
        return result.all()


async def _pending_reviews_for(new_patient_id: uuid.UUID) -> list:
    async with async_session_factory() as session:
        result = await session.execute(
            text(
                """SELECT candidate_patient_id, status FROM identity_review
                   WHERE new_patient_id=:id"""
            ),
            {"id": new_patient_id},
        )
        return result.all()


# score(normalize(...), normalize(...)) == 98.25 — well above AUTO_ACCEPT.
async def test_score_above_auto_accept_reuses_existing_patient_and_writes_an_alias(
    client, auth_headers
):
    existing_id = await _insert_existing_patient("Push Test Ekaterina Yusupova")
    entity_id = uuid.uuid4()

    await _push_accepted(
        client,
        auth_headers,
        "d-asha-a-auto",
        _create_op(entity_id, "Push Test Ekaterina Yusupovah", 1),
    )

    assert await _patient_id_for(entity_id) == existing_id
    aliases = await _aliases_for(existing_id)
    assert len(aliases) == 1
    assert aliases[0].raw_name == "Push Test Ekaterina Yusupovah"
    assert aliases[0].match_method == "fuzzy_auto"
    assert await _pending_reviews_for(existing_id) == []


# score(normalize(...), normalize(...)) == 81.82 — between REVIEW_FLOOR
# and AUTO_ACCEPT.
async def test_score_in_review_band_creates_a_provisional_patient_and_queues_one_review(
    client, auth_headers
):
    existing_id = await _insert_existing_patient("Push Test Kailash Joshi")
    entity_id = uuid.uuid4()

    await _push_accepted(
        client, auth_headers, "d-asha-a-review", _create_op(entity_id, "Push Test Kamlesh Jha", 1)
    )

    new_patient_id = await _patient_id_for(entity_id)
    assert new_patient_id != existing_id

    reviews = await _pending_reviews_for(new_patient_id)
    assert len(reviews) == 1
    assert reviews[0].candidate_patient_id == existing_id
    assert reviews[0].status == "pending"
    assert await _aliases_for(existing_id) == []


# score(normalize(...), normalize(...)) == 77.27 — below REVIEW_FLOOR.
async def test_score_below_review_floor_creates_a_provisional_patient_with_no_review(
    client, auth_headers
):
    existing_id = await _insert_existing_patient("Push Test Chetan Verma")
    entity_id = uuid.uuid4()

    await _push_accepted(
        client, auth_headers, "d-asha-a-new", _create_op(entity_id, "Push Test Rohan Sharma", 1)
    )

    new_patient_id = await _patient_id_for(entity_id)
    assert new_patient_id != existing_id
    assert await _pending_reviews_for(new_patient_id) == []
