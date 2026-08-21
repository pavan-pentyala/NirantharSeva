import { useEffect, useState } from "react";
import { decideIdentityReview, type IdentityDecision } from "../api/client";
import { getSession } from "../auth/session";
import { DemoMarker } from "../components/DemoMarker";
import { db, type IdentityReviewCacheRow, type IdentityReviewPatientSnapshot } from "../db/schema";
import { relativeTimeSince } from "../domain/relativeTime";
import { useLiveQuery } from "../hooks/useLiveQuery";
import { useSyncStatus } from "../hooks/useSyncStatus";
import { refreshIdentityReviews } from "../sync/identityReviews";
import styles from "./IdentityReviewPage.module.css";

function lastSeen(p: IdentityReviewPatientSnapshot): string {
  if (!p.last_seen_at) return "No visits recorded";
  const when = relativeTimeSince(p.last_seen_at);
  return p.last_seen_reason ? `${when} ago, ${p.last_seen_reason}` : `${when} ago`;
}

interface FieldRow {
  label: string;
  existing: string;
  next: string;
  disagree: boolean;
}

function fieldRows(pair: IdentityReviewCacheRow): FieldRow[] {
  const { existing, new: incoming } = pair;
  return [
    {
      label: "Age",
      existing: existing.age != null ? String(existing.age) : "—",
      next: incoming.age != null ? String(incoming.age) : "—",
      disagree: existing.age !== incoming.age,
    },
    {
      label: "Village",
      existing: existing.village_name ?? "—",
      next: incoming.village_name ?? "—",
      disagree: existing.village_name !== incoming.village_name,
    },
    {
      label: "Phone number",
      existing: existing.phone ?? "No number given",
      next: incoming.phone ?? "No number given",
      disagree: existing.phone !== incoming.phone,
    },
    {
      label: "Last seen",
      existing: lastSeen(existing),
      next: lastSeen(incoming),
      disagree: false, // history, not a field the two records need to agree on
    },
  ];
}

export default function IdentityReviewPage() {
  const session = getSession();
  const org = useLiveQuery(
    () => (session ? db.org_cache.get(session.orgUnitId) : undefined),
    [session?.orgUnitId],
  );
  const { online } = useSyncStatus();
  const reviews =
    useLiveQuery(() => db.identity_review_cache.toArray(), [])?.sort((a, b) =>
      a.created_at < b.created_at ? -1 : 1,
    ) ?? [];
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (online) void refreshIdentityReviews();
  }, [online]);

  if (!online) {
    return (
      <div className={styles.page}>
        <DemoMarker />
        <div className={styles.offlineCard}>
          <div className={styles.offlineTitle}>Needs a connection</div>
          <div className={styles.offlineBody}>
            Deciding whether two records are the same person needs a live connection, so the
            decision is always made against the current record — not one that may have already
            changed. Reconnect to see the list.
          </div>
        </div>
      </div>
    );
  }

  const current = reviews[0];

  async function handleDecide(decision: IdentityDecision) {
    if (!current || busy) return;
    setBusy(true);
    try {
      await decideIdentityReview(current.id, decision);
      await refreshIdentityReviews();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={styles.page}>
      <DemoMarker />

      <div className={styles.pageHeader}>
        <div className={styles.pageTitle}>Is this the same person?</div>
        <div className={styles.pageSubtitle}>
          One pair at a time. Fields that match sit in plain rows; fields that differ are boxed,
          so you never have to spot the difference yourself. Two clear choices — no middle option,
          because a wrong merge is worse than a slow one.
        </div>
      </div>

      {!current ? (
        <div className={styles.empty}>Nothing to review right now.</div>
      ) : (
        <div className={styles.card}>
          <div className={styles.cardHeader}>
            <div>
              <div className={styles.cardHeaderTitle}>Possible same person</div>
              <div className={styles.cardHeaderMeta}>Pair 1 of {reviews.length} to review</div>
            </div>
            <div className={styles.cardHeaderMeta}>
              {org?.name ?? ""} · {session?.username ?? ""}
            </div>
          </div>

          <div className={styles.cardBody}>
            <div className={styles.namePair}>
              <div className={styles.nameBox}>
                <div className={styles.nameBoxLabel}>Existing record</div>
                <div className={styles.nameBoxValue}>{current.existing.name}</div>
              </div>
              <div className={styles.nameBox}>
                <div className={styles.nameBoxLabel}>New referral</div>
                <div className={styles.nameBoxValue}>{current.new.name}</div>
              </div>
            </div>

            {current.existing.name !== current.new.name && (
              <div className={styles.disagreeBanner}>
                <div className={styles.disagreeBannerLabel}>
                  Name is spelled differently — check carefully
                </div>
                <div className={styles.disagreeBannerValues}>
                  <div className={styles.disagreeBannerValue}>{current.existing.name}</div>
                  <div className={styles.disagreeBannerValue}>{current.new.name}</div>
                </div>
              </div>
            )}

            <div className={styles.table}>
              <div className={styles.tableHeaderRow}>
                <div className={styles.tableHeaderCell}>Field</div>
                <div className={styles.tableHeaderCell}>Existing</div>
                <div className={styles.tableHeaderCell}>New</div>
              </div>
              {fieldRows(current).map((row) => (
                <div
                  key={row.label}
                  className={`${styles.tableRow} ${row.disagree ? styles.tableRowDisagree : ""}`}
                >
                  <div className={styles.tableCellLabel}>{row.label}</div>
                  <div className={styles.tableCellValue}>{row.existing}</div>
                  <div className={styles.tableCellValue}>{row.next}</div>
                </div>
              ))}
            </div>
          </div>

          <div className={styles.actions}>
            <button
              className={`${styles.actionButton} ${styles.mergeButton}`}
              disabled={busy}
              onClick={() => handleDecide("merge")}
            >
              Same person — merge
            </button>
            <button
              className={`${styles.actionButton} ${styles.keepSeparateButton}`}
              disabled={busy}
              onClick={() => handleDecide("keep_separate")}
            >
              Different people — keep both
            </button>
          </div>
        </div>
      )}

      <div className={styles.footnote}>
        Only fields that differ are boxed; everything that matches sits in a plain row, so
        agreement is the quiet default and disagreement is the only thing that stands out.
      </div>
    </div>
  );
}
