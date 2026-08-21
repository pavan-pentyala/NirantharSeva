"""The identity-resolution pipeline. docs/IMPLEMENTATION_PLAN.md §10.1.

docs/PHASE6_PLAN.md's "Contracts fixed now" corrects two errors in that
section's snippet: the blocking key crashes on a null phone (fixed by
routing through app/linkage/blocking.py, ADR-014), and the three-field
Resolution it shows cannot express the review_queue case, which needs to
name a new patient AND the candidate that new patient might duplicate —
Resolution below carries both.

Thresholds (Settings.identity_auto_accept / identity_review_floor) are
compared here, in Python, never pushed into a query — see scripts on
observation 37 in docs/PHASE2_OBSERVATIONS.md for what happens to a float
threshold that migrates into SQL.

Not wired into app/sync/push.py in P6.1 (docs/PHASE6_PLAN.md build order,
P6.2 item 4) — that is the one call site ADR-009 named, and it stays
untouched until migration 0007 exists.
"""

import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.linkage.blocking import block
from app.linkage.normalize import normalize
from app.linkage.scoring import score


@dataclass(frozen=True)
class Resolution:
    patient_id: uuid.UUID | None  # the patient to USE; None => caller creates one
    method: Literal["exact", "alias", "fuzzy_auto", "review_queue", "new_patient"]
    score: float
    candidate_id: uuid.UUID | None = None  # set only for review_queue: who it might be


async def _exact_match(
    session: AsyncSession, norm: str, village_org_id: uuid.UUID
) -> uuid.UUID | None:
    result = await session.execute(
        text(
            """SELECT id FROM patient
               WHERE normalized_name = :norm AND village_org_id = :village_org_id
               ORDER BY created_at ASC LIMIT 1"""
        ),
        {"norm": norm, "village_org_id": village_org_id},
    )
    row = result.first()
    return row.id if row is not None else None


async def _alias_lookup(
    session: AsyncSession, norm: str, village_org_id: uuid.UUID
) -> uuid.UUID | None:
    """patient_alias has no normalized_alias column until migration 0007
    (P6.2) — normalize()d comparison happens in Python here instead of
    anticipating that column. The table is empty until P6.2 wires a write
    path to it (docs/PHASE6_PLAN.md "Traps"), so this is a cheap no-op scan
    today and becomes a real lookup once P6.2 starts writing aliases; P6.2
    may replace this loop with a direct SQL comparison against the new
    column as an optimisation, but is not required to."""
    result = await session.execute(
        text(
            """SELECT pa.raw_name, pa.patient_id FROM patient_alias pa
               JOIN patient p ON p.id = pa.patient_id
               WHERE p.village_org_id = :village_org_id"""
        ),
        {"village_org_id": village_org_id},
    )
    for row in result.all():
        if normalize(row.raw_name) == norm:
            return row.patient_id
    return None


async def resolve(
    session: AsyncSession,
    settings: Settings,
    *,
    raw_name: str,
    phone: str | None,
    village_org_id: uuid.UUID,
) -> Resolution:
    norm = normalize(raw_name)

    exact_hit = await _exact_match(session, norm, village_org_id)
    if exact_hit is not None:
        return Resolution(patient_id=exact_hit, method="exact", score=100.0)

    alias_hit = await _alias_lookup(session, norm, village_org_id)
    if alias_hit is not None:
        return Resolution(patient_id=alias_hit, method="alias", score=100.0)

    candidates = await block(session, village_org_id=village_org_id, phone=phone)
    scored = [(c, score(norm, c.normalized_name)) for c in candidates]
    best, best_score = max(scored, key=lambda pair: pair[1], default=(None, 0.0))

    if best is not None and best_score >= settings.identity_auto_accept:
        return Resolution(patient_id=best.id, method="fuzzy_auto", score=best_score)
    if best is not None and best_score >= settings.identity_review_floor:
        return Resolution(
            patient_id=None, method="review_queue", score=best_score, candidate_id=best.id
        )
    return Resolution(patient_id=None, method="new_patient", score=best_score)
