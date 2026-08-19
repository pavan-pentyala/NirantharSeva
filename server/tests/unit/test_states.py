"""is_legal / may across all 8 states x 5 roles, plus replay_state and
replay_steps. Plan §6.2 and §6.5, docs/decisions/ADR-003.md and
docs/decisions/ADR-008.md."""

import pytest

from app.domain.states import (
    GUARDS,
    TRANSITIONS,
    Role,
    State,
    is_legal,
    may,
    replay_state,
    replay_steps,
)

ALL_STATES = list(State)
ALL_ROLES = list(Role)


@pytest.mark.parametrize("frm", ALL_STATES)
@pytest.mark.parametrize("to", ALL_STATES)
def test_is_legal_matches_transitions_table(frm, to):
    assert is_legal(frm, to) == (to in TRANSITIONS[frm])


@pytest.mark.parametrize("role", ALL_ROLES)
@pytest.mark.parametrize("to", ALL_STATES)
def test_may_matches_guards_table(role, to):
    assert may(role, to) == (role in GUARDS[to])


@pytest.mark.parametrize("state", [State.CLOSED, State.LOST])
def test_terminal_states_have_no_outgoing_transitions(state):
    assert TRANSITIONS[state] == set()
    assert all(not is_legal(state, other) for other in ALL_STATES)


def test_escalated_returns_to_the_ordinary_path_not_a_dead_end():
    # ESCALATED is a supervisory signal, not a parallel workflow — it can
    # resume into every ordinary in-flight state, plus LOST.
    assert TRANSITIONS[State.ESCALATED] == {
        State.IN_TRANSIT,
        State.ARRIVED,
        State.TREATED,
        State.BACK_REFERRED,
        State.CLOSED,
        State.LOST,
    }


@pytest.mark.parametrize("state", [State.ESCALATED, State.LOST])
def test_only_system_may_write_escalated_or_lost(state):
    assert GUARDS[state] == {Role.SYSTEM}
    for role in ALL_ROLES:
        if role is not Role.SYSTEM:
            assert not may(role, state)


class TestReplayState:
    def test_empty_log_is_no_state(self):
        state, lamport, op_id = replay_state([])
        assert state is None
        assert lamport == 0
        assert op_id is None

    def test_single_creation_event_advances_from_none(self):
        state, lamport, op_id = replay_state([(None, State.CREATED, 5, "op-1")])
        assert state is State.CREATED
        assert lamport == 5
        assert op_id == "op-1"

    def test_a_coherent_chain_replays_to_its_end(self):
        events = [
            (None, State.CREATED, 1, "op-1"),
            (State.CREATED, State.IN_TRANSIT, 2, "op-2"),
            (State.IN_TRANSIT, State.ARRIVED, 3, "op-3"),
        ]
        state, lamport, op_id = replay_state(events)
        assert state is State.ARRIVED
        assert lamport == 3
        assert op_id == "op-3"

    def test_an_event_whose_from_state_does_not_match_is_skipped(self):
        # Exactly what rows 4/5 of the conflict table produce: appended to
        # the log, never advancing the replayed state.
        events = [
            (None, State.CREATED, 1, "op-1"),
            (State.CREATED, State.IN_TRANSIT, 2, "op-2"),
            # Stale: from_state CREATED no longer matches running state IN_TRANSIT.
            (State.CREATED, State.IN_TRANSIT, 0, "op-stale"),
        ]
        state, lamport, op_id = replay_state(events)
        assert state is State.IN_TRANSIT
        assert lamport == 2
        assert op_id == "op-2"


class TestReplaySteps:
    def test_advancement_flag_per_event_including_a_middle_non_advancer(self):
        # Same log as the skipped-event case above, but this asserts the
        # per-event flag ADR-008's timeline reads, not just the fold result.
        events = [
            (None, State.CREATED, 1, "op-1"),
            (State.CREATED, State.IN_TRANSIT, 2, "op-2"),
            (State.CREATED, State.IN_TRANSIT, 0, "op-stale"),
            (State.IN_TRANSIT, State.ARRIVED, 3, "op-3"),
        ]
        steps = list(replay_steps(events))

        assert [advanced for advanced, *_ in steps] == [True, True, False, True]

        # The non-advancing step's state/lamport/winner are the running
        # values carried over from before it — not None/0/None, and not
        # anything derived from the event that was skipped.
        assert steps[2] == (False, State.IN_TRANSIT, 2, "op-2")
        assert steps[3] == (True, State.ARRIVED, 3, "op-3")

    def test_empty_log_yields_no_steps(self):
        assert list(replay_steps([])) == []

    def test_replay_state_is_the_last_step_folded(self):
        events = [
            (None, State.CREATED, 1, "op-1"),
            (State.CREATED, State.IN_TRANSIT, 2, "op-2"),
        ]
        *_, last = replay_steps(events)
        assert replay_state(events) == last[1:]
