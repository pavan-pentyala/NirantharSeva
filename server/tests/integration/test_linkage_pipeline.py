"""app/linkage/pipeline.py's resolve() — docs/IMPLEMENTATION_PLAN.md §10.1,
docs/PHASE6_PLAN.md's "Contracts fixed now" (the four-field Resolution).

Threshold boundary tests use a REAL computed score for each name pair
(via app.linkage.scoring.score, not a guessed number) and set
Settings.identity_auto_accept / identity_review_floor exactly at that
score — the "exactly AUTO_ACCEPT, exactly REVIEW_FLOOR" row of P6.1's
"What P6.1 must prove" table, made robust to any rapidfuzz version's exact
scoring behaviour.

Every patient name below is deliberately chosen to share no word with any
other name in this file, with app.seed's fixture ("Lakshmi Devi", "Ramesh
Kumar" — both in Village A), or with the next test's fixture: this module
runs its tests against the same live database with no per-test rollback
(the same pattern tests/integration/test_patient_resolution.py uses), and
token_set_ratio scores on shared WORDS, not on which test wrote them — a
shared "Devi" or "Kumar" is exactly the kind of accidental overlap that
would make one test's fixture a false-positive candidate for another's
query.

Not wired into app/sync/push.py in P6.1 — these tests call resolve()
directly, the same way scripts/e3_draft_sweep.py does.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import text

from app.config import Settings
from app.db import async_session_factory
from app.linkage.normalize import normalize
from app.linkage.pipeline import resolve
from app.linkage.scoring import score
from app.seed import _stable_id as _seed_stable_id

VILLAGE_A = _seed_stable_id("org:Village A")
_NOW = datetime(2026, 8, 21, 9, 0, tzinfo=UTC)


async def _insert_patient(name: str, phone: str | None = None) -> uuid.UUID:
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
                "norm": normalize(name),
                "phone": phone,
                "village_org_id": VILLAGE_A,
                "now": _NOW,
            },
        )
    return patient_id


async def _insert_alias(patient_id: uuid.UUID, raw_name: str) -> None:
    async with async_session_factory() as s, s.begin():
        await s.execute(
            text(
                """INSERT INTO patient_alias (id, patient_id, raw_name)
                   VALUES (:id, :patient_id, :raw_name)"""
            ),
            {"id": uuid.uuid4(), "patient_id": patient_id, "raw_name": raw_name},
        )


DEFAULT_SETTINGS = Settings(identity_auto_accept=92.0, identity_review_floor=80.0)


async def test_exact_match():
    existing_id = await _insert_patient("Zainab Bibi")

    async with async_session_factory() as s:
        resolution = await resolve(
            s, DEFAULT_SETTINGS, raw_name="Zainab Bibi", phone=None, village_org_id=VILLAGE_A
        )

    assert resolution.method == "exact"
    assert resolution.patient_id == existing_id
    assert resolution.score == 100.0
    assert resolution.candidate_id is None


async def test_alias_lookup():
    existing_id = await _insert_patient("Chandra Shekhar")
    await _insert_alias(existing_id, "Chandrashekhar")

    async with async_session_factory() as s:
        resolution = await resolve(
            s, DEFAULT_SETTINGS, raw_name="Chandrashekhar", phone=None, village_org_id=VILLAGE_A
        )

    assert resolution.method == "alias"
    assert resolution.patient_id == existing_id
    assert resolution.score == 100.0


async def test_new_patient_when_no_candidate_exists_at_all():
    async with async_session_factory() as s:
        resolution = await resolve(
            s,
            DEFAULT_SETTINGS,
            raw_name="Nobody Matches This Query String",
            phone=None,
            village_org_id=VILLAGE_A,
        )

    assert resolution.method == "new_patient"
    assert resolution.patient_id is None
    assert resolution.candidate_id is None


async def test_fuzzy_auto_at_exactly_the_auto_accept_boundary():
    """score >= AUTO_ACCEPT must auto-resolve, even when score == the
    threshold exactly (not strictly greater)."""
    existing_name = "Muhammad Ali"
    query_name = "Mohammed Ali"
    pair_score = score(normalize(existing_name), normalize(query_name))
    settings = Settings(identity_auto_accept=pair_score, identity_review_floor=50.0)
    existing_id = await _insert_patient(existing_name)

    async with async_session_factory() as s:
        resolution = await resolve(
            s, settings, raw_name=query_name, phone=None, village_org_id=VILLAGE_A
        )

    assert resolution.method == "fuzzy_auto"
    assert resolution.patient_id == existing_id
    assert resolution.score == pair_score
    assert resolution.candidate_id is None


async def test_review_queue_at_exactly_the_review_floor_boundary():
    """score >= REVIEW_FLOOR (but below AUTO_ACCEPT) must queue for
    review, even when score == the floor exactly."""
    existing_name = "Ibrahim Khan"
    query_name = "Ebrahim Khan"
    pair_score = score(normalize(existing_name), normalize(query_name))
    settings = Settings(identity_auto_accept=pair_score + 0.01, identity_review_floor=pair_score)
    existing_id = await _insert_patient(existing_name)

    async with async_session_factory() as s:
        resolution = await resolve(
            s, settings, raw_name=query_name, phone=None, village_org_id=VILLAGE_A
        )

    assert resolution.method == "review_queue"
    assert resolution.patient_id is None
    assert resolution.candidate_id == existing_id
    assert resolution.score == pair_score


async def test_new_patient_just_below_the_review_floor_boundary():
    existing_name = "Yusuf Sheikh"
    query_name = "Yousuf Sheikh"
    pair_score = score(normalize(existing_name), normalize(query_name))
    settings = Settings(identity_auto_accept=99.0, identity_review_floor=pair_score + 0.01)
    await _insert_patient(existing_name)

    async with async_session_factory() as s:
        resolution = await resolve(
            s, settings, raw_name=query_name, phone=None, village_org_id=VILLAGE_A
        )

    assert resolution.method == "new_patient"
    assert resolution.patient_id is None
    assert resolution.candidate_id is None
