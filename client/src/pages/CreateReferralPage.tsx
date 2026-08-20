import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { getSession } from "../auth/session";
import { DemoMarker } from "../components/DemoMarker";
import { db } from "../db/schema";
import { useLiveQuery } from "../hooks/useLiveQuery";
import { createReferral } from "../sync/engine";
import styles from "./CreateReferralPage.module.css";

type Urgency = "urgent" | "soon" | "routine";
type Sex = "M" | "F";

export default function CreateReferralPage() {
  const navigate = useNavigate();
  const session = getSession();

  const village = useLiveQuery(() => (session ? db.org_cache.get(session.orgUnitId) : undefined), [
    session?.orgUnitId,
  ]);
  const facilities = useLiveQuery(() => db.org_cache.where("type").equals("PHC").toArray(), []) ?? [];

  const [patientName, setPatientName] = useState("");
  const [age, setAge] = useState("");
  const [sex, setSex] = useState<Sex>("M");
  const [phone, setPhone] = useState("");
  const [reason, setReason] = useState("");
  const [urgency, setUrgency] = useState<Urgency>("urgent");
  const [targetOrgId, setTargetOrgId] = useState<string>("");
  const [saved, setSaved] = useState<{ patientName: string; savedOffline: boolean } | null>(null);

  const effectiveTargetOrgId = targetOrgId || facilities[0]?.id || "";

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!patientName.trim()) return;
    const savedOffline = !navigator.onLine;
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
          <button className={styles.primaryButton} type="submit" data-testid="save-referral-button">
            Save referral
          </button>
        </div>
      </form>
    </div>
  );
}
