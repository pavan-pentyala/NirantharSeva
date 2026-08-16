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

class NirantharSevaDB extends Dexie {
  outbox!: Table<OutboxOp, string>;
  toy_cache!: Table<ToyCacheRow, string>;
  sync_meta!: Table<SyncMetaRow, string>;

  constructor() {
    super("nirantharseva");
    this.version(1).stores({
      outbox: "op_id, status, lamport, next_retry_at",
      toy_cache: "id",
      sync_meta: "key",
    });
  }
}

export const db = new NirantharSevaDB();
