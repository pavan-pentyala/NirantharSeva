"""Per-referral state walks with per-stage dropout. docs/PHASE7_PLAN.md
P7.1 build order #4.

**Never emits an ESCALATED event.** Escalation is the sweep's job
(app/domain/escalation.py), authored by Role.SYSTEM — a cohort that ships
its own escalations would answer E1's "does escalation recover a dropped
referral" question in the input file. This module only ever walks the
ordinary path CREATED -> IN_TRANSIT -> ARRIVED -> TREATED -> BACK_REFERRED
-> CLOSED, stopping early on a dropout roll. A dropped referral simply has
no further rows — not a LOST event either, since LOST is also
Role.SYSTEM-only (app/domain/states.py GUARDS).

No datetime.now() — device_time is the referral's own created_device_time
plus generated dwell offsets, all seeded from `seed`.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from random import Random

from app.domain.states import GUARDS, TRANSITIONS, Role, State
from generator.cohort import Cohort, ReferralSpec

# Ordinary path only — ESCALATED and LOST are excluded on purpose (see
# module docstring). Each entry: (from_state, to_state, dropout_key).
# dropout_key indexes config["dropout_rate"]: the probability that a
# referral which has just ENTERED from_state never makes this transition.
_STEPS: list[tuple[State, State, str]] = [
    (State.CREATED, State.IN_TRANSIT, "CREATED"),
    (State.IN_TRANSIT, State.ARRIVED, "IN_TRANSIT"),
    (State.ARRIVED, State.TREATED, "ARRIVED"),
    (State.TREATED, State.BACK_REFERRED, "TREATED"),
    (State.BACK_REFERRED, State.CLOSED, "BACK_REFERRED"),
]
for _frm, _to, _ in _STEPS:
    assert _to in TRANSITIONS[_frm], f"{_frm} -> {_to} is not a legal transition"
    assert _to != State.ESCALATED, "the generator must never emit ESCALATED"

# Actor role per to_state, taken from the real GUARDS table so this module
# can never drift from what app/domain/states.py actually permits.
_ROLE_FOR: dict[State, Role] = {
    State.IN_TRANSIT: Role.ASHA,  # GUARDS[IN_TRANSIT] = {ASHA, ANM}; ASHA is always valid
    State.ARRIVED: Role.MO,
    State.TREATED: Role.MO,
    State.BACK_REFERRED: Role.MO,
    State.CLOSED: Role.ASHA,
}
for _state, _role in _ROLE_FOR.items():
    assert _role in GUARDS[_state], f"{_role} is not permitted to write {_state}"

# D33: device -> server push delay distribution, per connectivity_profile.
# Not swept by any of E1-E6 (§13.2) — a realism knob, seconds held offline
# before the device gets a chance to push.
_DELAY_RANGES: dict[str, list[tuple[float, float, float]]] = {
    # (probability, low_seconds, high_seconds) — probabilities sum to 1.0
    "always_online": [(1.0, 0, 60)],
    "intermittent": [(0.8, 0, 300), (0.2, 3600, 12 * 3600)],
    "poor": [(0.6, 1800, 6 * 3600), (0.4, 86400, 3 * 86400)],
}


@dataclass(frozen=True)
class EventRow:
    referral_id: uuid.UUID
    step: int
    from_state: str
    to_state: str
    actor_role: str
    device_time: datetime
    push_delay_seconds: int


def _push_delay(rng: Random, profile: str) -> int:
    buckets = _DELAY_RANGES[profile]
    roll = rng.random()
    cumulative = 0.0
    for prob, low, high in buckets:
        cumulative += prob
        if roll <= cumulative:
            return int(rng.uniform(low, high))
    prob, low, high = buckets[-1]
    return int(rng.uniform(low, high))


def _walk_one(rng: Random, referral: ReferralSpec, config: dict) -> list[EventRow]:
    dropout_rate = config["dropout_rate"]
    profile = config["connectivity_profile"]

    events: list[EventRow] = []
    device_time = referral.created_device_time
    for step, (frm, to, dropout_key) in enumerate(_STEPS, start=1):
        if rng.random() < dropout_rate[dropout_key]:
            break  # dropped at `frm` — no further rows for this referral
        dwell_hours = rng.uniform(1, 36)
        device_time = device_time + timedelta(hours=dwell_hours)
        events.append(
            EventRow(
                referral_id=referral.referral_id,
                step=step,
                from_state=frm.value,
                to_state=to.value,
                actor_role=_ROLE_FOR[to].value,
                device_time=device_time,
                push_delay_seconds=_push_delay(rng, profile),
            )
        )
    return events


def build_events(seed: int, config: dict, cohort: Cohort) -> list[EventRow]:
    """One independent RNG stream per call, seeded from `seed` — pure and
    deterministic, same discipline as generator/cohort.py's builders."""
    rng = Random(seed + 3)
    events: list[EventRow] = []
    for referral in cohort.referrals:
        events.extend(_walk_one(rng, referral, config))
    return events
