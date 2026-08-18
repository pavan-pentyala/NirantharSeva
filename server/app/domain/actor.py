"""Who is performing an operation. Resolved server-side from the
authenticated session (docs/decisions/ADR-006.md) — never trusted from an
op payload. Lives here, not in app/api/, so app/sync/ never has to import
from app/api/ to know who is acting.
"""

from dataclasses import dataclass
from uuid import UUID

from app.domain.states import Role


@dataclass(frozen=True)
class Actor:
    user_id: UUID
    role: Role
    org_unit_id: UUID
