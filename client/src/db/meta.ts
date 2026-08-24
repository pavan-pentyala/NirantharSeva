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

/** Wrapped in a Dexie transaction — a plain "await getLamport(); await
 * setLamport(...)" is two separate IndexedDB round trips, and two
 * concurrent callers (e.g. a double-tapped submit button with no busy
 * guard) can both read the same value before either writes the
 * increment, handing out the same lamport twice. Dexie's "rw" transaction
 * on sync_meta makes the read-modify-write atomic against any other
 * caller of nextLamport(). Found in a pre-Phase-9 audit. */
export async function nextLamport(): Promise<number> {
  return db.transaction("rw", db.sync_meta, async () => {
    const next = (await getLamport()) + 1;
    await setLamport(next);
    return next;
  });
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
