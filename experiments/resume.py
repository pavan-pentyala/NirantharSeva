"""ADR-017 (D34): when the sweep escalates a referral, draw once against the
cell's own seeded RNG; with probability `response_rate` the referral
resumes its interrupted timeline, pushed through the real /sync/push as an
ordinary transition authored by the real role for the state it is entering
next — never a direct state write (same reasoning ADR-015 gives for the
cohort load itself).

TRANSITIONS[ESCALATED] (app/domain/states.py) already permits ESCALATED to
go straight to IN_TRANSIT/ARRIVED/TREATED/BACK_REFERRED/CLOSED/LOST — a
resumed referral's first pushed transition is `from_state="ESCALATED"`,
`to_state=<the state it would have reached next on the ordinary path>`, and
app/sync/push.py's D22 handling resolves the open escalation row in the
same transaction as that event, automatically, with no special payload.
Every step after the first is an ordinary transition, same shape
generator/timeline.py's own walk produces.

A response is modelled as guaranteed eventual closure — once "recovered",
a referral does not get a second chance to drop out. This keeps the
per-referral ADR-017 outcome binary (resumed_and_closed or stayed dropped),
which is exactly what raw.csv's resumed_and_closed column measures.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from random import Random

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clock import Clock
from app.domain.states import State
from generator.cohort import District, ReferralSpec
from generator.timeline import _ROLE_FOR, _STEPS  # deliberate reuse, see module docstring

_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "nirantharseva.experiments.resume")
DEV_PASSWORD = "dev"  # app/seed.py's own constant


def _op_id(key: str) -> uuid.UUID:
    return uuid.uuid5(_NAMESPACE, key)


def _remaining_steps(breached_state: str) -> list[tuple[str, str]]:
    """(from_state, to_state) pairs from `breached_state` to CLOSED,
    inclusive of the step that would have followed it. Raises if
    breached_state is CLOSED/LOST/ESCALATED — the sweep never breaches
    those (app/domain/escalation.py's _BREACH_QUERY excludes them)."""
    idx = next(i for i, (frm, _to, _key) in enumerate(_STEPS) if frm.value == breached_state)
    return [(frm.value, to.value) for frm, to, _key in _STEPS[idx:]]


def _user_by_org_role(district: District) -> dict[tuple[str, str], str]:
    return {(str(u.org_id), u.role): u.name for u in district.users}


@dataclass
class ResumeOutcome:
    resumed_count: int = 0
    resumed_and_closed_count: int = 0


async def _login(client: httpx.AsyncClient, username: str) -> dict:
    resp = await client.post("/auth/login", json={"username": username, "password": DEV_PASSWORD})
    resp.raise_for_status()
    return {"authorization": f"Bearer {resp.json()['access_token']}"}


async def _push_transition(
    client: httpx.AsyncClient,
    headers: dict,
    device_id: str,
    referral_id: uuid.UUID,
    from_state: str,
    to_state: str,
    lamport: int,
    device_time: datetime,
    op_key: str,
) -> str:
    op = {
        "op_id": str(_op_id(op_key)),
        "entity": "referral",
        "entity_id": str(referral_id),
        "operation": "transition",
        "payload": {"from_state": from_state, "to_state": to_state},
        "lamport": lamport,
        "device_time": device_time.isoformat(),
    }
    resp = await client.post(
        "/sync/push", json={"device_id": device_id, "ops": [op]}, headers=headers
    )
    resp.raise_for_status()
    return resp.json()["results"][0]["status"]


async def _next_lamport(
    session_factory: async_sessionmaker[AsyncSession], referral_id: uuid.UUID
) -> int:
    async with session_factory() as session:
        result = await session.execute(
            text("SELECT COALESCE(MAX(lamport), 0) FROM referral_event WHERE referral_id=:id"),
            {"id": referral_id},
        )
        return int(result.scalar_one()) + 1


def _plan_from(events: list, breached_state: str) -> list:
    """The suffix of a referral's own generated walk starting at the step
    whose from_state is `breached_state` — i.e. "what she was always going
    to do next," independent of the escalation flag. Empty if
    breached_state never appears as a from_state in `events`: that means
    generator/timeline.py's own dropout roll stopped the walk exactly
    there, so there is nothing to reconcile — this referral is a real
    drop-out, ADR-017's concern (experiments/resume.py's
    resume_escalated_referrals), not this function's."""
    for i, e in enumerate(events):
        if e.from_state == breached_state:
            return events[i:]
    return []


async def reconcile_natural_continuations(
    *,
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    cell_seed: int,
    cell_id: str,
    cohort_referral_ids: list[uuid.UUID],
    events_by_referral: dict[str, list],
    referral_by_id: dict[str, ReferralSpec],
    district: District,
) -> int:
    """Escalation flags a referral; it does not stop the ASHA/MO from
    doing the work she was always going to do. The real client never hits
    this problem — it reads current_state from its own pulled cache before
    building a transition op (D20), so a device's op always carries a live
    from_state. server/scripts/load_cohort.py's load() has no such
    awareness (P7.1 never needed it — that phase's own exit criterion is
    zero ESCALATED events before any sweep runs), so once a cohort
    referral gets escalated mid-replay, load()'s next planned event for it
    carries the *pre-escalation* from_state and push.py's coherence check
    (ADR-003) rejects it forever. Silently, too — load() only tracks
    non_accepted counts, never surfaced up to experiments/cell.py, which is
    exactly how this stayed invisible until the r=0 identity check
    (ADR-017) caught it: every escalation-on cell was closing roughly half
    of what escalation-off closed, at every dropout level and every seed.

    Unlike resume_escalated_referrals (ADR-017's probability-`r` recovery
    of a *genuine* drop-out), this is unconditional and applies to every
    cell, escalation_on or not, r=0 included — there is no response_rate
    draw, because nothing was actually interrupted. Run once, after the
    cell's simulated horizon and its final sweep, for every cohort
    referral still sitting in ESCALATED: if the generator's own walk had
    more steps planned past the breached state, push them, with the first
    one's from_state overridden to "ESCALATED" so D22 resolves the open
    escalation row as a side effect, exactly as it would for a real
    device's next honest transition. A referral with no further planned
    events is left untouched — _plan_from returns empty, so the loop below
    does nothing for it, which is correct: it really did drop out."""
    async with session_factory() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT r.id, e.breached_state FROM referral r "
                    "JOIN escalation e ON e.referral_id = r.id AND e.resolved_at IS NULL "
                    "WHERE r.id = ANY(:ids) AND r.current_state = 'ESCALATED'"
                ),
                {"ids": cohort_referral_ids},
            )
        ).all()
    if not rows:
        return 0

    user_org_role = _user_by_org_role(district)
    token_cache: dict[str, dict] = {}

    async def token_for(username: str) -> dict:
        if username not in token_cache:
            token_cache[username] = await _login(client, username)
        return token_cache[username]

    reconciled = 0
    for row in sorted(rows, key=lambda r: str(r.id)):
        referral_id = row.id
        plan = _plan_from(events_by_referral.get(str(referral_id), []), row.breached_state)
        if not plan:
            continue

        referral = referral_by_id[str(referral_id)]
        lamport = await _next_lamport(session_factory, referral_id)
        from_state = State.ESCALATED.value
        ok = True
        for e in plan:
            role = _ROLE_FOR[State(e.to_state)]
            actor = (
                referral.origin_user
                if role.value == "ASHA"
                else user_org_role[(str(referral.target_org), role.value)]
            )
            headers = await token_for(actor)
            status = await _push_transition(
                client,
                headers,
                device_id=f"reconcile-{cell_id}-{actor}",
                referral_id=referral_id,
                from_state=from_state,
                to_state=e.to_state,
                lamport=lamport,
                device_time=e.device_time,
                op_key=f"reconcile:{cell_id}:{cell_seed}:{referral_id}:{e.step}",
            )
            lamport += 1
            from_state = e.to_state
            if status != "accepted":
                ok = False
                break
        if ok:
            reconciled += 1

    return reconciled


