"""GET /sync/pull. A gap-free scan of seq is safe only because event appends
are serialised through acquire_seq_lock (docs/decisions/ADR-002.md) — every
committed seq is visible in commit order, so `seq > since` never skips a row
that will still show up later.
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.sync import EventOut, PullResponse


async def handle_pull(session: AsyncSession, since: int, limit: int) -> PullResponse:
    result = await session.execute(
        text(
            """SELECT seq, toy_id, old_value, new_value, op_id, device_id,
                      lamport, device_time, server_time
               FROM toy_event
               WHERE seq > :since
               ORDER BY seq ASC
               LIMIT :fetch_limit"""
        ),
        {"since": since, "fetch_limit": limit + 1},
    )
    rows = result.mappings().all()

    has_more = len(rows) > limit
    page = rows[:limit]

    events = [EventOut(**row) for row in page]
    cursor = events[-1].seq if events else since

    return PullResponse(events=events, cursor=cursor, has_more=has_more)
