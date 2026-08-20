import { useState } from "react";
import { getSession } from "../auth/session";
import { DemoMarker } from "../components/DemoMarker";
import { StatePill } from "../components/StatePill";
import { db } from "../db/schema";
import { formatAgeSex } from "../domain/formatAgeSex";
import { moActionFor } from "../domain/referralActions";
import { relativeTimeSince } from "../domain/relativeTime";
import { useLiveQuery } from "../hooks/useLiveQuery";
import { useSyncStatus } from "../hooks/useSyncStatus";
import { transitionReferral } from "../sync/engine";
import styles from "./IncomingReferralsPage.module.css";

type Tab = "IN_TRANSIT" | "ARRIVED" | "TREATED";

const TABS: { key: Tab; label: string }[] = [
  { key: "IN_TRANSIT", label: "On the way" },
  { key: "ARRIVED", label: "At the centre" },
  { key: "TREATED", label: "Treated today" },
];

export default function IncomingReferralsPage() {
  const session = getSession();
  const syncStatus = useSyncStatus();
  const [tab, setTab] = useState<Tab>("IN_TRANSIT");

  const referrals = useLiveQuery(() => db.referral_cache.toArray(), []) ?? [];
  const org = useLiveQuery(() => (session ? db.org_cache.get(session.orgUnitId) : undefined), [
    session?.orgUnitId,
  ]);

  const counts: Record<Tab, number> = {
    IN_TRANSIT: referrals.filter((r) => r.current_state === "IN_TRANSIT").length,
    ARRIVED: referrals.filter((r) => r.current_state === "ARRIVED").length,
    TREATED: referrals.filter((r) => r.current_state === "TREATED").length,
  };
  const visible = referrals
    .filter((r) => r.current_state === tab)
    .sort((a, b) => (a.updated_at < b.updated_at ? -1 : 1));

  async function handleAdvance(referralId: string, currentState: string) {
    const action = moActionFor(currentState);
    if (!action) return;
    await transitionReferral(referralId, currentState, action.toState);
  }

  return (
    <div className={styles.page}>
      <DemoMarker />

      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <div className={styles.title}>Incoming referrals</div>
          <div className={styles.subtitle}>
            {session?.username ?? ""}
            {org ? ` · ${org.name}` : ""}
          </div>
        </div>
        <div className={styles.syncInline}>
          <span className={`${styles.dot} ${syncStatus.online ? styles.dotOnline : styles.dotOffline}`} />
          {syncStatus.online ? "Connected" : "No signal"}
        </div>
      </div>

      <div className={styles.tabs}>
        {TABS.map(({ key, label }) => (
          <button
            key={key}
            className={`${styles.tab} ${tab === key ? styles.tabActive : ""}`}
            onClick={() => setTab(key)}
          >
            {label} {counts[key]}
          </button>
        ))}
      </div>

      <div className={styles.list}>
        {visible.length === 0 && <div className={styles.empty}>Nothing here right now.</div>}
        {visible.map((r) => {
          const action = moActionFor(r.current_state);
          return (
            <div key={r.id} className={styles.card} data-testid="incoming-card">
              <div className={styles.cardMain}>
                <div className={styles.nameRow}>
                  <div className={styles.name}>{r.patient_name}</div>
                  <div className={styles.age}>{formatAgeSex(r.age, r.sex)}</div>
                </div>
                <div className={styles.reason}>{r.reason ?? ""}</div>
                <div className={styles.pillRow}>
                  <StatePill state={r.current_state} />
                  <span className={styles.since}>{relativeTimeSince(r.updated_at)} ago</span>
                </div>
              </div>
              {action && (
                <button
                  className={`${styles.actionButton} ${r.current_state === "ARRIVED" ? styles.actionButtonOutline : ""}`}
                  onClick={() => void handleAdvance(r.id, r.current_state)}
                  data-testid="advance-button"
                >
                  {action.buttonLabel}
                </button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
