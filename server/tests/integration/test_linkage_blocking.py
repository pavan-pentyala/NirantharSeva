"""app/linkage/blocking.py — docs/decisions/ADR-014.md's predicate.
docs/PHASE6_PLAN.md P6.1's "What P6.1 must prove" table:
- Blocking never returns a candidate from another village (the handoff's
  fourth unforgivable thing, made executable rather than a comment).
- A phone-less patient is still blockable.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import text

from app.db import async_session_factory
from app.linkage.blocking import block
from app.seed import _stable_id as _seed_stable_id

VILLAGE_A = _seed_stable_id("org:Village A")
VILLAGE_B = _seed_stable_id("org:Village B")
_NOW = datetime(2026, 8, 21, 9, 0, tzinfo=UTC)


async def _insert_patient(name: str, phone: str | None, village_org_id: uuid.UUID) -> uuid.UUID:
    patient_id = uuid.uuid4()
    async with async_session_factory() as s, s.begin():
        await s.execute(
            text(
                """INSERT INTO patient
                     (id, name, normalized_name, phone, village_org_id, created_at)
                   VALUES (:id, :name, :norm, :phone, :village_org_id, :now)"""
            ),
            {
                "id": patient_id,
                "name": name,
                "norm": name.strip().lower(),
                "phone": phone,
                "village_org_id": village_org_id,
                "now": _NOW,
            },
        )
    return patient_id


async def test_never_returns_a_candidate_from_another_village():
    same_phone = "9899999001"
    village_a_id = await _insert_patient("Test Blocking Alpha", same_phone, VILLAGE_A)
    village_b_id = await _insert_patient("Test Blocking Alpha", same_phone, VILLAGE_B)

    async with async_session_factory() as s:
        candidates = await block(s, village_org_id=VILLAGE_A, phone=same_phone)

    ids = {c.id for c in candidates}
    assert village_a_id in ids
    assert village_b_id not in ids


async def test_a_phone_less_patient_is_still_blockable():
    """ADR-014: a null phone on either side never excludes a candidate —
    the naive `phone[:4]` guard would make this patient permanently
    unmatchable."""
    patient_id = await _insert_patient("Test Blocking NoPhone", None, VILLAGE_A)

    async with async_session_factory() as s:
        candidates = await block(s, village_org_id=VILLAGE_A, phone="9899999002")

    assert patient_id in {c.id for c in candidates}


async def test_a_query_with_no_phone_still_finds_a_candidate_that_has_one():
    """The symmetric case: the incoming query itself has no phone."""
    patient_id = await _insert_patient("Test Blocking QueryNoPhone", "9899999003", VILLAGE_A)

    async with async_session_factory() as s:
        candidates = await block(s, village_org_id=VILLAGE_A, phone=None)

    assert patient_id in {c.id for c in candidates}


async def test_disagreeing_phone_prefixes_exclude_the_candidate_when_both_present():
    """ADR-014: when both records carry a phone, a disagreeing prefix DOES
    remove the candidate — phone only narrows, but it narrows for real."""
    patient_id = await _insert_patient("Test Blocking PhoneMismatch", "9810000001", VILLAGE_A)

    async with async_session_factory() as s:
        candidates = await block(s, village_org_id=VILLAGE_A, phone="9920000001")

    assert patient_id not in {c.id for c in candidates}


async def test_agreeing_phone_prefix_includes_the_candidate():
    patient_id = await _insert_patient("Test Blocking PhoneMatch", "9810000002", VILLAGE_A)

    async with async_session_factory() as s:
        candidates = await block(s, village_org_id=VILLAGE_A, phone="9810000099")

    assert patient_id in {c.id for c in candidates}
