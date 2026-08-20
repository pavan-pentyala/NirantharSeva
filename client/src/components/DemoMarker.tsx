import styles from "./DemoMarker.module.css";

/** Brief §8 hard constraint: a visible "Demonstration system — synthetic
 * data only" marker on every screen. */
export function DemoMarker() {
  return <div className={styles.marker}>Demonstration system — synthetic data only</div>;
}
