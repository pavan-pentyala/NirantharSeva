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
 * in direct sunlight or greyscale. */
export function StatePill({ state }: { state: string }) {
  const { label, family } = stateLabel(state);

  if (family === "overdue") {
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
