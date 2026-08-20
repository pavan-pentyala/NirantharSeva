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

/** Local cache of "what does the server currently think this entity is."
 * Carries lamport/device_id alongside the value so the client can apply the
 * same last-writer-wins comparison the server uses (app/sync/push.py) when
 * replaying pulled events — otherwise the cache could regress to an older
 * value just because it arrived later in a pull. */
export interface ToyCacheRow {
  id: string;
  value: number;
  updated_at: string;
  lamport: number;
  device_id: string;
}

export interface SyncMetaRow {
  key: string;
  value: string | number;
}

/** Local cache of a referral's current state and the snapshot fields the
 * screens render (ADR-010) — built entirely by folding pulled events
 * (client/src/sync/engine.ts's applyPulledEvents), the same pattern
 * toy_cache already proved out. Only an advancing pulled step writes here;
 * a losing or stale event still updates its outbox record but never this
 * table (D14). */
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

class NirantharSevaDB extends Dexie {
  outbox!: Table<OutboxOp, string>;
  toy_cache!: Table<ToyCacheRow, string>;
  sync_meta!: Table<SyncMetaRow, string>;
  referral_cache!: Table<ReferralCacheRow, string>;
  patient_cache!: Table<PatientCacheRow, string>;

  constructor() {
    super("nirantharseva");
    this.version(1).stores({
      outbox: "op_id, status, lamport, next_retry_at",
      toy_cache: "id",
      sync_meta: "key",
    });
    // v2 (Phase 4.1): referral_cache + patient_cache added; outbox gains an
    // entity_id index so a screen can list pending ops for one referral
    // without a table scan. toy_cache/sync_meta unchanged — omitted here,
    // not dropped (Dexie keeps a table's last-declared schema forward).
    this.version(2).stores({
      outbox: "op_id, status, lamport, next_retry_at, entity_id",
      referral_cache: "id",
      patient_cache: "id",
    });
  }
}

export const db = new NirantharSevaDB();
