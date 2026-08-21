"""The identity-review queue — ADR-013: plain REST, not a sync op. Screen 6
(docs/design_handoff_ui_screens). docs/PHASE6_PLAN.md P6.2, item 5.

Both endpoints are org-scoped via SUBTREE_CTE, rooted at the caller's own
org unit — the same predicate every other read/write in this project uses
(ADR-005). A pending `identity_review` row's `new_patient_id` and
`candidate_patient_id` always share one village_org_id (app/linkage/
blocking.py only ever offers a same-village candidate), so scoping on
`new_patient_id`'s village alone is sufficient and correct.

`decide` is idempotent by a conditional UPDATE, not a receipt (ADR-013):
`WHERE status = 'pending' AND ...scope...`. If it affects no row, the
pair was either already decided or is outside the caller's scope — both
collapse to a 404 if a same-scope re-check also finds nothing (the same
"404 not 403" rule ADR-005 already uses in app/api/referrals.py, so a
guess at another org's review id cannot be used to probe its existence),
and to the stored outcome with 200 otherwise (a double-tap on a tablet is
harmless).
"""

import uuid
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import CurrentUser, get_current_user
from app.api.scoping import SUBTREE_CTE, subtree_params
from app.clock import Clock, get_clock
from app.db import async_session_factory, get_session
from app.linkage.normalize import normalize
from app.schemas.identity import (
    IdentityReviewDecisionRequest,
    IdentityReviewDecisionResponse,
    IdentityReviewListResponse,
    IdentityReviewPatient,
    IdentityReviewRow,
)

router = APIRouter(prefix="/identity", tags=["identity"])

_LIST_QUERY = f"""
    {SUBTREE_CTE}
    SELECT
      ir.id, ir.score, ir.method, ir.created_at,
      cp.id AS existing_id, cp.name AS existing_name, cp.age AS existing_age,
      cp.sex AS existing_sex, cp.phone AS existing_phone,
      cp_org.name AS existing_village_name,
      cp_last.reason AS existing_last_seen_reason,
      cp_last.created_server_time AS existing_last_seen_at,
      np.id AS new_id, np.name AS new_name, np.age AS new_age,
      np.sex AS new_sex, np.phone AS new_phone,
      np_org.name AS new_village_name,
      np_last.reason AS new_last_seen_reason,
      np_last.created_server_time AS new_last_seen_at
    FROM identity_review ir
    JOIN patient np ON np.id = ir.new_patient_id
    JOIN patient cp ON cp.id = ir.candidate_patient_id
    LEFT JOIN org_unit np_org ON np_org.id = np.village_org_id
    LEFT JOIN org_unit cp_org ON cp_org.id = cp.village_org_id
    LEFT JOIN LATERAL (
      SELECT reason, created_server_time FROM referral
      WHERE patient_id = cp.id ORDER BY created_server_time DESC LIMIT 1
    ) cp_last ON true
    LEFT JOIN LATERAL (
      SELECT reason, created_server_time FROM referral
      WHERE patient_id = np.id ORDER BY created_server_time DESC LIMIT 1
    ) np_last ON true
    WHERE ir.status = 'pending' AND np.village_org_id IN (SELECT id FROM subtree)
    ORDER BY ir.created_at ASC
"""


