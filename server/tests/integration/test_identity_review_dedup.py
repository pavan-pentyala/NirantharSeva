"""uq_identity_review_open (migration 0007) — I5's sibling for identity.
docs/PHASE6_PLAN.md P6.2 exit criteria: "Two pushes producing the same
pending pair -> exactly one identity_review row, and the test asserts
this is uq_identity_review_open's doing: delete any Python duplicate-check
and it must still pass."

app/sync/push.py's own call site can never exercise this collision
naturally — every new_patient_id it passes to `_insert_identity_review`
is freshly INSERTed a few lines above, so no two calls from that call
site ever share a pair (see that function's docstring). This test proves
the SQL mechanism directly, the same shape
tests/integration/test_escalation_sweep.py uses for uq_escalation_open:
call the insert function itself twice with the same ids.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import text

from app.db import async_session_factory
from app.seed import _stable_id as _seed_stable_id
from app.sync.push import _insert_identity_review

_NOW = datetime(2026, 8, 21, 9, 0, tzinfo=UTC)


async def _insert_bare_patient(name: str) -> uuid.UUID:
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
                "village_org_id": _seed_stable_id("org:Village A"),
                "now": _NOW,
            },
        )
    return patient_id


async def test_two_inserts_for_the_same_pending_pair_produce_exactly_one_row():
    new_patient_id = await _insert_bare_patient("Dedup Test Provisional Person")
    candidate_id = await _insert_bare_patient("Dedup Test Existing Person")

    for _ in range(2):
        async with async_session_factory() as s, s.begin():
            await _insert_identity_review(
                s,
                new_patient_id=new_patient_id,
                candidate_patient_id=candidate_id,
                score=85.0,
                method="review_queue",
                now=_NOW,
                run_id=None,
            )

    async with async_session_factory() as s:
        result = await s.execute(
            text(
                """SELECT id FROM identity_review
                   WHERE new_patient_id=:new_patient_id AND candidate_patient_id=:candidate_id"""
            ),
            {"new_patient_id": new_patient_id, "candidate_id": candidate_id},
        )
        rows = result.all()

    assert len(rows) == 1
