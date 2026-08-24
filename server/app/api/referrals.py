"""D5 — the minimal scoped referral read API. docs/PHASE2_PLAN.md D5,
docs/decisions/ADR-005.md.

GET /referrals is a list, not a timeline or a dashboard. GET /referrals/{id}
is a summary, not P3's timeline endpoint. Both are an API, not a screen —
the UI is P4's.

The scope predicate is part of the lookup query itself, never a check
applied after the row comes back — that is what stops the 403 creeping
back in (docs/PHASE2_PLAN.md, "Implementation note that stops the 403
creeping back").
"""

import base64
import json
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import CurrentUser, get_current_user
from app.api.scoping import SUBTREE_CTE, subtree_params
from app.db import get_session
from app.domain.states import State, replay_steps
from app.instrumentation.logging import get_logger
from app.schemas.referral import (
    ReferralListResponse,
    ReferralOut,
    ReferralTimelineOut,
    TimelineEventOut,
)
from app.sync.event_log import triple

_logger = get_logger(__name__)

router = APIRouter(prefix="/referrals", tags=["referrals"])

_DEFAULT_LIMIT = 50
_MAX_LIMIT = 200

_REFERRAL_COLUMNS = """id, patient_id, origin_org_id, target_org_id, reason, priority,
                       current_state, state_entered_at"""


def _encode_cursor(state_entered_at, referral_id: UUID) -> str:
    raw = json.dumps([state_entered_at.isoformat(), str(referral_id)])
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    """Returns a real datetime, not the raw ISO string — asyncpg's wire
    protocol infers the bind parameter's type from the column it's
    compared against (state_entered_at, TIMESTAMPTZ) and requires an
    actual datetime.datetime for that type; a plain str raises
    asyncpg.exceptions.DataError the moment a second page is ever
    requested. Found in a pre-Phase-9 audit — no existing test requested a
    real second page, so this was never exercised."""
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        ts, rid = json.loads(raw)
        return datetime.fromisoformat(ts), rid
    except Exception as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid cursor") from exc


@router.get("", response_model=ReferralListResponse)
async def list_referrals(
    state: str | None = None,
    limit: int = Query(_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT),
    cursor: str | None = None,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> ReferralListResponse:
    params: dict = {**subtree_params(user.org_unit_id), "fetch_limit": limit + 1}
    conditions = ["origin_org_id IN (SELECT id FROM subtree)"]

    if state is not None:
        try:
            State(state)
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"unknown state: {state}") from exc
        conditions.append("current_state = :state")
        params["state"] = state

    if cursor is not None:
        cursor_ts, cursor_id = _decode_cursor(cursor)
        conditions.append(
            "(state_entered_at < :cursor_ts OR (state_entered_at = :cursor_ts AND id < :cursor_id))"
        )
        params["cursor_ts"] = cursor_ts
        params["cursor_id"] = cursor_id

    query = f"""
        {SUBTREE_CTE}
        SELECT {_REFERRAL_COLUMNS}
        FROM referral
        WHERE {" AND ".join(conditions)}
        ORDER BY state_entered_at DESC, id DESC
        LIMIT :fetch_limit
    """
    result = await session.execute(text(query), params)
    rows = result.mappings().all()

    has_more = len(rows) > limit
    page = rows[:limit]
    referrals = [ReferralOut(**row) for row in page]
    next_cursor = _encode_cursor(page[-1]["state_entered_at"], page[-1]["id"]) if has_more else None

    return ReferralListResponse(referrals=referrals, cursor=next_cursor, has_more=has_more)


