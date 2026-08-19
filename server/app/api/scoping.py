"""Org-subtree visibility. See docs/decisions/ADR-005.md.

One recursive CTE. Call sites, enumerated rather than counted because a
count drifts and a list can be checked — if you add one, add it here:

1. GET /referrals (app/api/referrals.py::list_referrals)
2. GET /referrals/{id} (app/api/referrals.py::get_referral)
3. The referral branch of GET /sync/pull (app/sync/pull.py)
4. app/sync/push.py::_actor_can_see_referral_origin — the write path needs
   the same subtree test the read path uses (D6, added after ADR-005 was
   written; see docs/PHASE2_OBSERVATIONS.md #11)
5. GET /referrals/{id}/timeline (app/api/referrals.py::get_referral_timeline,
   docs/decisions/ADR-008.md)

Returns a SQL fragment plus params — never a materialised Python list of
ids (ADR-005: a second round trip, a silent truncation risk, and a
security predicate a later refactor can drop without any query visibly
changing).

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
