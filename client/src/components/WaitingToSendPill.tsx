import styles from "./WaitingToSendPill.module.css";

/** Row-level indicator (brief §6): any referral holding an unsent change
 * carries this next to its state pill. */
export function WaitingToSendPill() {
  return <span className={styles.pill}>Waiting to send</span>;
}
