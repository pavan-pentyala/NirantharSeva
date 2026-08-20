import { useEffect, useState } from "react";
import { getLastSyncAt } from "../db/meta";
import { db } from "../db/schema";
import { useLiveQuery } from "./useLiveQuery";

export interface SyncStatus {
  online: boolean;
  pendingCount: number;
  lastSyncAt: number | null;
}

/** Backs SyncBand on every worker screen. Reads only Dexie (brief §8) —
 * pendingCount and lastSyncAt are both live queries, not polls, so the
 * band updates the instant engine.ts writes to outbox or sync_meta. */
export function useSyncStatus(): SyncStatus {
  const [online, setOnline] = useState(navigator.onLine);

  useEffect(() => {
    const onOnline = () => setOnline(true);
    const onOffline = () => setOnline(false);
    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOffline);
    return () => {
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOffline);
    };
  }, []);

  const pendingCount = useLiveQuery(() => db.outbox.where("status").anyOf("pending", "inflight").count(), []) ?? 0;
  const lastSyncAt = useLiveQuery(() => getLastSyncAt(), []) ?? null;

  return { online, pendingCount, lastSyncAt };
}
