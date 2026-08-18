"""Org-subtree visibility. See docs/decisions/ADR-005.md.

One recursive CTE, three call sites: GET /referrals, GET /referrals/{id},
and the referral branch of GET /sync/pull. Returns a SQL fragment plus
params — never a materialised Python list of ids (ADR-005: a second round
trip, a silent truncation risk, and a security predicate a later refactor
can drop without any query visibly changing).

Visibility is decided by origin_org_id alone; target_org_id does not
participate (ADR-005 point 1).
"""

from uuid import UUID

SUBTREE_CTE = """\
WITH RECURSIVE subtree AS (
  SELECT id FROM org_unit WHERE id = :root
  UNION ALL
  SELECT o.id FROM org_unit o JOIN subtree s ON o.parent_id = s.id
)"""


def subtree_params(root: UUID) -> dict[str, UUID]:
    return {"root": root}
