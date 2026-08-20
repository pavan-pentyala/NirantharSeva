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
 * referral_cache (D14) — the design's timeline never shows them either. */
export interface ReferralEventCacheRow {
  seq: number;
  referral_id: string;
  from_state: string | null;
  to_state: string;
  actor_role: string;
  actor_user_id: string;
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

class NirantharSevaDB extends Dexie {
  outbox!: Table<OutboxOp, string>;
  sync_meta!: Table<SyncMetaRow, string>;
  referral_cache!: Table<ReferralCacheRow, string>;
  patient_cache!: Table<PatientCacheRow, string>;
  referral_event_cache!: Table<ReferralEventCacheRow, number>;
  org_cache!: Table<OrgCacheRow, string>;

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
  }
}

export const db = new NirantharSevaDB();
