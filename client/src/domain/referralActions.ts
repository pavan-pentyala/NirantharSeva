/** The one action a role may take on a referral right now, if any — derived
 * from app/domain/states.py's GUARDS, not from the design mockup's button
 * copy. Screen 3's mockup shows the ASHA "Mark as arrived" (ARRIVED is
 * MO-only) and "mark as lost" (LOST is SYSTEM-only, no human role at all);
 * both were confirmed with the user as design/architecture conflicts and
 * dropped rather than built — see PROGRESS.md's P4.2 session notes. */

export interface ReferralAction {
  toState: string;
  buttonLabel: string;
}

const ASHA_ACTIONS: Partial<Record<string, ReferralAction>> = {
  CREATED: { toState: "IN_TRANSIT", buttonLabel: "Mark as sent" },
  BACK_REFERRED: { toState: "CLOSED", buttonLabel: "Mark as care finished" },
};

const ASHA_WAITING_COPY: Partial<Record<string, string>> = {
  IN_TRANSIT: "Waiting for the centre to confirm arrival.",
  ARRIVED: "Waiting for the doctor to see the patient.",
  TREATED: "Waiting for the centre to send the patient back.",
  ESCALATED: "The supervisor has been told. Waiting for an update.",
};

export function ashaActionFor(currentState: string): ReferralAction | null {
  return ASHA_ACTIONS[currentState] ?? null;
}

/** Shown instead of a button when the ASHA has no legal next action —
 * reuses the design's own "Waiting for: ..." pattern rather than leaving
 * an empty footer. */
export function ashaWaitingCopyFor(currentState: string): string | null {
  return ASHA_WAITING_COPY[currentState] ?? null;
}

const MO_ACTIONS: Partial<Record<string, ReferralAction>> = {
  IN_TRANSIT: { toState: "ARRIVED", buttonLabel: "Arrived" },
  ARRIVED: { toState: "TREATED", buttonLabel: "Treated" },
  TREATED: { toState: "BACK_REFERRED", buttonLabel: "Sent back to ASHA" },
};

export function moActionFor(currentState: string): ReferralAction | null {
  return MO_ACTIONS[currentState] ?? null;
}
