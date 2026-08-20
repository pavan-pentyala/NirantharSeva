"""GET /sync/pull. A gap-free scan of seq is safe only because event appends
are serialised through acquire_seq_lock (docs/decisions/ADR-002.md) — every
committed seq is visible in commit order, so `seq > since` never skips a row
that will still show up later.

D7/ADR-005: scoped to the caller's org subtree. The predicate lives inside
the query's own WHERE, before LIMIT — never applied in Python after the
fetch (a page filtered to empty in Python still advances has_more/cursor
logic as if nothing more existed, and the client stops advancing
permanently).

D14/ADR-010: payload also carries a referral snapshot — patient_name, age,
sex, reason, priority, target_org_name — joined from `patient` and
`org_unit` inside the same subquery, before LIMIT, for the same reason the
subtree predicate lives there and not in Python. Every referral event
repeats this snapshot, not just the create_referral one — ADR-010's
accepted cost, not an oversight.

Phase 4.3: this was a UNION ALL of an unscoped toy branch and this scoped
referral branch (D7/ADR-005) until the toy model was dropped (migration
0006, D1). event_seq (migration 0003) still isn't OWNED BY referral_event —
that was always about surviving the toy model's own event table being
dropped, not about that table existing forever.
"""

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.scoping import SUBTREE_CTE, subtree_params
from app.schemas.sync import EventOut, PullResponse


def _decode_payload(value: Any) -> dict:
    """Same asyncpg jsonb-via-text() quirk as push.py's _decode_detail:
    with no Core column type info, the driver hands back a string, not a
    dict."""
    if isinstance(value, str):
        return json.loads(value)
    return value or {}


async def handle_pull(
    session: AsyncSession, since: int, limit: int, actor_org_unit_id: UUID
) -> PullResponse:
    result = await session.execute(
        text(
            f"""{SUBTREE_CTE}
               SELECT e.seq, 'referral' AS entity_type, e.referral_id AS entity_id, e.op_id,
                      e.device_id, e.lamport, e.device_time, e.server_time,
                      jsonb_build_object(
                        'from_state', e.from_state, 'to_state', e.to_state,
                        'actor_role', e.actor_role, 'actor_user_id', e.actor_user_id,
                        'patient_name', p.name, 'age', p.age, 'sex', p.sex,
                        'reason', r.reason, 'priority', r.priority,
                        'target_org_name', target_org.name
                      ) AS payload
               FROM referral_event e
               JOIN referral r ON r.id = e.referral_id
               JOIN patient p ON p.id = r.patient_id
               LEFT JOIN org_unit target_org ON target_org.id = r.target_org_id
               WHERE e.seq > :since AND r.origin_org_id IN (SELECT id FROM subtree)
               ORDER BY e.seq ASC
               LIMIT :fetch_limit"""
        ),
        {"since": since, "fetch_limit": limit + 1, **subtree_params(actor_org_unit_id)},
    )
    rows = result.mappings().all()

    has_more = len(rows) > limit
    page = rows[:limit]

    events: list[EventOut] = []
    for row in page:
        fields: dict[str, Any] = dict(row)
        fields["payload"] = _decode_payload(fields["payload"])
        events.append(EventOut(**fields))
    cursor = events[-1].seq if events else since

    return PullResponse(events=events, cursor=cursor, has_more=has_more)
