from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class DashboardStats(BaseModel):
    """The stat strip, Screen 4 (docs/design_handoff_ui_screens). `open`
    counts every non-terminal referral, including CREATED — CREATED has no
    dedicated column of its own, matching the mockup's own arithmetic
    (open != the sum of the other columns)."""

    open: int
    on_the_way: int
    reached_centre: int
    treated_or_sent_back: int
    overdue: int
    closed_this_month: int


class DashboardOverdueRow(BaseModel):
    escalation_id: UUID
    referral_id: UUID
    patient_name: str
    village_name: str | None
    target_org_name: str | None
    reason: str | None
    asha_name: str | None
    asha_phone: str | None
    triggered_at: datetime


class DashboardSnapshot(BaseModel):
    stats: DashboardStats
    overdue: list[DashboardOverdueRow]
