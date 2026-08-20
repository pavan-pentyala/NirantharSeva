from uuid import UUID

from pydantic import BaseModel


class OrgUnitOut(BaseModel):
    id: UUID
    name: str
    type: str
    parent_id: UUID | None


class OrgUnitListResponse(BaseModel):
    org_units: list[OrgUnitOut]
