import styles from "./SyncBand.module.css";

function formatLastSent(lastSyncAt: number | null): string | null {
  if (lastSyncAt === null) return null;
  const d = new Date(lastSyncAt);
  const time = d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }).toLowerCase();
  const sameDay = new Date().toDateString() === d.toDateString();
  return sameDay ? `Last sent today ${time}` : `Last sent ${d.toLocaleDateString()} ${time}`;
}

export interface SyncBandProps {
  online: boolean;
  pendingCount: number;
  lastSyncAt: number | null;
}

/** Brief §6: lives directly under the header on every worker screen, the
 * first thing under the page title. Copy is drawn only from the brief's own
 * allowed vocabulary — the banned list (sync, pending ops, conflict,
 * operation, queue, offline mode, retry, payload) never appears here. */
export function SyncBand({ online, pendingCount, lastSyncAt }: SyncBandProps) {
  const offlineWithPending = !online && pendingCount > 0;
  const lastSent = formatLastSent(lastSyncAt);

  return (
    <div className={`${styles.band} ${offlineWithPending ? styles.amber : styles.grey}`}>
      <span className={`${styles.dot} ${offlineWithPending ? styles.dotAmber : styles.dotGrey}`} />
      <div className={styles.text}>
        <div className={styles.status}>{offlineWithPending ? "No signal" : "Connected"}</div>
        <div className={styles.detail}>
          {offlineWithPending
            ? `${pendingCount} update${pendingCount === 1 ? "" : "s"} waiting to send. They will send when signal comes back.`
            : "Everything is sent."}
        </div>
        {lastSent && <div className={styles.time}>{lastSent}</div>}
      </div>
    </div>
  );
}