@router.get("/{referral_id}", response_model=ReferralOut)
async def get_referral(
    referral_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> ReferralOut:
    query = f"""
        {SUBTREE_CTE}
        SELECT {_REFERRAL_COLUMNS}
        FROM referral
        WHERE id = :referral_id AND origin_org_id IN (SELECT id FROM subtree)
    """
    params = {**subtree_params(user.org_unit_id), "referral_id": referral_id}
    result = await session.execute(text(query), params)
    row = result.mappings().first()
    if row is None:
        # 404, not 403 — indistinguishable from a genuinely missing id.
        # A 403 would confirm the referral exists, which is the leak
        # (docs/decisions/ADR-005.md).
        raise HTTPException(status.HTTP_404_NOT_FOUND, "referral not found")
    return ReferralOut(**row)


@router.get("/{referral_id}/timeline", response_model=ReferralTimelineOut)
async def get_referral_timeline(
    referral_id: UUID,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(get_current_user),
) -> ReferralTimelineOut:
    """Every event for referral_id, in commit order, each tagged whether it
    advanced current_state. docs/decisions/ADR-008.md — the fifth call
    site of SUBTREE_CTE (app/api/scoping.py).

    Ordering is seq ASC — not server_time (two events can share a clock
    tick), not device_time (client-supplied, arbitrary), and not lamport
    (a partial order: a losing write carries a *higher* lamport than the
    winner it lost to). seq is commit order, and that is true because
    app/db.py's acquire_seq_lock (docs/decisions/ADR-002.md) serialises
    sequence assignment against commit order.

    Does not paginate, and should not gain a ?cursor= later without
    reading this: the advanced flag is prefix-dependent (replay_steps
    folds left to right), so a page starting mid-log cannot know whether
    its first event advanced without having folded everything before it.
    A cursor is only correct if it carries the running state — real
    complexity to bound a collection the state machine already bounds in
    practice (roughly six advancing transitions plus however many losers).

    One query, an INNER JOIN, not a LEFT JOIN: a referral that does not
    exist, one that exists but is outside the caller's subtree, and one
    that exists and is visible but has zero events all produce zero rows
    here — all three collapse to the same 404 on purpose. Telling them
    apart needs a second query whose only function is to leak the
    difference; python -m app.verify_replay is where a zero-event
    referral is actually diagnosed, not this path.
    """
    query = f"""
        {SUBTREE_CTE}
        SELECT r.current_state,
               e.seq, e.op_id, e.from_state, e.to_state, e.actor_role,
               e.actor_user_id, e.device_id, e.lamport, e.device_time, e.server_time
        FROM referral r
        JOIN referral_event e ON e.referral_id = r.id
        WHERE r.id = :referral_id AND r.origin_org_id IN (SELECT id FROM subtree)
        ORDER BY e.seq ASC
    """
    params = {**subtree_params(user.org_unit_id), "referral_id": referral_id}
    result = await session.execute(text(query), params)
    event_rows = result.all()
    if not event_rows:
        # 404, not 403 — same rule as get_referral (docs/decisions/ADR-005.md).
        raise HTTPException(status.HTTP_404_NOT_FOUND, "referral not found")

    current_state = event_rows[0].current_state
    steps = list(replay_steps(triple(r) for r in event_rows))

    events = [
        TimelineEventOut(
            seq=r.seq,
            op_id=r.op_id,
            from_state=r.from_state,
            to_state=r.to_state,
            advanced=advanced,
            actor_role=r.actor_role,
            actor_user_id=r.actor_user_id,
            device_id=r.device_id,
            lamport=r.lamport,
            device_time=r.device_time,
            server_time=r.server_time,
        )
        for r, (advanced, *_rest) in zip(event_rows, steps, strict=True)
    ]

    replayed_state = steps[-1][1]  # steps is non-empty: event_rows is non-empty

    if replayed_state is None or replayed_state.value != current_state:
        _logger.error(
            "current_state cache disagrees with the replayed event log — I3 violated",
            extra={"referral_id": str(referral_id)},
        )

    return ReferralTimelineOut(
        referral_id=referral_id,
        current_state=current_state,
        replayed_state=replayed_state.value if replayed_state is not None else None,
        events=events,
    )
