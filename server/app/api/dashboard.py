"""The supervisor dashboard — docs/PHASE5_PLAN.md P5.2, docs/decisions/
ADR-011.md, docs/decisions/ADR-012.md. Plan §9.3's headline: a breach
appearing on this screen without a page refresh.

GET /dashboard and GET /dashboard/stream share one snapshot query
(_fetch_snapshot) — the same stat strip and overdue list either way. This
is deliberately a separate read from /sync/pull: the wire sync contract is
frozen (handoff §2) and its payload (ADR-010) carries no village name or
ASHA name, which this screen needs and pull's contract was never asked to
grow to cover.

Notifications carry no data (ADR-011) — the stream re-runs this same
org-scoped query every time it wakes, and once more on connect/reconnect,
since a LISTEN/NOTIFY message issued while a client was disconnected is
simply lost. The client is expected to write every snapshot into Dexie and
render only from there (docs/PHASE5_PLAN.md "Traps") — this module has no
opinion on that; it only ever returns the current truth.
"""

import asyncio
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import CurrentUser, get_current_user, get_current_user_from_query_token
from app.api.scoping import SUBTREE_CTE, subtree_params
from app.clock import Clock, get_clock
from app.db import async_session_factory, get_session
from app.realtime import subscribe, unsubscribe
from app.schemas.dashboard import DashboardOverdueRow, DashboardSnapshot, DashboardStats

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

HEARTBEAT_SECONDS = 20

_STATS_QUERY = f"""
    {SUBTREE_CTE}
    SELECT
      COUNT(*) FILTER (WHERE current_state NOT IN ('CLOSED','LOST')) AS open,
      COUNT(*) FILTER (WHERE current_state = 'IN_TRANSIT') AS on_the_way,
      COUNT(*) FILTER (WHERE current_state = 'ARRIVED') AS reached_centre,
      COUNT(*) FILTER (WHERE current_state IN ('TREATED','BACK_REFERRED')) AS treated_or_sent_back,
      COUNT(*) FILTER (WHERE current_state = 'ESCALATED') AS overdue,
      COUNT(*) FILTER (
        WHERE current_state = 'CLOSED'
          AND state_entered_at >= date_trunc('month', CAST(:now AS timestamptz))
      ) AS closed_this_month
    FROM referral
    WHERE origin_org_id IN (SELECT id FROM subtree)
"""

# Secondary ORDER BY term, not in the SELECT list (Postgres allows this
# outside DISTINCT queries — no schema/response-shape change needed):
# every referral escalated in the SAME sweep pass shares an identical
# e.triggered_at (app/domain/escalation.py computes `now` once per sweep()
# call, not once per row), so triggered_at ASC alone leaves ties in
# whatever order the query planner happens to return them — no SQL
# guarantee, and confirmed to actually flip (a pre-Phase-9 audit's
# unrelated column-drop migration flipped a previously-passing sort-order
# test with zero change to this query). referral_event.seq is this
# project's own true commit-order marker (ADR-002's advisory lock makes
# seq order == commit order); joining back to the specific ESCALATED
# event this escalation row was created alongside (same transaction, same
# server_time) gives a real secondary key instead of an accidental one.
_OVERDUE_QUERY = f"""
    {SUBTREE_CTE}
    SELECT e.id AS escalation_id, e.referral_id, p.name AS patient_name,
           origin_org.name AS village_name, target_org.name AS target_org_name,
           r.reason, asha.display_name AS asha_name, asha.phone AS asha_phone, e.triggered_at
    FROM escalation e
    JOIN referral r ON r.id = e.referral_id
    JOIN patient p ON p.id = r.patient_id
    LEFT JOIN org_unit origin_org ON origin_org.id = r.origin_org_id
    LEFT JOIN org_unit target_org ON target_org.id = r.target_org_id
    LEFT JOIN app_user asha ON asha.id = r.origin_user_id
    WHERE e.resolved_at IS NULL AND r.origin_org_id IN (SELECT id FROM subtree)
    ORDER BY e.triggered_at ASC,
             (SELECT MAX(re.seq) FROM referral_event re
              WHERE re.referral_id = e.referral_id AND re.to_state = 'ESCALATED'
                AND re.server_time = e.triggered_at) ASC
"""


async def _fetch_snapshot(
    session: AsyncSession, org_unit_id: UUID, clock: Clock
) -> DashboardSnapshot:
    params = subtree_params(org_unit_id)
    stats_row = (
        (await session.execute(text(_STATS_QUERY), {**params, "now": clock.now()})).mappings().one()
    )
    overdue_rows = (await session.execute(text(_OVERDUE_QUERY), params)).mappings().all()
    return DashboardSnapshot(
        stats=DashboardStats(**stats_row),
        overdue=[DashboardOverdueRow(**row) for row in overdue_rows],
    )


@router.get("", response_model=DashboardSnapshot)
async def dashboard(
    session: AsyncSession = Depends(get_session),
    clock: Clock = Depends(get_clock),
    user: CurrentUser = Depends(get_current_user),
) -> DashboardSnapshot:
    return await _fetch_snapshot(session, user.org_unit_id, clock)


def _sse_event(snapshot: DashboardSnapshot) -> str:
    return f"data: {snapshot.model_dump_json()}\n\n"


async def stream_events(
    org_unit_id: UUID, clock: Clock, heartbeat_seconds: int = HEARTBEAT_SECONDS
):
    """The SSE body, as a standalone async generator — pulled out of the
    route function so a test can iterate it directly with `anext()`,
    without going through an HTTP client. httpx's ASGITransport cannot
    drive a response whose generator has a real gap between chunks (it
    hangs waiting for the body to finish, not just the next chunk — proven
    against a trivial FastAPI app with zero middleware, not something
    particular to this route), so an HTTP-level test of a live,
    still-open connection isn't practical here; P5.2's Playwright test
    against a real server is the actual proof of the wire behaviour.
    `heartbeat_seconds` is a parameter, not always the module constant, so
    a test can shrink it instead of waiting 20 real seconds.
    """
    queue = subscribe()
    try:
        # On connect and on every reconnect (ADR-011's "honest cost": a
        # notification issued while disconnected is simply gone, so the
        # stream cannot be treated as the source of truth by itself).
        async with async_session_factory() as session:
            yield _sse_event(await _fetch_snapshot(session, org_unit_id, clock))

        while True:
            try:
                await asyncio.wait_for(queue.get(), timeout=heartbeat_seconds)
                async with async_session_factory() as session:
                    yield _sse_event(await _fetch_snapshot(session, org_unit_id, clock))
            except TimeoutError:
                yield ": heartbeat\n\n"
    finally:
        unsubscribe(queue)


@router.get("/stream")
async def stream(
    clock: Clock = Depends(get_clock),
    user: CurrentUser = Depends(get_current_user_from_query_token),
) -> StreamingResponse:
    return StreamingResponse(stream_events(user.org_unit_id, clock), media_type="text/event-stream")
