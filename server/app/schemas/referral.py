from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ReferralOut(BaseModel):
    id: UUID
    patient_id: UUID
    origin_org_id: UUID
    target_org_id: UUID | None
    reason: str | None
    priority: str | None
    current_state: str
    state_entered_at: datetime


class ReferralListResponse(BaseModel):
    referrals: list[ReferralOut]
    cursor: str | None
    has_more: bool
