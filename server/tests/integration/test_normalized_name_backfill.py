"""Migration 0007's normalized_name backfill. docs/PHASE6_PLAN.md P6.2
exit criteria: "A pre-existing patient row whose normalized_name was
written by the old rule is matched by the new exact step — a test that
fails without the backfill." ADR-009 wrote normalized_name as
`name.strip().lower()`; app/linkage/normalize.py's normalize() differs on
anything NFKD-decomposable, such as a diacritic.

This test simulates a row that predates migration 0007 — a normalized_name
column value written by the old rule, the exact shape every existing row
had immediately before that migration ran — then applies the same one-line
UPDATE migration 0007's upgrade() applies to every row, and proves
resolve()'s exact-match step only finds the row afterward, not before.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import text

from app.config import Settings
from app.db import async_session_factory
from app.linkage.normalize import normalize
from app.linkage.pipeline import resolve
from app.seed import _stable_id as _seed_stable_id

VILLAGE_A = _seed_stable_id("org:Village A")
_NOW = datetime(2026, 8, 21, 9, 0, tzinfo=UTC)
_SETTINGS = Settings(identity_auto_accept=92.0, identity_review_floor=80.0)

# The old rule (name.strip().lower()) and the new normalize() (NFKD +
# diacritic strip) genuinely diverge on this name — the old rule leaves
# the diaeresis in place, normalize() strips it.
_RAW_NAME = "Zoë Backfill Test Person"
_OLD_RULE_NORMALIZED = _RAW_NAME.strip().lower()


async def test_exact_match_finds_the_row_only_after_the_backfill_update():
    patient_id = uuid.uuid4()
    async with async_session_factory() as s, s.begin():
        await s.execute(
            text(
                """INSERT INTO patient (id, name, normalized_name, village_org_id, created_at)
                   VALUES (:id, :name, :norm, :village_org_id, :now)"""
            ),
            {
                "id": patient_id,
                "name": _RAW_NAME,
                "norm": _OLD_RULE_NORMALIZED,
                "village_org_id": VILLAGE_A,
                "now": _NOW,
            },
        )

    async with async_session_factory() as s:
        before = await resolve(
            s, _SETTINGS, raw_name=_RAW_NAME, phone=None, village_org_id=VILLAGE_A
        )
    # Not found via the exact step — the stored value still has the
    # diacritic the query's normalize() strips. (It happens to still be
    # found via fuzzy_auto here, since a one-diacritic difference scores
    # very high — a coincidence of this specific example, not a guarantee
    # exact match can rely on.)
    assert before.method != "exact"

    async with async_session_factory() as s, s.begin():
        # The same UPDATE alembic/versions/0007_identity_resolution.py's
        # upgrade() runs for every pre-existing row.
        await s.execute(
            text("UPDATE patient SET normalized_name = :n WHERE id = :id"),
            {"n": normalize(_RAW_NAME), "id": patient_id},
        )

    async with async_session_factory() as s:
        after = await resolve(
            s, _SETTINGS, raw_name=_RAW_NAME, phone=None, village_org_id=VILLAGE_A
        )
    assert after.method == "exact"
    assert after.patient_id == patient_id
    assert after.score == 100.0
