import { useState } from "react";
import { getSession } from "../auth/session";
import { DemoMarker } from "../components/DemoMarker";
import { LogoutButton } from "../components/LogoutButton";
import { StatePill } from "../components/StatePill";
import { db } from "../db/schema";
import { displayStatesFor } from "../domain/displayState";
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
  const displayStates =
    useLiveQuery(() => displayStatesFor(referrals), [referrals]) ?? new Map<string, string>();
  const org = useLiveQuery(() => (session ? db.org_cache.get(session.orgUnitId) : undefined), [
    session?.orgUnitId,
  ]);

  // D20: an escalated referral is filed under the tab matching its display
  // state (the state it was breached from), not "current_state" — its own
  // tab is where a supervisor's "act now" is actually actionable, and
  // where GUARDS[ESCALATED]={SYSTEM} means it would otherwise never appear
  // on any tab at all.
  const displayStateOf = (r: (typeof referrals)[number]) => displayStates.get(r.id) ?? r.current_state;
  const counts: Record<Tab, number> = {
    IN_TRANSIT: referrals.filter((r) => displayStateOf(r) === "IN_TRANSIT").length,
    ARRIVED: referrals.filter((r) => displayStateOf(r) === "ARRIVED").length,
    TREATED: referrals.filter((r) => displayStateOf(r) === "TREATED").length,
  };
  const visible = referrals
    .filter((r) => displayStateOf(r) === tab)
    .sort((a, b) => (a.updated_at < b.updated_at ? -1 : 1));

  // fromState is always the real current_state (what the server's cache
  // actually holds — "ESCALATED" while overdue, per D22's resolve-on-exit
  // needing exactly that from_state) — toState comes from the display
  // state's action lookup instead, computed by the caller, not re-derived
  // here from currentState (which would silently find no MO_ACTIONS entry
  // for "ESCALATED" and no-op the button).
  async function handleAdvance(referralId: string, currentState: string, toState: string) {
    await transitionReferral(referralId, currentState, toState);
  }

  return (
    <div className={styles.page}>
      <DemoMarker />

      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <div className={styles.title}>Incoming referrals</div>
          <div className={styles.subtitle}>
            {[session?.role, session?.username, org?.name].filter(Boolean).join(" · ")}
          </div>
        </div>
        <div className={styles.headerRight}>
          <div className={styles.syncInline}>
            <span className={`${styles.dot} ${syncStatus.online ? styles.dotOnline : styles.dotOffline}`} />
            {syncStatus.online ? "Connected" : "No signal"}
          </div>
          <LogoutButton />
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
          const displayState = displayStateOf(r);
          const overdue = r.current_state === "ESCALATED";
          const action = moActionFor(displayState);
          return (
            <div
              key={r.id}
              className={`${styles.card} ${overdue ? styles.cardOverdue : ""}`}
              data-testid="incoming-card"
            >
              <div className={styles.cardMain}>
                <div className={styles.nameRow}>
                  <div className={styles.name}>{r.patient_name}</div>
                  <div className={styles.age}>{formatAgeSex(r.age, r.sex)}</div>
                </div>
                <div className={styles.reason}>{r.reason ?? ""}</div>
                <div className={styles.pillRow}>
                  <StatePill state={displayState} overdue={overdue} />
                  <span className={styles.since}>{relativeTimeSince(r.updated_at)} ago</span>
                </div>
              </div>
              {action && (
                <button
                  className={`${styles.actionButton} ${displayState === "ARRIVED" ? styles.actionButtonOutline : ""}`}
                  onClick={() => void handleAdvance(r.id, r.current_state, action.toState)}
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
