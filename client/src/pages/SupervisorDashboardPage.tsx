import { useEffect, useRef, useState } from "react";
import { getSession } from "../auth/session";
import { DemoMarker } from "../components/DemoMarker";
import { db, type DashboardOverdueCacheRow } from "../db/schema";
import { relativeTimeSince } from "../domain/relativeTime";
import { useLiveQuery } from "../hooks/useLiveQuery";
import { startDashboardStream } from "../sync/dashboardStream";
import styles from "./SupervisorDashboardPage.module.css";

interface Banner {
  patientName: string;
  village: string | null;
  overdueBy: string;
}

const STAT_TILES: { key: "open" | "on_the_way" | "reached_centre" | "treated_or_sent_back" | "closed_this_month"; label: string }[] = [
  { key: "open", label: "Open referrals" },
  { key: "on_the_way", label: "On the way" },
  { key: "reached_centre", label: "Reached centre" },
  { key: "treated_or_sent_back", label: "Treated / sent back" },
  { key: "closed_this_month", label: "Closed this month" },
];

export default function SupervisorDashboardPage() {
  const session = getSession();
  const org = useLiveQuery(
    () => (session ? db.org_cache.get(session.orgUnitId) : undefined),
    [session?.orgUnitId],
  );
  const stats = useLiveQuery(() => db.dashboard_stats_cache.get("current"), []);
  const overdueRows = useLiveQuery(() => db.dashboard_overdue_cache.toArray(), []) ?? [];
  const sorted = [...overdueRows].sort((a, b) => (a.triggered_at < b.triggered_at ? -1 : 1));

  useEffect(() => startDashboardStream(), []);

  // "updated N seconds ago" needs its own clock — nothing else in this
  // component re-renders on a timer, and stats.updated_at is a fixed
  // string once written.
  const [, tick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => tick((n) => n + 1), 1000);
    return () => clearInterval(id);
  }, []);

  // Row-arrival animation and the banner both fire only for rows genuinely
  // new since the *previous* snapshot — never for the first one a fresh
  // connection delivers (that's just the current steady state, not a
  // "new breach"). animatedIds is a ref, not state: once a row is marked,
  // its fade-in class stays on the element permanently (harmless — a CSS
  // animation plays once on mount and does not replay on an unrelated
  // re-render of the same DOM node), so this only ever grows.
  const seenIds = useRef<Set<string> | null>(null);
  const animatedIds = useRef(new Set<string>());
  const [banner, setBanner] = useState<Banner | null>(null);

  useEffect(() => {
    const currentIds = new Set(sorted.map((r) => r.escalation_id));
    if (seenIds.current === null) {
      seenIds.current = currentIds;
      return;
    }
    const newRows = sorted.filter((r) => !seenIds.current!.has(r.escalation_id));
    seenIds.current = currentIds;
    if (newRows.length === 0) return;

    for (const row of newRows) animatedIds.current.add(row.escalation_id);
    const latest = newRows[0];
    setBanner({
      patientName: latest.patient_name,
      village: latest.village_name,
      overdueBy: relativeTimeSince(latest.triggered_at),
    });
    // Deliberately keyed on the id set, not on `sorted` itself (a new
    // array reference every render) or on functions this effect doesn't
    // otherwise close over — this project has no eslint-plugin-react-hooks
    // to appease, only the actual re-run condition: which rows are present.
  }, [sorted.map((r) => r.escalation_id).join(",")]);

  const live = stats !== undefined;

  return (
    <div className={styles.page}>
      <DemoMarker />

      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <div className={styles.blockName}>{org?.name ?? ""}</div>
          <div className={styles.subtitle}>Supervisor · {session?.username ?? ""}</div>
        </div>
        <div className={styles.liveIndicator}>
          <span className={`${styles.dot} ${live ? styles.dotLive : styles.dotConnecting}`} />
          <span className={styles.liveLabel}>{live ? "Live" : "Connecting…"}</span>
          {stats && <span className={styles.updatedAt}>updated {relativeTimeSince(stats.updated_at)} ago</span>}
        </div>
      </div>

      {banner && (
        <div className={styles.banner}>
          <span className={styles.bannerDot} />
          <div className={styles.bannerText}>
            <b>New overdue referral:</b> {banner.patientName}
            {banner.village ? `, ${banner.village}` : ""} — no update for {banner.overdueBy} past deadline.
          </div>
          <button className={styles.bannerDismiss} onClick={() => setBanner(null)} aria-label="Dismiss">
            ✕
          </button>
        </div>
      )}

      <div className={styles.statStrip}>
        {STAT_TILES.map(({ key, label }) => (
          <div key={key} className={styles.statTile}>
            <div className={styles.statValue}>{stats ? stats[key] : "–"}</div>
            <div className={styles.statLabel}>{label}</div>
          </div>
        ))}
        <div className={`${styles.statTile} ${styles.statTileOverdue}`}>
          <div className={`${styles.statValue} ${styles.statValueOverdue}`}>{stats ? stats.overdue : "–"}</div>
          <div className={`${styles.statLabel} ${styles.statLabelOverdue}`}>Overdue</div>
        </div>
      </div>

      <div className={styles.listHeading}>
        <div className={styles.listTitle}>Overdue — act now</div>
        <div className={styles.sortNote}>sorted by how overdue</div>
      </div>

      {sorted.length === 0 ? (
        <div className={styles.empty}>Nothing overdue right now.</div>
      ) : (
        <div className={styles.table}>
          <div className={styles.tableHeaderRow}>
            <div>Patient</div>
            <div>Village</div>
            <div>Sent to</div>
            <div>Reason</div>
            <div>Overdue by</div>
            <div>ASHA</div>
          </div>
          {sorted.map((row: DashboardOverdueCacheRow) => (
            <div
              key={row.escalation_id}
              className={`${styles.tableRow} ${animatedIds.current.has(row.escalation_id) ? styles.tableRowNew : ""}`}
            >
              <div className={styles.patientName}>{row.patient_name}</div>
              <div>{row.village_name ?? ""}</div>
              <div>{row.target_org_name ?? ""}</div>
              <div>{row.reason ?? ""}</div>
              <div className={styles.overdueBy}>{relativeTimeSince(row.triggered_at)}</div>
              <div>{row.asha_name ?? ""}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
