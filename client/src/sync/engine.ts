/** Client outbox and flush loop. See plan §5.5.
 *
 * flush() pushes pending/inflight ops; pullAndApply() pulls new events and
 * folds them into referral_cache/referral_event_cache. Both are idempotent
 * and safe to call repeatedly — the single-flight guard on flush() is what
 * stops the four triggers (online, 15s timer, after every mutation,
 * visibilitychange) from stampeding each other.
 */

import * as api from "../api/client";
import { db, type OutboxOp } from "../db/schema";
import { getCursor, getDeviceId, getLamport, mergeLamport, markSyncedNow, nextLamport, setCursor, setLamport } from "../db/meta";

const BACKOFF_BASE_MS = 1000;
const BACKOFF_MAX_MS = 30_000;

// Env var, not a constant, for the same reason SLA_SCALE/SWEEP_INTERVAL_SECONDS
// are (docker-compose.yml) — demo and field cadence differ without a code
// change, and it turns the E5 poll load into a tunable rather than a fixed cost.
const SYNC_INTERVAL_MS = Number(import.meta.env.VITE_SYNC_INTERVAL_MS) || 15_000;

let flushing = false;
let pulling = false;

export interface CreateReferralInput {
  patientName: string;
  age?: number;
  sex?: string;
  phone?: string;
  reason?: string;
  priority?: string;
  targetOrgId?: string;
}

/** ADR-009: the payload names a patient by what the ASHA typed, not an id
 * she never gets to pick from — the server resolves-or-creates the patient
 * row. Returns the client-generated referral id (the op's entity_id). */
export async function createReferral(input: CreateReferralInput): Promise<string> {
  const deviceId = await getDeviceId();
  const lamport = await nextLamport();
  const deviceTime = new Date().toISOString();
  const opId = crypto.randomUUID();
  const entityId = crypto.randomUUID();

  const payload: Record<string, unknown> = { patient_name: input.patientName };
  if (input.age !== undefined) payload.age = input.age;
  if (input.sex !== undefined) payload.sex = input.sex;
  if (input.phone !== undefined) payload.phone = input.phone;
  if (input.reason !== undefined) payload.reason = input.reason;
  if (input.priority !== undefined) payload.priority = input.priority;
  if (input.targetOrgId !== undefined) payload.target_org_id = input.targetOrgId;

  await db.transaction("rw", db.outbox, db.referral_cache, async () => {
    await db.outbox.add({
      op_id: opId,
      entity: "referral",
      entity_id: entityId,
      operation: "create_referral",
      payload,
      lamport,
      device_time: deviceTime,
      status: "pending",
    });
    // Optimistic — the server may resolve this to an existing patient row
    // rather than create one, but the referral itself is new and always
    // wins locally until told otherwise. target_org_name isn't known
    // locally (only target_org_id was typed); it fills in once this
    // create_referral event is pulled back (ADR-010).
    await db.referral_cache.put({
      id: entityId,
      current_state: "CREATED",
      patient_name: input.patientName,
      age: input.age ?? null,
      sex: input.sex ?? null,
      reason: input.reason ?? null,
      priority: input.priority ?? null,
      target_org_name: null,
      lamport,
      device_id: deviceId,
      updated_at: deviceTime,
    });
  });

  void syncNow();
  return entityId;
}

/** Same left-to-right advancement rule app/domain/states.py's replay_steps
 * encodes server-side (D14): only write the cache when the transition is
 * coherent with what's cached now. A transition requested against a state
 * that has already moved on locally leaves the cache untouched — the
 * outbox entry is still queued and the server will decide for real. */
