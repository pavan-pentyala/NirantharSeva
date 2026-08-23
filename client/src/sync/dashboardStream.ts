/** Screen 4's live feed. docs/PHASE5_PLAN.md P5.2, docs/decisions/ADR-011.md,
 * docs/decisions/ADR-012.md.
 *
 * EventSource, not fetch+ReadableStream — plan §9.2's own reason: automatic
 * reconnection with no hand-rolled retry logic. Authenticates by query
 * token (ADR-012) since EventSource cannot set an Authorization header;
 * getToken() already exposes the raw JWT for exactly this.
 *
 * Writes every message into Dexie and nothing else — the screen reads only
 * Dexie (docs/PHASE5_PLAN.md "Traps": "do not let the dashboard read the
 * network directly"). Each message is a full snapshot (ADR-011: a
 * notification is a signal, not data — the server re-runs its own query
 * and sends the result), so the overdue table is cleared and rewritten
 * wholesale on every message, never patched — a referral that resolved is
 * simply absent from the next snapshot, and its stale row goes with it.
 */

import { getToken } from "../api/client";
import { db } from "../db/schema";

const STREAM_URL = "/api/dashboard/stream";

interface DashboardStatsPayload {
  open: number;
  on_the_way: number;
  reached_centre: number;
  treated_or_sent_back: number;
  overdue: number;
  closed_this_month: number;
}

interface DashboardOverdueRowPayload {
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

interface DashboardSnapshotPayload {
  stats: DashboardStatsPayload;
  overdue: DashboardOverdueRowPayload[];
}

async function writeSnapshot(snapshot: DashboardSnapshotPayload): Promise<void> {
  const now = new Date().toISOString();
  await db.transaction("rw", db.dashboard_stats_cache, db.dashboard_overdue_cache, async () => {
    await db.dashboard_stats_cache.put({ key: "current", ...snapshot.stats, updated_at: now });
    await db.dashboard_overdue_cache.clear();
    await db.dashboard_overdue_cache.bulkPut(snapshot.overdue);
  });
}

let activeSource: EventSource | null = null;

/** Starts the subscription (idempotent — a second call while one is already
 * open is a no-op, same guard shape as sync/engine.ts's startAutoFlush).
 * Returns a stop function; call it on unmount so the connection doesn't
 * outlive Screen 4. */
export function startDashboardStream(): () => void {
  if (activeSource) return () => {};

  const token = getToken();
  if (!token) return () => {};

  const source = new EventSource(`${STREAM_URL}?token=${encodeURIComponent(token)}`);
  activeSource = source;

  source.onmessage = (event) => {
    try {
      const snapshot = JSON.parse(event.data) as DashboardSnapshotPayload;
      void writeSnapshot(snapshot);
    } catch (err) {
      console.error("dashboardStream: failed to parse snapshot", err);
    }
  };
  // No onerror-driven close: EventSource retries on its own (plan §9.2),
  // and closing here would fight its native reconnect instead of relying
  // on it — that's the whole reason this uses EventSource over a
  // hand-rolled fetch loop.

  return () => {
    source.close();
    activeSource = null;
  };
}
