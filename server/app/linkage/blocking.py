"""Candidate fetch for identity resolution. docs/decisions/ADR-014.md.

Blocking scopes candidates by village **always** — this is the executable
form of the handoff's fourth unforgivable thing (§5: "never fuzzy-match
without blocking first"). Phone only narrows the candidate set, and only
when both records carry one: `patient.phone` is nullable and a blank phone
is the common case, not the edge case (ADR-014). A candidate from another
village is never returned, at any phone value, at any threshold.

Seam for P6.2: once migration 0007 adds `patient.merged_into_id`, this
query needs `AND merged_into_id IS NULL` — the column does not exist yet,
so it cannot be written here. Marked below; do not work around its absence
by filtering merged rows out in Python, since that would silently drop the
predicate the moment the column arrives and nobody remembers to wire it in.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class Candidate:
    id: uuid.UUID
    normalized_name: str


# CAST(:phone AS text) is load-bearing, not decoration: :phone's first use
# is `:phone IS NULL`, which gives asyncpg's prepared-statement protocol no
# type to infer from a NULL comparison, so a call with phone=None raises
# asyncpg.exceptions.AmbiguousParameterError instead of matching anything —
# discovered running this query for real, the same shape as observation 37
# (docs/PHASE2_OBSERVATIONS.md, SLA_SCALE's CAST in app/domain/escalation.py).
_BLOCK_QUERY = """
    SELECT id, normalized_name
    FROM patient
    WHERE village_org_id = :village_org_id
      AND (CAST(:phone AS text) IS NULL OR phone IS NULL
           OR left(phone, 4) = left(CAST(:phone AS text), 4))
      -- P6.2 (migration 0007) adds: AND merged_into_id IS NULL
"""


async def block(
    session: AsyncSession, *, village_org_id: uuid.UUID, phone: str | None
) -> list[Candidate]:
    """Every patient row in `village_org_id` whose phone does not
    positively disagree with `phone`. Never crosses a village boundary."""
    rows = await session.execute(
        text(_BLOCK_QUERY), {"village_org_id": village_org_id, "phone": phone}
    )
    return [Candidate(id=row.id, normalized_name=row.normalized_name) for row in rows.all()]
