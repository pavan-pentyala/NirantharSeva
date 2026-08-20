"""Push/pull request and response shapes. Frozen API contract (handoff §2) —
do not change these without asking the user.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

OpStatus = Literal["accepted", "accepted_stale", "conflict", "rejected"]


class Op(BaseModel):
    op_id: UUID
    entity: str
    entity_id: UUID
    operation: str
    payload: dict
    lamport: int
    device_time: datetime


class PushRequest(BaseModel):
    device_id: str
    ops: list[Op]


class OpResult(BaseModel):
    op_id: UUID
    status: OpStatus
    server_seq: int | None = None
    detail: dict | None = None


class PushResponse(BaseModel):
    results: list[OpResult]
    server_lamport: int


class EventOut(BaseModel):
    """Generic pull envelope (D3, docs/decisions/ADR-004.md). Fields the
    sync engine itself reads stay flat; everything only the domain reads
    goes in `payload`. `entity_type` is always "referral" since the toy
    model's drop (migration 0006, Phase 4.3) — kept as a field rather than
    removed, since the shape still discriminates by design (D3) even with
    one entity type today. payload is {from_state, to_state, actor_role,
    actor_user_id, patient_name, age, sex, reason, priority,
    target_org_name} — the last six are a referral snapshot, not
    sync-engine fields (D14/ADR-010); payload stays a plain dict here so
    this schema itself is unchanged by their addition."""

    seq: int
    entity_type: str
    entity_id: UUID
    op_id: UUID
    device_id: str
    lamport: int
    device_time: datetime
    server_time: datetime
    payload: dict


class PullResponse(BaseModel):
    events: list[EventOut]
    cursor: int
    has_more: bool
