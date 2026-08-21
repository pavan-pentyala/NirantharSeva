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

Wired into app/sync/push.py's `_resolve_patient` in P6.2 — ADR-009's one
named call site. Every read here filters `merged_into_id IS NULL`
(migration 0007): an exact or alias hit on a row that has already been
merged into another would reuse a dead id instead of the canonical one,
silently undoing the merge the next time someone types the old spelling.
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
                     AND merged_into_id IS NULL
               ORDER BY created_at ASC LIMIT 1"""
        ),
        {"norm": norm, "village_org_id": village_org_id},
    )
    row = result.first()
    return row.id if row is not None else None


async def _alias_lookup(
    session: AsyncSession, norm: str, village_org_id: uuid.UUID
) -> uuid.UUID | None:
    """Direct comparison against `patient_alias.normalized_alias`
    (migration 0007) — populated by app/sync/push.py's `_resolve_patient`
    on every `fuzzy_auto` resolution and by a `merge` decision
    (app/api/identity.py). Before 0007, P6.1's draft of this function
    compared `normalize()`d `raw_name` in a Python loop, since the column
    didn't exist yet and the table was always empty; this is that draft's
    promised replacement, not a new decision."""
    result = await session.execute(
        text(
            """SELECT pa.patient_id FROM patient_alias pa
               JOIN patient p ON p.id = pa.patient_id
               WHERE pa.normalized_alias = :norm AND p.village_org_id = :village_org_id
                     AND p.merged_into_id IS NULL
               LIMIT 1"""
        ),
        {"norm": norm, "village_org_id": village_org_id},
    )
    row = result.first()
    return row.patient_id if row is not None else None


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
