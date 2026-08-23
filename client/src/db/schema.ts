import Dexie, { type Table } from "dexie";

export type OutboxStatus = "pending" | "inflight" | "synced" | "conflict" | "rejected";

export interface OutboxOp {
  op_id: string;
  entity: string;
  entity_id: string;
  operation: string;
  payload: Record<string, unknown>;
  lamport: number;
  device_time: string;
  status: OutboxStatus;
  next_retry_at?: number;
  attempts?: number;
}

export interface SyncMetaRow {
  key: string;
  value: string | number;
}

/** Local cache of a referral's current state and the snapshot fields the
 * screens render (ADR-010) — built entirely by folding pulled events
 * (client/src/sync/engine.ts's applyPulledEvents). Only an advancing
 * pulled step writes here; a losing or stale event still updates its
 * outbox record but never this table (D14). */
export interface ReferralCacheRow {
  id: string;
  current_state: string;
  patient_name: string;
  age: number | null;
  sex: string | null;
  reason: string | null;
  priority: string | null;
  target_org_name: string | null;
  lamport: number;
  device_id: string;
  updated_at: string;
}

/** Declared for Phase 4.1 (D14's build order names it alongside
 * referral_cache) but not written by anything yet: /sync/pull's referral
 * payload carries a patient snapshot, not a patient_id (ADR-010), so there
 * is no key to cache pulled patient rows under. Left empty until a phase
 * gives the wire protocol a reason to carry one. */
export interface PatientCacheRow {
  id: string;
  name: string;
  age: number | null;
  sex: string | null;
  phone: string | null;
  village_org_id: string;
}

/** P4.2: one row per *advancing* pulled referral event — Screen 3's "What
 * happened" timeline reads only from here, never a live API call (brief
 * §8: the interface reads only from the local cache). Losing/stale events
 * are deliberately not cached here, same as they're not folded into
 * referral_cache (D14) — the design's timeline never shows them either.
 * actor_user_id is nullable since P5.1 (docs/PHASE5_PLAN.md "Traps"): a
 * SYSTEM-authored escalation event has no acting user. */
export interface ReferralEventCacheRow {
  seq: number;
  referral_id: string;
  from_state: string | null;
  to_state: string;
  actor_role: string;
  actor_user_id: string | null;
  device_time: string;
  server_time: string;
}

/** P4.2: org names/hierarchy (app/api/org_units.py) — not patient data,
 * fetched once and cached rather than re-fetched per screen. Refreshed
 * opportunistically after login; stale org names are a cosmetic risk, not
 * a correctness one (the org tree is effectively static demo fixture data
 * this phase). */
export interface OrgCacheRow {
  id: string;
  name: string;
  type: string;
  parent_id: string | null;
}

/** P5.2: Screen 4's stat strip, written by client/src/sync/dashboardStream.ts
 * on every SSE message — a single row under the fixed key "current", the
 * same one-row-table pattern app/db/meta.ts's sync_meta already uses.
 * Mirrors app/schemas/dashboard.py's DashboardStats field-for-field. */
export interface DashboardStatsCacheRow {
  key: "current";
  open: number;
  on_the_way: number;
  reached_centre: number;
  treated_or_sent_back: number;
  overdue: number;
  closed_this_month: number;
  updated_at: string;
}

/** P5.2: Screen 4's overdue list, one row per open escalation — replaced
 * wholesale on every SSE message (dashboardStream.ts clears and rewrites
 * the whole table, never a partial patch), since the server always sends
 * the full current snapshot, not a diff (docs/decisions/ADR-011.md: a
 * notification is a signal, and every subscriber re-runs its own query —
 * this table is that query's result, cached). */
export interface DashboardOverdueCacheRow {
  escalation_id: string;
  referral_id: string;
  patient_name: string;
  village_name: string | null;
  target_org_name: string | null;
  reason: string | null;
  asha_name: string | null;
  asha_phone: string | null;
  triggered_at: string;
}

