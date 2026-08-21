from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class IdentityReviewPatient(BaseModel):
    """One side of a pair on Screen 6. `last_seen_reason`/`last_seen_at`
    are the patient's most recent referral — computed, not stored (the
    design's own "Husband's name" field has no column and is dropped;
    "Last seen" does and is kept, docs/PHASE6_PLAN.md "Traps")."""

    id: UUID
    name: str
    age: int | None
    sex: str | None
    phone: str | None
    village_name: str | None
    last_seen_reason: str | None
    last_seen_at: datetime | None


class IdentityReviewRow(BaseModel):
    id: UUID
    score: float
    method: str
    created_at: datetime
    existing: IdentityReviewPatient
    new: IdentityReviewPatient


class IdentityReviewListResponse(BaseModel):
    reviews: list[IdentityReviewRow]


class IdentityReviewDecisionRequest(BaseModel):
    decision: Literal["merge", "keep_separate"]


class IdentityReviewDecisionResponse(BaseModel):
    id: UUID
    status: Literal["merged", "kept_separate"]
