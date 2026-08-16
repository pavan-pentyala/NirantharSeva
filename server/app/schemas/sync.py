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
    seq: int
    toy_id: UUID
    old_value: int | None
    new_value: int
    op_id: UUID
    device_id: str
    lamport: int
    device_time: datetime
    server_time: datetime


class PullResponse(BaseModel):
    events: list[EventOut]
    cursor: int
    has_more: bool
