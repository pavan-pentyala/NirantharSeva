import { db, type ReferralEventCacheRow } from "../db/schema";

/** D20 (docs/PHASE5_PLAN.md): current_state becomes "ESCALATED" and the
 * state it was breached from is gone from that column — but the design
 * shows escalation as an overlay on the real state, not a replacement
 * (docs/design_handoff_ui_screens/README.md's "State → label mapping":
 * "the row keeps its real state label and gains the red pill + bar").
 * The real state is recoverable without a wire change: it's the from_state
 * of the most recent cached event whose to_state is "ESCALATED" — already
 * folded into referral_event_cache by P4.2's applyPulledReferralEvent.
 * Falls back to currentState itself if, for any reason, no such event is
 * cached yet (a pull still in flight) — never renders a blank state. */
export function displayStateFromEvents(
  currentState: string,
  events: Pick<ReferralEventCacheRow, "from_state" | "to_state">[],
): string {
  if (currentState !== "ESCALATED") return currentState;
  for (let i = events.length - 1; i >= 0; i--) {
    if (events[i].to_state === "ESCALATED") return events[i].from_state ?? currentState;
  }
  return currentState;
}

/** Batch form for list screens (1 and 5), which hold many referrals'
 * current_state but not their event logs — one query for every escalated
 * referral's events at once, not one query per row. Only escalated
 * referrals are looked up; everyone else's display state is just their
 * own current_state, unconditionally. */
export async function displayStatesFor(
  referrals: { id: string; current_state: string }[],
): Promise<Map<string, string>> {
  const escalatedIds = referrals.filter((r) => r.current_state === "ESCALATED").map((r) => r.id);
  const result = new Map<string, string>();
  if (escalatedIds.length === 0) return result;

  const events = await db.referral_event_cache
    .where("referral_id")
    .anyOf(escalatedIds)
    .and((e) => e.to_state === "ESCALATED")
    .toArray();

  const latestSeq = new Map<string, number>();
  for (const e of events) {
    const seen = latestSeq.get(e.referral_id);
    if (seen === undefined || e.seq > seen) {
      latestSeq.set(e.referral_id, e.seq);
      result.set(e.referral_id, e.from_state ?? "CREATED");
    }
  }
  return result;
}