@router.get("/reviews", response_model=IdentityReviewListResponse)
async def list_reviews(
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> IdentityReviewListResponse:
    result = await session.execute(text(_LIST_QUERY), subtree_params(user.org_unit_id))
    rows = result.mappings().all()
    reviews = [
        IdentityReviewRow(
            id=row["id"],
            score=float(row["score"]),
            method=row["method"],
            created_at=row["created_at"],
            existing=IdentityReviewPatient(
                id=row["existing_id"],
                name=row["existing_name"],
                age=row["existing_age"],
                sex=row["existing_sex"],
                phone=row["existing_phone"],
                village_name=row["existing_village_name"],
                last_seen_reason=row["existing_last_seen_reason"],
                last_seen_at=row["existing_last_seen_at"],
            ),
            new=IdentityReviewPatient(
                id=row["new_id"],
                name=row["new_name"],
                age=row["new_age"],
                sex=row["new_sex"],
                phone=row["new_phone"],
                village_name=row["new_village_name"],
                last_seen_reason=row["new_last_seen_reason"],
                last_seen_at=row["new_last_seen_at"],
            ),
        )
        for row in rows
    ]
    return IdentityReviewListResponse(reviews=reviews)


_DECIDE_UPDATE = f"""
    {SUBTREE_CTE}
    UPDATE identity_review ir
    SET status = :status, decided_by = :decided_by, decided_at = :now
    FROM patient np
    WHERE ir.id = :id AND ir.status = 'pending'
      AND np.id = ir.new_patient_id AND np.village_org_id IN (SELECT id FROM subtree)
    RETURNING ir.new_patient_id, ir.candidate_patient_id, ir.score, ir.method
"""

_SAME_SCOPE_STATUS = f"""
    {SUBTREE_CTE}
    SELECT ir.status
    FROM identity_review ir
    JOIN patient np ON np.id = ir.new_patient_id
    WHERE ir.id = :id AND np.village_org_id IN (SELECT id FROM subtree)
"""


async def _apply_merge(
    session: AsyncSession,
    *,
    new_patient_id: UUID,
    candidate_patient_id: UUID,
    score,
    method,
    decided_by: UUID,
) -> None:
    await session.execute(
        text("UPDATE referral SET patient_id = :candidate WHERE patient_id = :new_patient"),
        {"candidate": candidate_patient_id, "new_patient": new_patient_id},
    )
    name_result = await session.execute(
        text("SELECT name FROM patient WHERE id = :id"), {"id": new_patient_id}
    )
    new_patient_name = name_result.scalar_one()
    await session.execute(
        text(
            """INSERT INTO patient_alias
                 (id, patient_id, raw_name, normalized_alias,
                  match_method, match_score, confirmed_by)
               VALUES
                 (:id, :patient_id, :raw_name, :normalized_alias,
                  :match_method, :match_score, :confirmed_by)"""
        ),
        {
            "id": uuid.uuid4(),
            "patient_id": candidate_patient_id,
            "raw_name": new_patient_name,
            "normalized_alias": normalize(new_patient_name),
            "match_method": method,
            "match_score": score,
            "confirmed_by": decided_by,
        },
    )
    await session.execute(
        text("UPDATE patient SET merged_into_id = :candidate WHERE id = :new_patient"),
        {"candidate": candidate_patient_id, "new_patient": new_patient_id},
    )


@router.post("/reviews/{review_id}/decide", response_model=IdentityReviewDecisionResponse)
async def decide(
    review_id: UUID,
    body: IdentityReviewDecisionRequest,
    clock: Clock = Depends(get_clock),
    user: CurrentUser = Depends(get_current_user),
) -> IdentityReviewDecisionResponse:
    now = clock.now()
    new_status = "merged" if body.decision == "merge" else "kept_separate"

    async with async_session_factory() as s, s.begin():
        updated = await s.execute(
            text(_DECIDE_UPDATE),
            {
                **subtree_params(user.org_unit_id),
                "status": new_status,
                "decided_by": user.id,
                "now": now,
                "id": review_id,
            },
        )
        row = updated.first()

        if row is None:
            same_scope = await s.execute(
                text(_SAME_SCOPE_STATUS), {**subtree_params(user.org_unit_id), "id": review_id}
            )
            existing = same_scope.first()
            if existing is None:
                # 404, not 403 — same rule as app/api/referrals.py
                # (docs/decisions/ADR-005.md): a guess at another org's
                # review id cannot be used to confirm it exists.
                raise HTTPException(status.HTTP_404_NOT_FOUND, "review not found")
            return IdentityReviewDecisionResponse(id=review_id, status=existing.status)

        if body.decision == "merge":
            await _apply_merge(
                s,
                new_patient_id=row.new_patient_id,
                candidate_patient_id=row.candidate_patient_id,
                score=row.score,
                method=row.method,
                decided_by=user.id,
            )

    return IdentityReviewDecisionResponse(id=review_id, status=new_status)
