"""GET /dashboard and GET /dashboard/stream. docs/PHASE5_PLAN.md P5.2,
docs/decisions/ADR-011.md, docs/decisions/ADR-012.md.

Escalations are produced by the real sweep(), not hand-inserted — the point
of these tests is the read side, but a hand-built escalation row could
silently drift from what the sweep actually writes (village/ASHA names come
from a real referral+patient+org chain, not a fixture shortcut).
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app.api.dashboard import stream_events
from app.clock import SimulatedClock
from app.db import async_session_factory
from app.domain.escalation import sweep
from app.realtime import _subscribers

BASE = datetime(2026, 8, 20, 0, 0, tzinfo=UTC)


async def _user(name: str):
    async with async_session_factory() as session:
        row = (
            await session.execute(
                text("SELECT id, org_unit_id FROM app_user WHERE name = :name"), {"name": name}
            )
        ).one()
        return row.id, row.org_unit_id


async def _insert_patient(session, patient_id, name, now):
    await session.execute(
        text(
            """INSERT INTO patient (id, name, normalized_name, created_at)
               VALUES (:id, :name, :norm, :now)"""
        ),
        {"id": patient_id, "name": name, "norm": name.lower(), "now": now},
    )


async def _insert_referral(
    session, referral_id, patient_id, user_id, org_id, target_org_id, reason, now
):
    await session.execute(
        text(
            """INSERT INTO referral
                 (id, patient_id, origin_user_id, origin_org_id, target_org_id,
                  reason, priority, current_state, state_entered_at,
                  sla_profile_id, created_device_time, created_server_time)
               VALUES
                 (:id, :patient_id, :user_id, :org_id, :target_org_id,
                  :reason, 'normal', 'CREATED', :now, NULL, :now, :now)"""
        ),
        {
            "id": referral_id,
            "patient_id": patient_id,
            "user_id": user_id,
            "org_id": org_id,
            "target_org_id": target_org_id,
            "reason": reason,
            "now": now,
        },
    )


async def _phc_ramnagar_id():
    async with async_session_factory() as session:
        return (
            await session.execute(text("SELECT id FROM org_unit WHERE name = 'PHC Ramnagar'"))
        ).scalar_one()


@pytest.fixture
async def make_breached_referral():
    """Factory fixture: make_breached_referral(username, patient_name,
    reason, state_entered_at) -> referral_id, a CREATED referral owned by
    `username`, breached against the CREATED SLA profile (24h). Inserted
    directly, with no matching CREATED event — the same "zero_events" shape
    test_escalation_sweep.py's make_referral fixture uses, and for the same
    reason it needs the same cleanup: left behind, a referral like this
    fails test_replay_verifier.py's whole-database check the next time it
    runs in this session, regardless of which test module created it."""
    created: list[uuid.UUID] = []

    async def _factory(
        username: str, patient_name: str, reason: str, state_entered_at
    ) -> uuid.UUID:
        user_id, org_id = await _user(username)
        target_org_id = await _phc_ramnagar_id()
        referral_id = uuid.uuid4()
        patient_id = uuid.uuid4()
        async with async_session_factory() as session, session.begin():
            await _insert_patient(session, patient_id, patient_name, state_entered_at)
            await _insert_referral(
                session,
                referral_id,
                patient_id,
                user_id,
                org_id,
                target_org_id,
                reason,
                state_entered_at,
            )
        created.append(referral_id)
        return referral_id

    yield _factory

    async with async_session_factory() as session, session.begin():
        for referral_id in created:
            await session.execute(
                text("DELETE FROM referral_event WHERE referral_id=:id"), {"id": referral_id}
            )
            await session.execute(
                text("DELETE FROM escalation WHERE referral_id=:id"), {"id": referral_id}
            )
            await session.execute(text("DELETE FROM referral WHERE id=:id"), {"id": referral_id})


async def test_dashboard_stats_and_overdue_row_shape(
    client, supervisor_auth_headers, make_breached_referral
):
    triggered_at = BASE - timedelta(hours=25)  # CREATED SLA: 24h
    referral_id = await make_breached_referral(
        "asha_a", "Dashboard Test Patient A", "fever", triggered_at
    )
    await sweep(async_session_factory, SimulatedClock(BASE))

    resp = await client.get("/dashboard", headers=supervisor_auth_headers)
    assert resp.status_code == 200
    body = resp.json()

    assert body["stats"]["overdue"] >= 1
    row = next(r for r in body["overdue"] if r["referral_id"] == str(referral_id))
    assert row["patient_name"] == "Dashboard Test Patient A"
    assert row["village_name"] == "Village A"
    assert row["target_org_name"] == "PHC Ramnagar"
    assert row["reason"] == "fever"
    assert row["asha_name"] == "Sunita Kumari"  # seed.py's display_name for asha_a


async def test_overdue_list_sorted_worst_first(
    client, supervisor_auth_headers, make_breached_referral
):
    older = await make_breached_referral(
        "asha_a", "Dashboard Sort Old", "fever", BASE - timedelta(hours=48)
    )
    newer = await make_breached_referral(
        "asha_a", "Dashboard Sort New", "fever", BASE - timedelta(hours=25)
    )
    await sweep(async_session_factory, SimulatedClock(BASE))

    resp = await client.get("/dashboard", headers=supervisor_auth_headers)
    ids = [r["referral_id"] for r in resp.json()["overdue"]]
    assert ids.index(str(older)) < ids.index(str(newer))


async def test_dashboard_scoped_to_callers_subtree(
    client, auth_headers, asha_b_auth_headers, make_breached_referral
):
    """Two org branches, same shape as test_org_scoping.py's pull test:
    asha_a's subtree is Village A alone, so Village B's breach must not
    appear in her dashboard, and vice versa."""
    village_a_referral = await make_breached_referral(
        "asha_a", "Dashboard Scope A", "fever", BASE - timedelta(hours=25)
    )
    village_b_referral = await make_breached_referral(
        "asha_b", "Dashboard Scope B", "fever", BASE - timedelta(hours=25)
    )
    await sweep(async_session_factory, SimulatedClock(BASE))

    resp_a = await client.get("/dashboard", headers=auth_headers)
    ids_a = {r["referral_id"] for r in resp_a.json()["overdue"]}
    assert str(village_a_referral) in ids_a
    assert str(village_b_referral) not in ids_a

    resp_b = await client.get("/dashboard", headers=asha_b_auth_headers)
    ids_b = {r["referral_id"] for r in resp_b.json()["overdue"]}
    assert str(village_b_referral) in ids_b
    assert str(village_a_referral) not in ids_b


async def test_stream_rejects_missing_or_invalid_token(client):
    resp = await client.get("/dashboard/stream")
    assert resp.status_code in (401, 422)  # 422: FastAPI's own missing-query-param response

    resp = await client.get("/dashboard/stream", params={"token": "not-a-real-token"})
    assert resp.status_code == 401


async def test_query_token_is_not_accepted_on_an_ordinary_endpoint(client, auth_headers):
    """ADR-012: the query-token form is opted into by /dashboard/stream
    alone — no shared dependency is loosened for any other route."""
    token = auth_headers["authorization"].removeprefix("Bearer ")
    resp = await client.get("/referrals", params={"token": token})
    assert resp.status_code == 401


async def test_stream_events_yields_a_snapshot_on_connect_then_a_heartbeat(supervisor_auth_headers):
    """The SSE body's actual logic, iterated directly — see stream_events's
    own docstring for why an HTTP-level test of a live connection isn't
    practical against httpx's ASGITransport. heartbeat_seconds=0 makes the
    second event arrive without a real wait."""
    _, org_unit_id = await _user("supervisor1")
    agen = stream_events(org_unit_id, SimulatedClock(BASE), heartbeat_seconds=0)
    try:
        first = await anext(agen)
        assert first.startswith("data: ")
        assert "\n\n" in first

        second = await anext(agen)
        assert second == ": heartbeat\n\n"
    finally:
        await agen.aclose()


async def test_stream_events_wakes_and_resends_a_snapshot_on_notify(supervisor_auth_headers):
    """A NOTIFY on the escalation channel — issued here directly rather
    than through a real sweep(), since only the wake-and-requery behaviour
    is under test — should produce a second snapshot event instead of a
    heartbeat, without waiting out heartbeat_seconds."""
    _, org_unit_id = await _user("supervisor1")
    agen = stream_events(org_unit_id, SimulatedClock(BASE), heartbeat_seconds=20)
    try:
        first = await anext(agen)
        assert first.startswith("data: ")

        for queue in _subscribers:
            queue.put_nowait(None)

        second = await asyncio.wait_for(anext(agen), timeout=5)
        assert second.startswith("data: ")
    finally:
        await agen.aclose()


async def test_request_timing_records_the_path_not_the_query_string(client, auth_headers):
    """ADR-012's second cost: a credential in a query string must never
    leak into our own logging or instrumentation. /dashboard/stream itself
    can't be driven far enough by this test client to reach the INSERT
    (see stream_events's docstring) — TimingMiddleware makes no per-route
    decision at all (app/instrumentation/timing.py uses request.url.path
    unconditionally), so pinning the same behaviour against /sync/pull,
    which does take query params and returns normally, proves the general
    mechanism the streaming route also relies on."""
    resp = await client.get("/sync/pull", params={"since": 0, "limit": 5}, headers=auth_headers)
    assert resp.status_code == 200

    async with async_session_factory() as session:
        row = (
            (
                await session.execute(
                    text(
                        """SELECT endpoint FROM request_timing
                       WHERE endpoint = '/sync/pull' ORDER BY id DESC LIMIT 1"""
                    )
                )
            )
            .mappings()
            .one()
        )
    assert row["endpoint"] == "/sync/pull"
    assert "since" not in row["endpoint"]