export async function transitionReferral(entityId: string, fromState: string, toState: string): Promise<void> {
  const deviceId = await getDeviceId();
  const lamport = await nextLamport();
  const deviceTime = new Date().toISOString();
  const opId = crypto.randomUUID();

  await db.transaction("rw", db.outbox, db.referral_cache, async () => {
    await db.outbox.add({
      op_id: opId,
      entity: "referral",
      entity_id: entityId,
      operation: "transition",
      payload: { from_state: fromState, to_state: toState },
      lamport,
      device_time: deviceTime,
      status: "pending",
    });
    const cached = await db.referral_cache.get(entityId);
    if (cached && cached.current_state === fromState) {
      await db.referral_cache.put({
        ...cached,
        current_state: toState,
        lamport,
        device_id: deviceId,
        updated_at: deviceTime,
      });
    }
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
    // Each op's own outbox write is isolated in its own try/catch: this
    // loop runs inside flush()'s try block, and flush()'s catch reverts
    // the WHOLE original batch back to "inflight" on any thrown error —
    // correct if the push itself failed, but wrong here, since an update
    // failing partway through an already-accepted response would revert
    // ops this same loop had already, correctly, marked "synced" moments
    // earlier. A push response is never retried (the server already
    // applied it — that's what accepted/conflict/rejected mean), so a
    // failed local write here is a Dexie-level problem, not a sync one;
    // it's logged and skipped rather than allowed to corrupt siblings.
    // Found in a pre-Phase-9 audit.
    try {
      if (r.status === "accepted" || r.status === "accepted_stale") {
        await db.outbox.update(r.op_id, { status: "synced" });
      } else {
        // conflict or rejected — re-pull and overwrite local cache. Never
        // hand-write an inverse operation to undo the optimistic update;
        // server truth plus overwrite is simpler and cannot drift.
        await db.outbox.update(r.op_id, { status: r.status });
        needsRepull = true;
      }
    } catch (err) {
      console.error("failed to record push result locally", r.op_id, err);
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

// Single-flight, same reason flush() has `flushing`: this function is
// reachable concurrently from four places (the 15s timer, `online`,
// `visibilitychange`, and every post-write syncNow()) plus a nested call
// from applyResults() below when a push comes back with a conflict. Two
// overlapping runs would each start from the cursor's value at their own
// call time and could then race writing setCursor(), one clobbering the
// other's further-advanced value. Found in a pre-Phase-9 audit.
export async function pullAndApply(): Promise<void> {
  if (pulling || !navigator.onLine) return;
  pulling = true;
  try {
    for (;;) {
      const since = await getCursor();
      const res = await api.pull(since);

      if (res.events.length) {
        await applyPulledEvents(res.events);
        const local = await getLamport();
        const maxIncoming = Math.max(...res.events.map((e) => e.lamport));
        await setLamport(mergeLamport(local, [maxIncoming]));
      }

      // Monotonic merge, not a blind overwrite — the `pulling` guard above
      // already makes a second concurrent run impossible, but merging
      // keeps this correct on its own terms rather than relying entirely
      // on that guard (the same defense-in-depth reasoning as the lamport
      // merge just above).
      const current = await getCursor();
      await setCursor(Math.max(current, res.cursor));
      await markSyncedNow();

      if (!res.has_more) break;
    }
  } catch {
    // A transient pull failure used to propagate as an unhandled promise
    // rejection to every caller (none of them await this — void syncNow()).
    // Swallow it here, the same way flush() contains its own failures —
    // the next periodic trigger (15s timer, online, visibilitychange)
    // retries from wherever the cursor actually got to.
  } finally {
    pulling = false;
  }
}

export async function applyPulledEvents(events: api.EventOut[]): Promise<void> {
  for (const e of events) {
    if (e.entity_type === "referral") {
      await applyPulledReferralEvent(e);
    }
  }
}

/** D14/ADR-010: the same left-to-right advancement rule
 * app/domain/states.py's replay_steps encodes server-side — an event
 * advances the cached state only when its from_state matches the state
 * already folded in from earlier *pulled* events. "State so far" is read
 * from referral_event_cache (only ever written by an advancing pull), not
 * from referral_cache — referral_cache can already be ahead of the fold at
 * this point, because createReferral()/transitionReferral() write it
 * optimistically before any round trip. Folding from referral_cache instead
 * of referral_event_cache was P4.2's first attempt, and it broke exactly
 * the case that matters most: a device's own confirming pull for its own
 * op never advanced, because its optimistic write had already moved
 * referral_cache past what the confirming event's from_state expected — see
 * docs/OBSERVATIONS.md's P4.2 section. Folding from
 * referral_event_cache instead is immune to that, because nothing but this
 * function ever writes there.
 *
 * A losing or stale event is received here — pull is a full log, nothing is
 * filtered out — but never advances the fold, matching the server's own
 * decision. Do not add a lamport comparison here: referral state coherence
 * is decided by from_state alone (see replay_steps's own docstring). */
async function applyPulledReferralEvent(e: api.EventOut): Promise<void> {
  const priorEvents = await db.referral_event_cache.where("referral_id").equals(e.entity_id).sortBy("seq");
  const stateSoFar = priorEvents.length > 0 ? priorEvents[priorEvents.length - 1].to_state : null;
  const fromState = (e.payload.from_state as string | null) ?? null;
  const advanced = fromState === stateSoFar;
  if (!advanced) return;

  await db.referral_cache.put({
    id: e.entity_id,
    current_state: e.payload.to_state as string,
    patient_name: e.payload.patient_name as string,
    age: (e.payload.age as number | null | undefined) ?? null,
    sex: (e.payload.sex as string | null | undefined) ?? null,
    reason: (e.payload.reason as string | null | undefined) ?? null,
    priority: (e.payload.priority as string | null | undefined) ?? null,
    target_org_name: (e.payload.target_org_name as string | null | undefined) ?? null,
    lamport: e.lamport,
    device_id: e.device_id,
    updated_at: e.server_time,
  });

  // P4.2: Screen 3's timeline reads only this table, never a live API call
  // (brief §8). Only advancing events are kept, matching what the design
  // renders — a losing/stale event never appears in "What happened" either.
  // put(), not add(): idempotent under pullAndApply()'s retry-from-cursor
  // behaviour if applying a later event in the same page throws.
  await db.referral_event_cache.put({
    seq: e.seq,
    referral_id: e.entity_id,
    from_state: fromState,
    to_state: e.payload.to_state as string,
    actor_role: e.payload.actor_role as string,
    actor_user_id: (e.payload.actor_user_id as string | null | undefined) ?? null,
    device_time: e.device_time,
    server_time: e.server_time,
  });
}

/** P4.2: org names/hierarchy, fetched once rather than pulled through the
 * sync stream — org_unit isn't an event-sourced entity (app/api/org_units.py
 * is a plain read, not part of /sync/push|pull). Safe to call repeatedly;
 * a bulkPut just refreshes the cache with whatever the server has now. */
export async function refreshOrgCache(): Promise<void> {
  if (!navigator.onLine) return;
  const orgUnits = await api.listOrgUnits();
  await db.org_cache.bulkPut(orgUnits);
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

  const interval = setInterval(() => void syncNow(), SYNC_INTERVAL_MS);
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
