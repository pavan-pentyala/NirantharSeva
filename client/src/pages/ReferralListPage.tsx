import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { getSession } from "../auth/session";
import { DemoMarker } from "../components/DemoMarker";
import { LogoutButton } from "../components/LogoutButton";
import { StatePill } from "../components/StatePill";
import { SyncBand } from "../components/SyncBand";
import { WaitingToSendPill } from "../components/WaitingToSendPill";
import { db } from "../db/schema";
import { displayStatesFor } from "../domain/displayState";
import { formatAgeSex } from "../domain/formatAgeSex";
import { relativeTimeSince } from "../domain/relativeTime";
import { ashaActionFor } from "../domain/referralActions";
import { stateLabel } from "../domain/stateLabels";
import { useLiveQuery } from "../hooks/useLiveQuery";
import { useSyncStatus } from "../hooks/useSyncStatus";
import styles from "./ReferralListPage.module.css";

type Tab = "all" | "check" | "done";

/** D20: an escalated referral still needs a check even though its display
 * state (what ashaActionFor is asked about) is never "ESCALATED" itself —
 * currentState carries that fact, displayState carries whether she has an
 * action available. */
function needsCheck(currentState: string, displayState: string): boolean {
  return ashaActionFor(displayState) !== null || currentState === "ESCALATED";
}

export default function ReferralListPage() {
  const navigate = useNavigate();
  const session = getSession();
  const syncStatus = useSyncStatus();
  const [tab, setTab] = useState<Tab>("all");

  const referrals = useLiveQuery(() => db.referral_cache.toArray(), []) ?? [];
  const displayStates =
    useLiveQuery(() => displayStatesFor(referrals), [referrals]) ?? new Map<string, string>();
  const org = useLiveQuery(
    () => (session ? db.org_cache.get(session.orgUnitId) : undefined),
    [session?.orgUnitId],
  );
  const pendingEntityIds =
    useLiveQuery(async () => {
      const rows = await db.outbox
        .where("status")
        .anyOf("pending", "inflight")
        .and((o) => o.entity === "referral")
        .toArray();
      return new Set(rows.map((r) => r.entity_id));
    }, []) ?? new Set<string>();

  const sorted = [...referrals].sort((a, b) => (a.updated_at < b.updated_at ? 1 : -1));
  const displayStateOf = (r: (typeof sorted)[number]) => displayStates.get(r.id) ?? r.current_state;
  const checkCount = sorted.filter((r) => needsCheck(r.current_state, displayStateOf(r))).length;
  const doneCount = sorted.filter((r) => stateLabel(r.current_state).family === "done").length;
  const visible = sorted.filter((r) => {
    if (tab === "check") return needsCheck(r.current_state, displayStateOf(r));
    if (tab === "done") return stateLabel(r.current_state).family === "done";
    return true;
  });

  return (
    <div className={styles.page}>
      <DemoMarker />

      <div className={styles.header}>
        <div className={styles.headerTop}>
          <div className={styles.title}>My referrals</div>
          <div className={styles.headerActions}>
            <div className={styles.roleChip}>{session?.role ?? ""}</div>
            <LogoutButton />
          </div>
        </div>
        <div className={styles.subtitle}>
          {session?.username ?? ""}
          {org ? ` · ${org.name}` : ""}
        </div>
      </div>

      <SyncBand {...syncStatus} />

      <div className={styles.tabs}>
        <button className={`${styles.tab} ${tab === "all" ? styles.tabActive : ""}`} onClick={() => setTab("all")}>
          All {sorted.length}
        </button>
        <button
          className={`${styles.tab} ${tab === "check" ? styles.tabActive : ""}`}
          onClick={() => setTab("check")}
        >
          Need a check {checkCount}
        </button>
        <button className={`${styles.tab} ${tab === "done" ? styles.tabActive : ""}`} onClick={() => setTab("done")}>
          Done {doneCount}
        </button>
      </div>

      {visible.length === 0 ? (
        <div className={styles.empty}>
          <div className={styles.emptyCircle}>no referrals</div>
          <div className={styles.emptyTitle}>No referrals yet</div>
          <div className={styles.emptyBody}>
            When you send a patient to a health centre, add it here so everyone can follow up.
          </div>
        </div>
      ) : (
        <div className={styles.list}>
          {visible.map((r) => {
            const overdue = r.current_state === "ESCALATED";
            return (
              <button
                key={r.id}
                className={`${styles.row} ${overdue ? styles.rowOverdue : ""}`}
                onClick={() => navigate(`/referrals/${r.id}`)}
                data-testid="referral-row"
              >
                <div className={styles.rowTop}>
                  <div className={`${styles.name} ${overdue ? styles.nameOverdue : ""}`}>{r.patient_name}</div>
                  <div className={`${styles.age} ${overdue ? styles.ageOverdue : ""}`}>
                    {relativeTimeSince(r.updated_at)}
                  </div>
                </div>
                <div className={styles.secondary}>
                  {[
                    formatAgeSex(r.age, r.sex),
                    r.reason,
                    r.target_org_name,
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </div>
                <div className={styles.pills}>
                  <StatePill state={displayStateOf(r)} overdue={overdue} />
                  {pendingEntityIds.has(r.id) && <WaitingToSendPill />}
                </div>
              </button>
            );
          })}
        </div>
      )}

      <div className={styles.footer}>
        <button className={styles.newButton} onClick={() => navigate("/referrals/new")} data-testid="new-referral-button">
          New referral
        </button>
      </div>
    </div>
  );
}
