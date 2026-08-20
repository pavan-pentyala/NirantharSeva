import { useParams, useNavigate } from "react-router-dom";
import { DemoMarker } from "../components/DemoMarker";
import { StatePill } from "../components/StatePill";
import { db } from "../db/schema";
import { formatAgeSex } from "../domain/formatAgeSex";
import { ashaActionFor, ashaWaitingCopyFor } from "../domain/referralActions";
import { stateLabel } from "../domain/stateLabels";
import { relativeTimeSince } from "../domain/relativeTime";
import { timelineAttribution, timelineEntryLabel, timelineTimestamp } from "../domain/timeline";
import { useLiveQuery } from "../hooks/useLiveQuery";
import { transitionReferral } from "../sync/engine";
import styles from "./ReferralDetailPage.module.css";

export default function ReferralDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const referral = useLiveQuery(() => (id ? db.referral_cache.get(id) : undefined), [id]);
  const events =
    useLiveQuery(() => (id ? db.referral_event_cache.where("referral_id").equals(id).sortBy("seq") : []), [id]) ??
    [];

  if (!referral) {
    return (
      <div className={styles.page}>
        <DemoMarker />
        <div className={styles.notFound}>Referral not found on this phone.</div>
      </div>
    );
  }

  const { family } = stateLabel(referral.current_state);
  const overdue = family === "overdue";
  const action = ashaActionFor(referral.current_state);
  const waitingCopy = ashaWaitingCopyFor(referral.current_state);

  async function handleAction() {
    if (!action || !referral) return;
    await transitionReferral(referral.id, referral.current_state, action.toState);
  }

  return (
    <div className={styles.page}>
      <DemoMarker />

      <div className={styles.header}>
        <button className={styles.back} onClick={() => navigate(-1)} aria-label="Back">
          ←
        </button>
        <div className={styles.title}>{referral.patient_name}</div>
      </div>

      <div className={styles.body}>
        <div className={`${styles.summary} ${overdue ? styles.summaryOverdue : ""}`}>
          <div className={styles.demographics}>{formatAgeSex(referral.age, referral.sex)}</div>
          <div className={styles.reasonLine}>
            {[referral.reason, referral.target_org_name ? `sent to ${referral.target_org_name}` : null]
              .filter(Boolean)
              .join(" · ")}
          </div>
          <div className={styles.pillRow}>
            <StatePill state={referral.current_state} />
            <span className={styles.sinceLine}>since {relativeTimeSince(referral.updated_at)} ago</span>
          </div>
          {overdue && (
            <div className={styles.overdueCard}>
              This referral is overdue. The supervisor has been told.
            </div>
          )}
        </div>

        <div className={styles.timelineSection}>
          <div className={styles.timelineHeading}>What happened</div>
          {events.length === 0 ? (
            <div className={styles.timelineEmpty}>No events yet.</div>
          ) : (
            <div className={styles.timeline}>
              {[...events].reverse().map((event, i) => (
                <div key={event.seq} className={styles.timelineRow}>
                  <div className={styles.timelineRail}>
                    <span
                      className={`${styles.timelineDot} ${event.to_state === "ESCALATED" ? styles.timelineDotAlert : ""}`}
                    />
                    {i < events.length - 1 && <span className={styles.timelineConnector} />}
                  </div>
                  <div className={styles.timelineContent}>
                    <div
                      className={`${styles.timelineLabel} ${event.to_state === "ESCALATED" ? styles.timelineLabelAlert : ""}`}
                    >
                      {timelineEntryLabel(event)}
                    </div>
                    <div className={styles.timelineMeta}>
                      {timelineTimestamp(event.server_time)} · {timelineAttribution(event)}
                    </div>
                  </div>
                </div>
              ))}
              <div className={styles.timelineRow}>
                <div className={styles.timelineRail}>
                  <span className={styles.timelineDotHollow} />
                </div>
                <div className={styles.timelineWaiting}>
                  {waitingCopy ?? "Waiting for the next update."}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      <div className={styles.footer}>
        {action ? (
          <button className={styles.primaryButton} onClick={() => void handleAction()} data-testid="referral-action-button">
            {action.buttonLabel}
          </button>
        ) : (
          <div className={styles.waitingFooter}>{waitingCopy ?? "No action needed right now."}</div>
        )}
      </div>
    </div>
  );
}