/** P6.2: Screen 6's queue — fetched over REST (never SSE, ADR-013),
 * written wholesale on every fetch/refetch, read only from here (brief
 * §8). Mirrors app/schemas/identity.py's IdentityReviewRow field-for-field,
 * nested patient snapshots included — Dexie stores them as-is, no need to
 * flatten since nothing indexes into them. */
export interface IdentityReviewPatientSnapshot {
  id: string;
  name: string;
  age: number | null;
  sex: string | null;
  phone: string | null;
  village_name: string | null;
  last_seen_reason: string | null;
  last_seen_at: string | null;
}

export interface IdentityReviewCacheRow {
  id: string;
  score: number;
  method: string;
  created_at: string;
  existing: IdentityReviewPatientSnapshot;
  new: IdentityReviewPatientSnapshot;
}

class NirantharSevaDB extends Dexie {
  outbox!: Table<OutboxOp, string>;
  sync_meta!: Table<SyncMetaRow, string>;
  referral_cache!: Table<ReferralCacheRow, string>;
  patient_cache!: Table<PatientCacheRow, string>;
  referral_event_cache!: Table<ReferralEventCacheRow, number>;
  org_cache!: Table<OrgCacheRow, string>;
  dashboard_stats_cache!: Table<DashboardStatsCacheRow, string>;
  dashboard_overdue_cache!: Table<DashboardOverdueCacheRow, string>;
  identity_review_cache!: Table<IdentityReviewCacheRow, string>;

  constructor() {
    super("nirantharseva");
    this.version(1).stores({
      outbox: "op_id, status, lamport, next_retry_at",
      toy_cache: "id",
      sync_meta: "key",
    });
    // v2 (Phase 4.1): referral_cache + patient_cache added; outbox gains an
    // entity_id index so a screen can list pending ops for one referral
    // without a table scan. Tables not named here are unchanged, not
    // dropped (Dexie carries a table's last-declared schema forward).
    this.version(2).stores({
      outbox: "op_id, status, lamport, next_retry_at, entity_id",
      referral_cache: "id",
      patient_cache: "id",
    });
    // v3 (Phase 4.2): referral_event_cache (Screen 3's timeline) and
    // org_cache (Screen 2's village/facility names) added. Never edit a
    // shipped version — same discipline as the server's Alembic migrations.
    this.version(3).stores({
      referral_event_cache: "seq, referral_id",
      org_cache: "id, type",
    });
    // v4 (Phase 4.3): the Phase 1 scaffold model is dropped server-side
    // (migration 0006, D1/D7), so its local cache table goes too. Setting
    // a table to null is Dexie's actual "drop this" syntax — omitting it,
    // the way every version above omits tables it doesn't change, would
    // leave it in place instead.
    //
    // The two remaining references to that table name in this file (v1's
    // original declaration and the null below) are both load-bearing and
    // cannot be removed: v1 is shipped history, which is never edited
    // (same rule as an Alembic migration), and the null IS the drop. They
    // are the only matches P4.3's `grep -rn toy_ client/src` criterion
    // still finds, and that is expected, not leftover code.
    this.version(4).stores({
      toy_cache: null,
    });
    // v5 (Phase 5.2): Screen 4's live dashboard cache — written by
    // client/src/sync/dashboardStream.ts, read by SupervisorDashboardPage.
    // Not shared with referral_cache/referral_event_cache: the server's
    // dashboard payload carries village and ASHA names /sync/pull's frozen
    // contract does not (docs/PHASE5_PLAN.md P5.2 build order #3).
    this.version(5).stores({
      dashboard_stats_cache: "key",
      dashboard_overdue_cache: "escalation_id, referral_id",
    });
    // v6 (Phase 6, P6.2): Screen 6's review queue — client/src/sync/
    // identityReviews.ts writes it, IdentityReviewPage reads it.
    this.version(6).stores({
      identity_review_cache: "id",
    });
  }
}

export const db = new NirantharSevaDB();
