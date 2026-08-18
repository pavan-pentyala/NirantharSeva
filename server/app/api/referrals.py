"""D5 — the minimal scoped referral read API. docs/PHASE2_PLAN.md D5,
docs/decisions/ADR-005.md.

GET /referrals is a list, not a timeline or a dashboard. GET /referrals/{id}
is a summary, not P3's timeline endpoint. Both are an API, not a screen —
the UI is P4's.

The scope predicate is part of the lookup query itself, never a check
applied after the row comes back — that is what stops the 403 creeping
back in (docs/PHASE2_PLAN.md, "Implementation note that stops the 403
creeping back").
"""

import base64
import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import CurrentUser, get_current_user
from app.api.scoping import SUBTREE_CTE, subtree_params
from app.db import get_session
from app.domain.states import State
from app.schemas.referral import ReferralListResponse, ReferralOut

router = APIRouter(prefix="/referrals", tags=["referrals"])

_DEFAULT_LIMIT = 50
_MAX_LIMIT = 200

_REFERRAL_COLUMNS = """id, patient_id, origin_org_id, target_org_id, reason, priority,
                       current_state, state_entered_at"""


def _encode_cursor(state_entered_at, referral_id: UUID) -> str:
    raw = json.dumps([state_entered_at.isoformat(), str(referral_id)])
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[str, str]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        ts, rid = json.loads(raw)
        return ts, rid
    except Exception as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid cursor") from exc


@router.get("", response_model=ReferralListResponse)
async def list_referrals(
    state: str | None = None,
    limit: int = Query(_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT),
    cursor: str | None = None,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> ReferralListResponse:
    params: dict = {**subtree_params(user.org_unit_id), "fetch_limit": limit + 1}
    conditions = ["origin_org_id IN (SELECT id FROM subtree)"]

    if state is not None:
        try:
            State(state)
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"unknown state: {state}") from exc
        conditions.append("current_state = :state")
        params["state"] = state

    if cursor is not None:
        cursor_ts, cursor_id = _decode_cursor(cursor)
        conditions.append(
            "(state_entered_at < :cursor_ts OR (state_entered_at = :cursor_ts AND id < :cursor_id))"
        )
        params["cursor_ts"] = cursor_ts
        params["cursor_id"] = cursor_id

    query = f"""
        {SUBTREE_CTE}
        SELECT {_REFERRAL_COLUMNS}
        FROM referral
        WHERE {" AND ".join(conditions)}
        ORDER BY state_entered_at DESC, id DESC
        LIMIT :fetch_limit
    """
    result = await session.execute(text(query), params)
    rows = result.mappings().all()

    has_more = len(rows) > limit
    page = rows[:limit]
    referrals = [ReferralOut(**row) for row in page]
    next_cursor = _encode_cursor(page[-1]["state_entered_at"], page[-1]["id"]) if has_more else None

    return ReferralListResponse(referrals=referrals, cursor=next_cursor, has_more=has_more)


@router.get("/{referral_id}", response_model=ReferralOut)
async def get_referral(
    referral_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> ReferralOut:
    query = f"""
        {SUBTREE_CTE}
        SELECT {_REFERRAL_COLUMNS}
        FROM referral
        WHERE id = :referral_id AND origin_org_id IN (SELECT id FROM subtree)
    """
    params = {**subtree_params(user.org_unit_id), "referral_id": referral_id}
    result = await session.execute(text(query), params)
    row = result.mappings().first()
    if row is None:
        # 404, not 403 — indistinguishable from a genuinely missing id.
        # A 403 would confirm the referral exists, which is the leak
        # (docs/decisions/ADR-005.md).
        raise HTTPException(status.HTTP_404_NOT_FOUND, "referral not found")
    return ReferralOut(**row)
