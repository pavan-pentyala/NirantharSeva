import { db } from "./schema";

const DEVICE_ID_KEY = "device_id";
const LAMPORT_KEY = "lamport";
const CURSOR_KEY = "cursor";
const LAST_SYNC_KEY = "last_sync_at";

export async function getDeviceId(): Promise<string> {
  const row = await db.sync_meta.get(DEVICE_ID_KEY);
  if (row) return row.value as string;
  const id = crypto.randomUUID();
  await db.sync_meta.put({ key: DEVICE_ID_KEY, value: id });
  return id;
}

export async function getLamport(): Promise<number> {
  const row = await db.sync_meta.get(LAMPORT_KEY);
  return row ? (row.value as number) : 0;
}

export async function setLamport(value: number): Promise<void> {
  await db.sync_meta.put({ key: LAMPORT_KEY, value });
}

/** Same max-merge formula the server uses (plan §5.4 / app/sync/lamport.py). */
export function mergeLamport(local: number, incoming: number[]): number {
  return Math.max(local, ...incoming);
}

export async function nextLamport(): Promise<number> {
  const next = (await getLamport()) + 1;
  await setLamport(next);
  return next;
}

export async function getCursor(): Promise<number> {
  const row = await db.sync_meta.get(CURSOR_KEY);
  return row ? (row.value as number) : 0;
}

export async function setCursor(value: number): Promise<void> {
  await db.sync_meta.put({ key: CURSOR_KEY, value });
}

export async function getLastSyncAt(): Promise<number | null> {
  const row = await db.sync_meta.get(LAST_SYNC_KEY);
  return row ? (row.value as number) : null;
}

export async function markSyncedNow(): Promise<void> {
  await db.sync_meta.put({ key: LAST_SYNC_KEY, value: Date.now() });
}
