"""GET /org_units — P4.2. Org names and hierarchy, not exposed to the
client anywhere before this (the JWT carries only the actor's own
org_unit_id, a bare UUID). Needed offline: Screen 2's "Village: yours" and
"Sending to" facility picker, and any screen that has to show a facility
name rather than an id.

Unscoped by design, unlike GET /referrals (docs/decisions/ADR-005.md):
org names and the tree shape are not patient data and carry none of the
confidentiality concerns origin_org_id-based referral scoping exists for.
Requires authentication (any role), nothing more.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import CurrentUser, get_current_user
from app.db import get_session
from app.schemas.org_unit import OrgUnitListResponse, OrgUnitOut

router = APIRouter(prefix="/org_units", tags=["org_units"])


@router.get("", response_model=OrgUnitListResponse)
async def list_org_units(
    session: AsyncSession = Depends(get_session),
    _user: CurrentUser = Depends(get_current_user),
) -> OrgUnitListResponse:
    result = await session.execute(text("SELECT id, name, type, parent_id FROM org_unit"))
    rows = result.mappings().all()
    return OrgUnitListResponse(org_units=[OrgUnitOut(**row) for row in rows])
