"""The referral state machine. Plan §6.2, quoted in Chapter 3.

No database imports. No framework imports. Nothing but enums, dicts, and
one replay function — this is the module unit-tested hardest.
"""

from collections.abc import Iterable, Iterator
from enum import StrEnum


class State(StrEnum):
    CREATED = "CREATED"
    IN_TRANSIT = "IN_TRANSIT"
    ARRIVED = "ARRIVED"
    TREATED = "TREATED"
    BACK_REFERRED = "BACK_REFERRED"
    CLOSED = "CLOSED"
    ESCALATED = "ESCALATED"
    LOST = "LOST"


class Role(StrEnum):
    ASHA = "ASHA"
    ANM = "ANM"
    MO = "MO"
    SUPERVISOR = "SUPERVISOR"
    SYSTEM = "SYSTEM"  # D2 — app_user.role is never SYSTEM, by convention


TRANSITIONS: dict[State, set[State]] = {
    State.CREATED: {State.IN_TRANSIT, State.ESCALATED},
    State.IN_TRANSIT: {State.ARRIVED, State.ESCALATED},
    State.ARRIVED: {State.TREATED, State.ESCALATED},
    State.TREATED: {State.BACK_REFERRED, State.ESCALATED},
    State.BACK_REFERRED: {State.CLOSED, State.ESCALATED},
    # ESCALATED returns to the ordinary path — a supervisory signal, not a
    # parallel workflow. breached_state on the escalation row (Phase 5) is
    # what lets the referral resume rather than restart.
    State.ESCALATED: {
        State.IN_TRANSIT,
        State.ARRIVED,
        State.TREATED,
        State.BACK_REFERRED,
        State.CLOSED,
        State.LOST,
    },
    State.CLOSED: set(),
    State.LOST: set(),
}

GUARDS: dict[State, set[Role]] = {
    State.CREATED: {Role.ASHA, Role.ANM},
    State.IN_TRANSIT: {Role.ASHA, Role.ANM},
    State.ARRIVED: {Role.MO},
    State.TREATED: {Role.MO},
    State.BACK_REFERRED: {Role.MO},
    State.CLOSED: {Role.ASHA},
    State.ESCALATED: {Role.SYSTEM},  # no human role can write this transition
    State.LOST: {Role.SYSTEM},
}


def is_legal(frm: State, to: State) -> bool:
    return to in TRANSITIONS[frm]


def may(role: Role, to: State) -> bool:
    return role in GUARDS[to]


def replay_steps(
    events: Iterable[tuple[State | None, State, int, str]],
) -> Iterator[tuple[bool, State | None, int, str | None]]:
    """Per event, in input order: (advanced, state_after, lamport_after,
    winning_op_id_after) — the fold I3 and the timeline both rest on.

    An event advances the running state only when its from_state matches
    the state so far — exactly row 3 of the conflict table
    (docs/decisions/ADR-003.md). Rows 4/5 (accepted_stale/conflict) are
    present in the log but never advance the state, and rows 1/2 write no
    event at all — so this single condition reproduces the same state the
    live conflict decisions produced, without needing an "accepted" flag
    stored anywhere. The very first event has from_state=None, matching the
    initial running state of None, so referral creation needs no special
    case here.

    This is the fold I3 rests on: current_state is always derivable by
    replaying the event log. replay_state (below) folds this to a single
    end result; app/verify_replay.py and the referral timeline endpoint
    consume the per-event flag directly, so neither has to re-derive the
    advancement rule on its own — see docs/decisions/ADR-008.md, whose
    exit criterion is that this rule appears exactly once under app/.
    """
    state: State | None = None
    lamport = 0
    winning_op_id: str | None = None
    for frm, to, ev_lamport, op_id in events:
        advanced = frm == state
        if advanced:
            state, lamport, winning_op_id = to, ev_lamport, op_id
        yield advanced, state, lamport, winning_op_id


def replay_state(
    events: Iterable[tuple[State | None, State, int, str]],
) -> tuple[State | None, int, str | None]:
    """Reconstruct (current_state, current_lamport, winning_op_id) by
    replaying an ordered (seq ASC) sequence of
    (from_state, to_state, lamport, op_id) events. A thin fold over
    replay_steps — see its docstring for the rule.

    apply_operation calls this before every transition to find "the
    current lamport"; python -m app.verify_replay calls it to verify the
    cache against the log independently, over every referral in the
    database.
    """
    result: tuple[State | None, int, str | None] = (None, 0, None)
    for _advanced, state, lamport, winning_op_id in replay_steps(events):
        result = (state, lamport, winning_op_id)
    return result
