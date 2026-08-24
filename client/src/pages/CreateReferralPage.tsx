import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { getSession } from "../auth/session";
import { DemoMarker } from "../components/DemoMarker";
import { db, type OrgCacheRow } from "../db/schema";
import { useLiveQuery } from "../hooks/useLiveQuery";
import { createReferral } from "../sync/engine";
import styles from "./CreateReferralPage.module.css";

type Urgency = "urgent" | "soon" | "routine";
type Sex = "M" | "F";

/** Walks the org tree up from `startId` (an ASHA's own village) looking for
 * the nearest PHC ancestor, so the facility picker can default to it — the
 * facility she'd send to on the ordinary path, not whichever row Postgres
 * happened to return first. */
function nearestPhcAncestor(startId: string | undefined, orgById: Map<string, OrgCacheRow>): string | undefined {
  let current = startId ? orgById.get(startId) : undefined;
  while (current) {
    if (current.type === "PHC") return current.id;
    current = current.parent_id ? orgById.get(current.parent_id) : undefined;
  }
  return undefined;
}

export default function CreateReferralPage() {
  const navigate = useNavigate();
  const session = getSession();

  const village = useLiveQuery(() => (session ? db.org_cache.get(session.orgUnitId) : undefined), [
    session?.orgUnitId,
  ]);
  const allOrgs = useLiveQuery(() => db.org_cache.toArray(), []) ?? [];
  const orgById = new Map(allOrgs.map((o) => [o.id, o]));
  const facilities = [...(useLiveQuery(() => db.org_cache.where("type").equals("PHC").toArray(), []) ?? [])].sort(
    (a, b) => a.name.localeCompare(b.name),
  );

  const [patientName, setPatientName] = useState("");
  const [age, setAge] = useState("");
  const [sex, setSex] = useState<Sex>("M");
  const [phone, setPhone] = useState("");
  const [reason, setReason] = useState("");
  const [urgency, setUrgency] = useState<Urgency>("urgent");
  const [targetOrgId, setTargetOrgId] = useState<string>("");
  const [saved, setSaved] = useState<{ patientName: string; savedOffline: boolean } | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const defaultFacilityId = nearestPhcAncestor(session?.orgUnitId, orgById) ?? facilities[0]?.id ?? "";
  const effectiveTargetOrgId = targetOrgId || defaultFacilityId;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!patientName.trim() || submitting) return;
    const savedOffline = !navigator.onLine;
    setSubmitting(true);
    try {
      await createReferral({
        patientName: patientName.trim(),
        age: age ? Number(age) : undefined,
        sex,
        phone: phone.trim() || undefined,
        reason: reason.trim() || undefined,
        priority: urgency,
        targetOrgId: effectiveTargetOrgId || undefined,
      });
      setSaved({ patientName: patientName.trim(), savedOffline });
    } finally {
      setSubmitting(false);
    }
  }

  function resetForm() {
    setPatientName("");
    setAge("");
    setSex("M");
    setPhone("");
    setReason("");
    setUrgency("urgent");
    setSaved(null);
  }

  if (saved) {
    return (
      <div className={styles.page}>
        <DemoMarker />
        <div className={styles.confirmContent}>
          <div className={styles.checkCircle}>✓</div>
          <div className={styles.confirmTitle}>Referral saved</div>
          <div className={styles.confirmBody}>{saved.patientName}&rsquo;s referral is saved on your phone.</div>
          {saved.savedOffline && (
            <div className={styles.noSignalCard}>
              <span className={styles.noSignalDot} />
              <div>
                <div className={styles.noSignalTitle}>No signal right now</div>
                <div className={styles.noSignalBody}>
                  It will send by itself when your phone finds signal. You do not need to do anything.
                </div>
              </div>
            </div>
          )}
        </div>
        <div className={styles.confirmFooter}>
          <button className={styles.primaryButton} onClick={() => navigate("/referrals")}>
            Back to my referrals
          </button>
          <button className={styles.secondaryButton} onClick={resetForm}>
            Add another referral
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <DemoMarker />
      <div className={styles.header}>
        <button className={styles.back} onClick={() => navigate(-1)} aria-label="Back">
          ←
        </button>
        <div className={styles.title}>New referral</div>
      </div>

      <form className={styles.form} onSubmit={handleSubmit}>
        <label className={styles.field}>
          <span className={styles.label}>Patient name</span>
          <input
            className={styles.input}
            value={patientName}
            onChange={(e) => setPatientName(e.target.value)}
            data-testid="patient-name-input"
          />
        </label>

        <div className={styles.row}>
          <label className={styles.field} style={{ flex: 1 }}>
            <span className={styles.label}>Age</span>
            <input
              className={styles.input}
              type="number"
              min={0}
              placeholder="Years"
              value={age}
              onChange={(e) => setAge(e.target.value)}
            />
          </label>
          <div className={styles.field} style={{ flex: 1 }}>
            <span className={styles.label}>Sex</span>
            <div className={styles.toggleRow}>
              {(["M", "F"] as const).map((option) => (
                <button
                  key={option}
                  type="button"
                  className={`${styles.toggleButton} ${sex === option ? styles.toggleButtonActive : ""}`}
                  onClick={() => setSex(option)}
                >
                  {option}
                </button>
              ))}
            </div>
          </div>
        </div>

        <label className={styles.field}>
          <span className={styles.label}>Phone number</span>
          <input
            className={styles.input}
            placeholder="Optional"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
          />
        </label>

        <div className={styles.field}>
          <span className={styles.label}>Village</span>
          <div className={styles.readonlyField}>
            <span>{village?.name ?? "—"}</span>
            <span className={styles.yoursTag}>yours</span>
          </div>
        </div>

        <label className={styles.field}>
          <span className={styles.label}>Reason for referral</span>
          <input className={styles.input} value={reason} onChange={(e) => setReason(e.target.value)} />
        </label>

        <div className={styles.field}>
          <span className={styles.label}>How urgent</span>
          <div className={styles.urgencyRow}>
            {(
              [
                ["urgent", "Urgent"],
                ["soon", "Soon"],
                ["routine", "Routine"],
              ] as const
            ).map(([value, label]) => (
              <button
                key={value}
                type="button"
                className={`${styles.urgencyButton} ${urgency === value ? styles[`urgency_${value}`] : ""}`}
                onClick={() => setUrgency(value)}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        <div className={styles.field}>
          <span className={styles.label}>Sending to</span>
          {facilities.length > 1 ? (
            <select
              className={styles.select}
              value={effectiveTargetOrgId}
              onChange={(e) => setTargetOrgId(e.target.value)}
            >
              {facilities.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.name}
                </option>
              ))}
            </select>
          ) : (
            <div className={styles.sendingToChip}>
              <span>{facilities[0]?.name ?? "—"}</span>
            </div>
          )}
        </div>

        <div className={styles.footer}>
          <button
            className={styles.primaryButton}
            type="submit"
            disabled={submitting}
            data-testid="save-referral-button"
          >
            Save referral
          </button>
        </div>
      </form>
    </div>
  );
}
