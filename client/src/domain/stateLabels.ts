/** The event-log state names (source of truth, app/domain/states.py) and
 * the plain-language labels shown in the UI. This is the only place the two
 * vocabularies should meet — docs/design_handoff_ui_screens/README.md's
 * "State → label mapping" table, verbatim. */

export type StateFamily = "fine" | "overdue" | "done";

export interface StateLabel {
  label: string;
  family: StateFamily;
}

const STATE_LABELS: Record<string, StateLabel> = {
  CREATED: { label: "Not travelled yet", family: "fine" },
  IN_TRANSIT: { label: "On the way", family: "fine" },
  ARRIVED: { label: "Reached the centre", family: "fine" },
  TREATED: { label: "Doctor has seen her/him", family: "fine" },
  BACK_REFERRED: { label: "Sent back to you", family: "fine" },
  ESCALATED: { label: "Overdue", family: "overdue" },
  CLOSED: { label: "Care finished", family: "done" },
  LOST: { label: "No longer followed", family: "done" },
};

/** Falls back to the raw state name rather than throwing — a referral_cache
 * row can never hold a state outside app/domain/states.py's State enum
 * (the server rejects anything else before it's ever written), so this
 * fallback exists for robustness, not because it's expected to fire. */
export function stateLabel(state: string): StateLabel {
  return STATE_LABELS[state] ?? { label: state, family: "fine" };
}
