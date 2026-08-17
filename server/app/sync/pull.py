"""GET /sync/pull. A gap-free scan of seq is safe only because event appends
are serialised through acquire_seq_lock (docs/decisions/ADR-002.md) — every
committed seq is visible in commit order, so `seq > since` never skips a row
that will still show up later.

D3/ADR-004: toy_event and referral_event share one sequence (event_seq, see
migration 0003), so a single seq-ordered UNION ALL across both tables is a
gap-free stream for one cursor. Each entity type's own fields are packed
into `payload`; only the fields the sync engine itself needs stay flat.
"""

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.sync import EventOut, PullResponse


def _decode_payload(value: Any) -> dict:
    """Same asyncpg jsonb-via-text() quirk as push.py's _decode_detail:
    with no Core column type info, the driver hands back a string, not a
    dict."""
    if isinstance(value, str):
        return json.loads(value)
    return value or {}


async def handle_pull(session: AsyncSession, since: int, limit: int) -> PullResponse:
    result = await session.execute(
        text(
            """(SELECT seq, 'toy' AS entity_type, toy_id AS entity_id, op_id, device_id,
                       lamport, device_time, server_time,
                       jsonb_build_object('old_value', old_value, 'new_value', new_value) AS payload
                FROM toy_event
                WHERE seq > :since)
               UNION ALL
               (SELECT seq, 'referral' AS entity_type, referral_id AS entity_id, op_id, device_id,
                       lamport, device_time, server_time,
                       jsonb_build_object(
                         'from_state', from_state, 'to_state', to_state,
                         'actor_role', actor_role, 'actor_user_id', actor_user_id
                       ) AS payload
                FROM referral_event
                WHERE seq > :since)
               ORDER BY seq ASC
               LIMIT :fetch_limit"""
        ),
        {"since": since, "fetch_limit": limit + 1},
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
