import { stateLabel } from "../domain/stateLabels";
import styles from "./StatePill.module.css";

const FINE_STATE_CLASS: Record<string, string> = {
  CREATED: "created",
  IN_TRANSIT: "intransit",
  ARRIVED: "arrived",
  TREATED: "treated",
  BACK_REFERRED: "backreferred",
};

/** The three-shape rule (README "The three-shape rule"): shape first,
 * colour second, a word always — so the state family reads correctly even
 * in direct sunlight or greyscale.
 *
 * `overdue` (D20, docs/PHASE5_PLAN.md) forces the overdue treatment on top
 * of whatever `state` would normally render as — used when `state` is
 * itself a *display* state (e.g. "IN_TRANSIT") for a referral whose real
 * current_state is "ESCALATED", so the pill shows the real state's label
 * with the alert shape, not the word "Overdue" replacing it. Omitted (or
 * state itself is "ESCALATED"), this behaves exactly as before P5.2. */
export function StatePill({ state, overdue }: { state: string; overdue?: boolean }) {
  const { label, family } = stateLabel(state);

  if (overdue || family === "overdue") {
    return (
      <span className={`${styles.pill} ${styles.overdue}`}>
        <span className={styles.bangMark}>!</span>
        {label}
      </span>
    );
  }

  if (family === "done") {
    const isLost = state === "LOST";
    return (
      <span className={`${styles.pill} ${isLost ? styles.lost : styles.closed}`}>
        <span>{isLost ? "✕" : "✓"}</span>
        {label}
      </span>
    );
  }

  const variant = FINE_STATE_CLASS[state] ?? "created";
  return <span className={`${styles.pill} ${styles[variant]}`}>{label}</span>;
}
