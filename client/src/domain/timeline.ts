import type { ReferralEventCacheRow } from "../db/schema";

const TO_STATE_LABEL: Record<string, string> = {
  CREATED: "Referral created",
  IN_TRANSIT: "Sent — On the way",
  ARRIVED: "Reached the centre",
  TREATED: "Doctor has seen the patient",
  BACK_REFERRED: "Sent back to the ASHA",
  CLOSED: "Care finished",
  LOST: "No longer followed",
  ESCALATED: "Marked overdue — supervisor told",
};

export function timelineEntryLabel(event: ReferralEventCacheRow): string {
  return TO_STATE_LABEL[event.to_state] ?? event.to_state;
}

const ROLE_ATTRIBUTION: Record<string, string> = {
  ASHA: "the ASHA",
  ANM: "the ANM",
  MO: "the MO",
  SUPERVISOR: "the supervisor",
  SYSTEM: "the system",
};

/** No display name is available client-side for any actor but the one
 * logged in (and even that one isn't — the JWT carries a username, not a
 * display_name; see PROGRESS.md's P4.2 session notes). Attributed by role
 * instead of "by you, <name>" as the mockup shows. */
export function timelineAttribution(event: ReferralEventCacheRow): string {
  return `by ${ROLE_ATTRIBUTION[event.actor_role] ?? event.actor_role}`;
}

export function timelineTimestamp(iso: string): string {
  const d = new Date(iso);
  const time = d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }).toLowerCase();
  const diffDays = Math.floor((Date.now() - d.getTime()) / 86_400_000);
  if (diffDays <= 0) return `Today, ${time}`;
  if (diffDays === 1) return `Yesterday, ${time}`;
  return `${diffDays} days ago, ${time}`;
}
