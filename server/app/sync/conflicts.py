"""The five-row conflict decision table. Plan §6.3, docs/decisions/ADR-003.md.

Pure function — no database access. Row order matters; the first matching
row wins. Assumes the referral already exists: `apply_operation` handles
"unknown_referral" and "already_exists" before calling this (ADR-003 "Gap
2" — those are not rows of this table).
"""

from dataclasses import dataclass
from typing import Literal

from app.domain.states import Role, State, is_legal, may

Decision = Literal["accepted", "accepted_stale", "conflict", "rejected"]


@dataclass(frozen=True)
class ConflictOutcome:
    status: Decision
    reason: str | None = None  # populated only when status == "rejected"


def decide(
    *,
    actor_role: Role,
    from_state: State,
    to_state: State,
    current_state: State,
    incoming_lamport: int,
    current_lamport: int,
) -> ConflictOutcome:
    # Rows 1-2: is the op coherent on its own terms, before freshness is
    # considered at all. Neither writes an event.
    if not may(actor_role, to_state):
        return ConflictOutcome("rejected", "role_not_permitted")
    if not is_legal(from_state, to_state):
        return ConflictOutcome("rejected", "illegal_transition")

    # Row 3: the device was up to date.
    if from_state == current_state:
        return ConflictOutcome("accepted")

    # Row 4: a late event — explained by the delay, not wrong.
    if incoming_lamport < current_lamport:
        return ConflictOutcome("accepted_stale")

    # Row 5: incoming_lamport > current_lamport, and — per ADR-003's "Gap
    # 1" — incoming_lamport == current_lamport too. Equal lamports means
    # neither device could have seen the other's write, which is the
    # strongest case for asking a human, not the weakest; see ADR-003 for
    # why this departs from the phase plan's suggested device_id tiebreak.
    return ConflictOutcome("conflict")
