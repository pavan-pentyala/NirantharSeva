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


class TimelineEventOut(BaseModel):
    """One referral_event row, tagged with whether it advanced
    current_state. docs/decisions/ADR-008.md — deliberately not EventOut
    from app/schemas/sync.py, which is a frozen sync-protocol contract and
    buries these fields inside payload."""

    seq: int
    op_id: UUID
    from_state: str | None
    to_state: str
    advanced: bool
    actor_role: str
    actor_user_id: UUID
    device_id: str
    lamport: int
    device_time: datetime
    server_time: datetime


class ReferralTimelineOut(BaseModel):
    referral_id: UUID
    current_state: str
    replayed_state: str | None
    events: list[TimelineEventOut]
