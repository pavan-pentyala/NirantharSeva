"""app/domain/escalation.py's sweep(). docs/PHASE5_PLAN.md P5.1 — "What
P5.1 must prove", mapped one test per row.

Referrals are inserted directly with a controlled state_entered_at, bypassing
/sync/push (the same device test_replay_verifier.py's zero-event test uses)
— the sweep does not care how a referral got into a state, only how long it
has sat there. sweep() takes an explicit Clock, decoupled from whatever
clock_mode the running container uses, so every test here controls "now"
exactly rather than racing real wall-clock time.

Every direct-inserted referral here has a cache (current_state) with no
event log behind it — deliberately, to control state and age independent of
a real state machine walk. That is exactly the "zero_events" shape
test_replay_verifier.py's own test asserts I3 catches, so the make_referral
fixture deletes what it creates once each test ends (referral_event first,
then escalation, then referral — FK order), the same way that test's
corrupted-cache case restores itself in a finally block. Left behind, a
zero-event referral would fail test_replay_verifier.py's whole-database
check the next time it runs in this session.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app.clock import SimulatedClock
from app.config import Settings
from app.db import async_session_factory
from app.domain.escalation import sweep
from app.verify_replay import verify_all

BASE = datetime(2026, 8, 20, 0, 0, tzinfo=UTC)


async def _asha_a():
    async with async_session_factory() as session:
        row = (
            await session.execute(
                text("SELECT id, org_unit_id FROM app_user WHERE name = 'asha_a'")
            )
        ).one()
        return row.id, row.org_unit_id


async def _insert_patient(session, patient_id, now):
    await session.execute(
        text(
            """INSERT INTO patient (id, name, normalized_name, created_at)
               VALUES (:id, 'Sweep Test Patient', 'sweep test patient', :now)"""
        ),
        {"id": patient_id, "now": now},
    )


async def _insert_referral(
    session, referral_id, patient_id, origin_user_id, org_id, state, state_entered_at
):
    await session.execute(
        text(
            """INSERT INTO referral
                 (id, patient_id, origin_user_id, origin_org_id, target_org_id,
                  reason, priority, current_state, state_entered_at,
                  sla_profile_id, created_device_time, created_server_time)
               VALUES
                 (:id, :patient_id, :user_id, :org_id, :org_id,
                  'fever', 'normal', :state, :state_entered_at,
                  NULL, :state_entered_at, :state_entered_at)"""
        ),
        {
            "id": referral_id,
            "patient_id": patient_id,
            "user_id": origin_user_id,
            "org_id": org_id,
            "state": state,
            "state_entered_at": state_entered_at,
        },
    )


@pytest.fixture
async def make_referral():
    """Factory fixture: make_referral(state, state_entered_at) -> referral_id,
    owned by asha_a. Deletes every referral it created once the test ends —
    see the module docstring for why that cleanup matters here."""
    created: list[uuid.UUID] = []

    async def _factory(state: str, state_entered_at: datetime) -> uuid.UUID:
        origin_user_id, org_id = await _asha_a()
        referral_id = uuid.uuid4()
        patient_id = uuid.uuid4()
        async with async_session_factory() as session, session.begin():
            await _insert_patient(session, patient_id, state_entered_at)
            await _insert_referral(
                session, referral_id, patient_id, origin_user_id, org_id, state, state_entered_at
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


async def _referral_state(referral_id) -> str:
    async with async_session_factory() as session:
        row = (
            await session.execute(
                text("SELECT current_state FROM referral WHERE id=:id"), {"id": referral_id}
            )
        ).one()
        return row.current_state


async def _escalation_rows(referral_id):
    async with async_session_factory() as session:
        return (
            await session.execute(
                text(
                    """SELECT breached_state, resolved_at, sla_profile_version
                       FROM escalation WHERE referral_id=:id ORDER BY triggered_at"""
                ),
                {"id": referral_id},
            )
        ).all()


async def _escalated_events(referral_id):
    async with async_session_factory() as session:
        return (
            await session.execute(
                text(
                    """SELECT from_state, to_state, actor_role, actor_user_id, device_id, lamport
                       FROM referral_event
                       WHERE referral_id=:id AND to_state='ESCALATED'
                       ORDER BY seq"""
                ),
                {"id": referral_id},
            )
        ).all()


async def test_breached_referral_is_escalated(make_referral):
    referral_id = await make_referral("CREATED", BASE - timedelta(hours=25))  # SLA: 24h
    clock = SimulatedClock(BASE)

    escalated = await sweep(async_session_factory, clock)

    assert referral_id in escalated
    assert await _referral_state(referral_id) == "ESCALATED"

    rows = await _escalation_rows(referral_id)
    assert len(rows) == 1
    assert rows[0].breached_state == "CREATED"
    assert rows[0].resolved_at is None
    assert rows[0].sla_profile_version == 1

    events = await _escalated_events(referral_id)
    assert len(events) == 1
    ev = events[0]
    assert ev.from_state == "CREATED"
    assert ev.actor_role == "SYSTEM"
    assert ev.actor_user_id is None
    assert ev.device_id == "scheduler"


async def test_within_sla_referral_is_untouched(make_referral):
    referral_id = await make_referral("CREATED", BASE - timedelta(hours=1))  # SLA: 24h
    clock = SimulatedClock(BASE)

    escalated = await sweep(async_session_factory, clock)

    assert referral_id not in escalated
    assert await _referral_state(referral_id) == "CREATED"
    assert await _escalation_rows(referral_id) == []


@pytest.mark.parametrize("state", ["CLOSED", "LOST", "ESCALATED"])
async def test_dead_or_already_escalated_referrals_are_skipped(state, make_referral):
    # Far past its SLA window under any profile — the exclusion has to come
    # from current_state, not from happening to still be within the window.
    referral_id = await make_referral(state, BASE - timedelta(days=30))
    clock = SimulatedClock(BASE)

    escalated = await sweep(async_session_factory, clock)

    assert referral_id not in escalated
    assert await _referral_state(referral_id) == state
    assert await _escalation_rows(referral_id) == []


async def test_two_sweeps_over_the_same_open_breach_produce_one_row_one_event(make_referral):
    """I5. The escalation row from the first sweep is deliberately left
    open (resolved_at IS NULL) and current_state is reverted by hand to
    look unescalated again — standing in for two writers racing the same
    breach — before sweeping a second time. sweep()'s own pre-check (the
    "re-check under the lock" read) does NOT catch this, because it only
    compares current_state to the breached_state it expects, and the
    revert below makes that comparison pass. What actually stops the
    duplicate is uq_escalation_open — the ON CONFLICT ... RETURNING gate in
    app/domain/escalation.py. Delete that pre-check entirely and this test
    still passes; it exercises no Python guard against a re-run."""
    referral_id = await make_referral("CREATED", BASE - timedelta(hours=25))
    clock = SimulatedClock(BASE)

    first = await sweep(async_session_factory, clock)
    assert referral_id in first

    async with async_session_factory() as session, session.begin():
        await session.execute(
            text("UPDATE referral SET current_state='CREATED' WHERE id=:id"), {"id": referral_id}
        )

    second = await sweep(async_session_factory, clock)
    assert referral_id not in second

    rows = await _escalation_rows(referral_id)
    assert len(rows) == 1
    events = await _escalated_events(referral_id)
    assert len(events) == 1


async def test_resolution_on_exit_and_rebreach_creates_a_second_row(
    client, auth_headers, make_referral
):
    """D22. Escalate IN_TRANSIT, resolve it by pushing ESCALATED -> IN_TRANSIT
    (a legal move — states.py's ESCALATED transitions return to the state
    that breached, not just forward), let it stall in IN_TRANSIT again, and
    sweep a second time. Also a regression check on the swept event's op_id:
    a formula keyed only on (referral, breached_state) would collide with
    the first escalation's op_id here, since both breaches are IN_TRANSIT —
    the second event would either fail to insert or crash the sweep. It
    doesn't, because the op_id also incorporates triggered_at."""
    referral_id = await make_referral("IN_TRANSIT", BASE - timedelta(hours=50))  # SLA: 48h
    clock = SimulatedClock(BASE)

    await sweep(async_session_factory, clock)
    assert await _referral_state(referral_id) == "ESCALATED"

    resp = await client.post(
        "/sync/push",
        json={
            "device_id": "d-asha",
            "ops": [
                {
                    "op_id": str(uuid.uuid4()),
                    "entity": "referral",
                    "entity_id": str(referral_id),
                    "operation": "transition",
                    "payload": {"from_state": "ESCALATED", "to_state": "IN_TRANSIT"},
                    "lamport": 1000,
                    "device_time": BASE.isoformat(),
                }
            ],
        },
        headers=auth_headers,
    )
    assert resp.json()["results"][0]["status"] == "accepted"

    rows = await _escalation_rows(referral_id)
    assert len(rows) == 1
    assert rows[0].resolved_at is not None  # D22

    # Stalls in IN_TRANSIT again, long enough to re-breach the same state.
    later = BASE + timedelta(days=1)
    async with async_session_factory() as session, session.begin():
        await session.execute(
            text("UPDATE referral SET state_entered_at=:t WHERE id=:id"),
            {"t": later - timedelta(hours=50), "id": referral_id},
        )

    second_clock = SimulatedClock(later)
    escalated = await sweep(async_session_factory, second_clock)
    assert referral_id in escalated

    rows = await _escalation_rows(referral_id)
    assert len(rows) == 2
    assert sum(1 for r in rows if r.resolved_at is None) == 1
    assert all(r.breached_state == "IN_TRANSIT" for r in rows)

    events = await _escalated_events(referral_id)
    assert len(events) == 2  # not silently dropped by an op_id collision