async def resume_escalated_referrals(
    *,
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    clock: Clock,
    cell_seed: int,
    cell_id: str,
    response_rate: float,
    escalated_referral_ids: list[uuid.UUID],
    referral_by_id: dict[str, ReferralSpec],
    district: District,
) -> ResumeOutcome:
    """One RNG draw per newly-escalated referral, in a deterministic order
    (sorted by referral id, not sweep-return order — sweep()'s own list
    order is a database scan order, not seeded, and I7 needs the draw
    itself to be the only source of randomness that matters here).

    Each referral gets its OWN `Random(f"{cell_seed}:{cell_id}:resume:
    {referral_id}")` — not one shared `Random(f"{cell_seed}:{cell_id}:
    resume")` reused across referrals and across calls. This function runs
    once per sweep pass (every SWEEP_STEP_HOURS, ~1000+ times over a cell's
    horizon), and most passes see only one or two newly-escalated
    referrals — a single shared stream, freshly re-seeded from the SAME
    string on every call, hands most referrals the *identical* first draw,
    so whether a referral "succeeds" stopped depending on response_rate at
    all and started depending only on which (cell_seed, cell_id) it was in
    and how many other referrals happened to escalate in the same pass.
    Found by comparing E1's own already-committed raw.csv against a fresh
    E2 run: resumed_count was 0-or-(nearly)-all for a given (dropout, seed)
    across every response_rate, never a real ~25/50/75% split — the
    signature of this bug, not of a working probability draw. Per-referral
    keying makes each referral's draw independent of every other one and
    of how sweep passes happen to batch them, while staying exactly as
    reproducible (same seed -> same outcome) as before.

    Logs in fresh every call, never a token cached across calls — unlike
    server/scripts/load_cohort.py's own per-call token cache (which is
    naturally safe: the injected clock never advances *during* one load()
    call, so nothing cached inside it can go stale before that same call
    returns), this function is called repeatedly across a cell's entire
    simulated horizon, with the clock advancing SWEEP_STEP_HOURS between
    calls — well past JWT_EXPIRE_MINUTES's 8 (simulated) hours after only
    one step. A token cache that outlived a single call here would go
    stale mid-cell and every push after that would fail with 401, which is
    exactly what caching across calls did before this was found."""
    outcome = ResumeOutcome()
    if response_rate <= 0.0 or not escalated_referral_ids:
        return outcome

    user_org_role = _user_by_org_role(district)
    token_cache: dict[str, dict] = {}

    async def token_for(username: str) -> dict:
        if username not in token_cache:
            token_cache[username] = await _login(client, username)
        return token_cache[username]

    async with session_factory() as session:
        breach_rows = (
            await session.execute(
                text(
                    "SELECT referral_id, breached_state FROM escalation "
                    "WHERE referral_id = ANY(:ids) AND resolved_at IS NULL"
                ),
                {"ids": escalated_referral_ids},
            )
        ).all()
    breached_state_by_id = {row.referral_id: row.breached_state for row in breach_rows}

    for referral_id in sorted(escalated_referral_ids, key=str):
        breached_state = breached_state_by_id.get(referral_id)
        if breached_state is None:
            continue  # already resolved by a later step this same sweep pass -- nothing to do
        referral_rng = Random(f"{cell_seed}:{cell_id}:resume:{referral_id}")
        if not (referral_rng.random() < response_rate):
            continue

        referral = referral_by_id[str(referral_id)]
        steps = _remaining_steps(breached_state)
        lamport = await _next_lamport(session_factory, referral_id)
        device_time = clock.now()

        # First transition is from_state="ESCALATED" — resolves the open
        # escalation row (D22) — every step after that is an ordinary
        # from_state -> to_state pair from the remaining walk.
        from_state = State.ESCALATED.value
        pushed_ok = True
        for step_index, (_frm, to) in enumerate(steps):
            device_time = device_time + timedelta(hours=referral_rng.uniform(1, 12))
            role = _ROLE_FOR[State(to)]
            actor = (
                referral.origin_user
                if role.value == "ASHA"
                else user_org_role[(str(referral.target_org), role.value)]
            )
            headers = await token_for(actor)
            status = await _push_transition(
                client,
                headers,
                device_id=f"resume-{cell_id}-{actor}",
                referral_id=referral_id,
                from_state=from_state,
                to_state=to,
                lamport=lamport,
                device_time=device_time,
                op_key=f"resume:{cell_id}:{cell_seed}:{referral_id}:{step_index}",
            )
            lamport += 1
            from_state = to
            if status != "accepted":
                pushed_ok = False
                break

        if pushed_ok:
            outcome.resumed_count += 1
            if steps[-1][1] == State.CLOSED.value:
                outcome.resumed_and_closed_count += 1

    return outcome
