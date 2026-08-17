"""One test per row of the five-row conflict decision table, plus the
lamport-equality tiebreak. Plan §6.3, docs/decisions/ADR-003.md."""

from app.domain.states import Role, State
from app.sync.conflicts import decide


def test_row1_role_not_permitted_is_rejected():
    # ASHA may create/IN_TRANSIT, never ARRIVED (that's MO's).
    outcome = decide(
        actor_role=Role.ASHA,
        from_state=State.IN_TRANSIT,
        to_state=State.ARRIVED,
        current_state=State.IN_TRANSIT,
        incoming_lamport=5,
        current_lamport=5,
    )
    assert outcome.status == "rejected"
    assert outcome.reason == "role_not_permitted"


def test_row2_illegal_transition_is_rejected():
    # CLOSED has no outgoing transitions at all.
    outcome = decide(
        actor_role=Role.ASHA,
        from_state=State.CLOSED,
        to_state=State.IN_TRANSIT,
        current_state=State.CLOSED,
        incoming_lamport=5,
        current_lamport=5,
    )
    assert outcome.status == "rejected"
    assert outcome.reason == "illegal_transition"


def test_row1_checked_before_row2_when_both_would_fire():
    # Role-permission is checked first, regardless of transition legality —
    # ADR-003: rows 1-2 both ask whether the op is coherent on its own
    # terms, in that order.
    outcome = decide(
        actor_role=Role.ASHA,
        from_state=State.CLOSED,  # also illegal (row 2 would also fire)
        to_state=State.ARRIVED,  # ASHA may never write ARRIVED (row 1)
        current_state=State.CLOSED,
        incoming_lamport=5,
        current_lamport=5,
    )
    assert outcome.status == "rejected"
    assert outcome.reason == "role_not_permitted"


def test_row3_from_state_matches_current_is_accepted():
    outcome = decide(
        actor_role=Role.ASHA,
        from_state=State.CREATED,
        to_state=State.IN_TRANSIT,
        current_state=State.CREATED,
        incoming_lamport=5,
        current_lamport=3,
    )
    assert outcome.status == "accepted"


def test_row4_stale_lamport_is_accepted_stale():
    outcome = decide(
        actor_role=Role.MO,
        from_state=State.IN_TRANSIT,  # already moved on
        to_state=State.ARRIVED,
        current_state=State.ARRIVED,
        incoming_lamport=2,
        current_lamport=5,
    )
    assert outcome.status == "accepted_stale"


def test_row5_newer_lamport_disagreeing_with_current_is_conflict():
    outcome = decide(
        actor_role=Role.MO,
        from_state=State.IN_TRANSIT,
        to_state=State.ARRIVED,
        current_state=State.ARRIVED,  # someone else already moved it on
        incoming_lamport=9,
        current_lamport=5,
    )
    assert outcome.status == "conflict"


def test_equal_lamport_disagreeing_with_current_is_conflict_not_a_device_id_tiebreak():
    # ADR-003 "Gap 1": the plan's table is silent on lamport ==. Equal
    # lamports proves neither device saw the other's write — the strongest
    # case for asking a human, not the weakest. This departs from the phase
    # plan's suggested device_id tiebreak; see ADR-003 for the reasoning.
    outcome = decide(
        actor_role=Role.MO,
        from_state=State.IN_TRANSIT,
        to_state=State.ARRIVED,
        current_state=State.ARRIVED,
        incoming_lamport=5,
        current_lamport=5,
    )
    assert outcome.status == "conflict"