async def test_sweep_honours_the_injected_clock(make_referral):
    referral_id = await make_referral("CREATED", BASE)  # entered right at "now"
    clock = SimulatedClock(BASE)

    assert referral_id not in await sweep(async_session_factory, clock)
    assert await _referral_state(referral_id) == "CREATED"

    clock.advance(hours=25)  # past the 24h CREATED SLA
    assert referral_id in await sweep(async_session_factory, clock)
    assert await _referral_state(referral_id) == "ESCALATED"


async def test_sla_scale_shrinks_the_window(monkeypatch, make_referral):
    # Real-hours window untouched (D17) — only the sweep's own read of it is
    # scaled. 1 second old is nowhere near 24 real hours, but is well past
    # a 24h window scaled down to a fraction of a second.
    referral_id = await make_referral("CREATED", BASE - timedelta(seconds=1))
    monkeypatch.setattr("app.domain.escalation.get_settings", lambda: Settings(sla_scale=0.0001))
    clock = SimulatedClock(BASE)

    escalated = await sweep(async_session_factory, clock)

    assert referral_id in escalated


async def test_verify_replay_is_clean_after_a_sweep(client, auth_headers, mo_auth_headers):
    """Unlike the other tests here, this referral needs a real event log
    behind it — a direct-inserted row with no CREATED/IN_TRANSIT/ARRIVED
    events would report a mismatch on its own (the same shape
    test_replay_verifier.py's zero-event test asserts deliberately), which
    would make this test pass for the wrong reason."""
    referral_id = uuid.uuid4()
    patient_id = uuid.uuid4()
    async with async_session_factory() as session, session.begin():
        await _insert_patient(session, patient_id, BASE)

    device_time = BASE.isoformat()

    async def _push(headers, device_id, op_id, entity_id, operation, payload, lamport):
        resp = await client.post(
            "/sync/push",
            json={
                "device_id": device_id,
                "ops": [
                    {
                        "op_id": str(op_id),
                        "entity": "referral",
                        "entity_id": str(entity_id),
                        "operation": operation,
                        "payload": payload,
                        "lamport": lamport,
                        "device_time": device_time,
                    }
                ],
            },
            headers=headers,
        )
        assert resp.json()["results"][0]["status"] == "accepted", resp.json()

    await _push(
        auth_headers,
        "d-asha",
        uuid.uuid4(),
        referral_id,
        "create_referral",
        {"patient_id": str(patient_id), "reason": "fever", "priority": "normal"},
        1,
    )
    await _push(
        auth_headers,
        "d-asha",
        uuid.uuid4(),
        referral_id,
        "transition",
        {"from_state": "CREATED", "to_state": "IN_TRANSIT"},
        2,
    )
    await _push(
        mo_auth_headers,
        "d-mo",
        uuid.uuid4(),
        referral_id,
        "transition",
        {"from_state": "IN_TRANSIT", "to_state": "ARRIVED"},
        3,
    )

    async with async_session_factory() as session, session.begin():
        await session.execute(
            text("UPDATE referral SET state_entered_at=:t WHERE id=:id"),
            {"t": BASE - timedelta(hours=25), "id": referral_id},  # SLA: 24h
        )

    clock = SimulatedClock(BASE)
    escalated = await sweep(async_session_factory, clock)
    assert referral_id in escalated

    report = await verify_all()
    mismatch = next((m for m in report.mismatches if m.referral_id == referral_id), None)
    assert mismatch is None, mismatch
