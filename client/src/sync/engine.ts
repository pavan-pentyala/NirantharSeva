/** Client outbox and flush loop. See plan §5.5.
 *
 * flush() pushes pending/inflight ops; pullAndApply() pulls new events and
 * folds them into the local toy_cache. Both are idempotent and safe to
 * call repeatedly — the single-flight guard on flush() is what stops the
 * four triggers (online, 15s timer, after every mutation, visibilitychange)
 * from stampeding each other.
 */

import * as api from "../api/client";
import { db, type OutboxOp } from "../db/schema";
import { getCursor, getDeviceId, getLamport, mergeLamport, markSyncedNow, nextLamport, setCursor, setLamport } from "../db/meta";

const BACKOFF_BASE_MS = 1000;
const BACKOFF_MAX_MS = 30_000;

let flushing = false;

export async function createOp(entityId: string, value: number): Promise<void> {
  const deviceId = await getDeviceId();
  const lamport = await nextLamport();
  const deviceTime = new Date().toISOString();
  const opId = crypto.randomUUID();

  await db.transaction("rw", db.outbox, db.toy_cache, async () => {
    await db.outbox.add({
      op_id: opId,
      entity: "toy",
      entity_id: entityId,
      operation: "set_value",
      payload: { value },
      lamport,
      device_time: deviceTime,
      status: "pending",
    });
    // Optimistic local cache — assumed to win until told otherwise by a
    // push response or a pulled event with a higher (lamport, device_id).
    await db.toy_cache.put({ id: entityId, value, updated_at: deviceTime, lamport, device_id: deviceId });
  });

  void syncNow();
}

export async function flush(): Promise<void> {
  if (flushing || !navigator.onLine) return;
  flushing = true;
  let batch: OutboxOp[] = [];
  try {
    const now = Date.now();
    batch = await db.outbox
      .where("status")
      .anyOf("pending", "inflight")
      .filter((o) => !o.next_retry_at || o.next_retry_at <= now)
      .sortBy("lamport"); // device order preserved

    if (!batch.length) return;

    await db.outbox.bulkUpdate(batch.map((o) => ({ key: o.op_id, changes: { status: "inflight" as const } })));

    const deviceId = await getDeviceId();
    const ops = batch.map(toWireOp);
    const res = await api.push(deviceId, ops);
    await applyResults(res.results);

    const local = await getLamport();
    await setLamport(mergeLamport(local, [res.server_lamport]));
    await markSyncedNow();
  } catch {
    // stays 'inflight'; safe to retry — the server is idempotent by op_id
    await scheduleBackoff(batch);
  } finally {
    flushing = false;
  }
}

function toWireOp(o: OutboxOp): api.Op {
  return {
    op_id: o.op_id,
    entity: o.entity,
    entity_id: o.entity_id,
    operation: o.operation,
    payload: o.payload,
    lamport: o.lamport,
    device_time: o.device_time,
  };
}

async function applyResults(results: api.OpResult[]): Promise<void> {
  let needsRepull = false;
  for (const r of results) {
    if (r.status === "accepted" || r.status === "accepted_stale") {
      await db.outbox.update(r.op_id, { status: "synced" });
    } else {
      // conflict or rejected — re-pull and overwrite local cache. Never
      // hand-write an inverse operation to undo the optimistic update;
      // server truth plus overwrite is simpler and cannot drift.
      await db.outbox.update(r.op_id, { status: r.status });
      needsRepull = true;
    }
  }
  if (needsRepull) {
    await pullAndApply();
  }
}

async function scheduleBackoff(batch: OutboxOp[]): Promise<void> {
  if (!batch.length) return;
  const now = Date.now();
  await db.outbox.bulkUpdate(
    batch.map((o) => {
      const attempts = (o.attempts ?? 0) + 1;
      const delay = Math.min(BACKOFF_BASE_MS * 2 ** attempts, BACKOFF_MAX_MS);
      return { key: o.op_id, changes: { status: "inflight" as const, next_retry_at: now + delay, attempts } };
    }),
  );
}

export async function pullAndApply(): Promise<void> {
  if (!navigator.onLine) return;
  for (;;) {
    const since = await getCursor();
    const res = await api.pull(since);

    if (res.events.length) {
      await applyPulledEvents(res.events);
      const local = await getLamport();
      const maxIncoming = Math.max(...res.events.map((e) => e.lamport));
      await setLamport(mergeLamport(local, [maxIncoming]));
    }

    await setCursor(res.cursor);
    await markSyncedNow();

    if (!res.has_more) break;
  }
}

async function applyPulledEvents(events: api.EventOut[]): Promise<void> {
  for (const e of events) {
    // D1: the toy model is the only thing this client caches through
    // Phase 4. Referral events already flow through /sync/pull (D3) but
    // have no client-side cache to land in yet.
    if (e.entity_type !== "toy") continue;

    const newValue = e.payload.new_value as number;
    const cached = await db.toy_cache.get(e.entity_id);
    const isWinner =
      !cached || e.lamport > cached.lamport || (e.lamport === cached.lamport && e.device_id >= cached.device_id);
    if (isWinner) {
      await db.toy_cache.put({
        id: e.entity_id,
        value: newValue,
        updated_at: e.server_time,
        lamport: e.lamport,
        device_id: e.device_id,
      });
    }
  }
}

async function syncNow(): Promise<void> {
  await flush();
  await pullAndApply();
}

let autoFlushStarted = false;

/** Guarded against being started twice. React 18 StrictMode mounts, unmounts,
 * and remounts effects in dev mode; the unmount's cleanup runs before the
 * mount's async login() has resolved, so it captures `stop` as undefined and
 * is a no-op — without this guard that leaves two intervals and two sets of
 * listeners running at once, racing each other. */
export function startAutoFlush(): () => void {
  if (autoFlushStarted) return () => {};
  autoFlushStarted = true;

  const interval = setInterval(() => void syncNow(), 15_000);
  const onOnline = () => void syncNow();
  const onVisibility = () => {
    if (document.visibilityState === "visible") void syncNow();
  };
  window.addEventListener("online", onOnline);
  document.addEventListener("visibilitychange", onVisibility);
  void syncNow();

  return () => {
    autoFlushStarted = false;
    clearInterval(interval);
    window.removeEventListener("online", onOnline);
    document.removeEventListener("visibilitychange", onVisibility);
  };
}
