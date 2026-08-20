import { useNavigate } from "react-router-dom";
import { DemoMarker } from "../components/DemoMarker";
import styles from "./PlaceholderPage.module.css";

/** Screens 4 (supervisor dashboard) and 6 (ANM identity review) are routed
 * here in P4.2 — see docs/PHASE4_PLAN.md's screen-scope decision. Screen 4
 * needs Phase 5's SSE stream to be the point of the screen at all; Screen 6
 * renders a match Phase 6's identity-resolution pipeline doesn't exist yet
 * to produce. Both get a real route so navigation is complete and nothing
 * 404s from inside the app shell — not a stub for its own screen's build. */
export default function PlaceholderPage({ title, comingIn }: { title: string; comingIn: string }) {
  const navigate = useNavigate();
  return (
    <div className={styles.page}>
      <DemoMarker />
      <div className={styles.content}>
        <div className={styles.title}>{title}</div>
        <div className={styles.body}>Coming in {comingIn}.</div>
        <button className={styles.button} onClick={() => navigate("/login")}>
          Back to login
        </button>
      </div>
    </div>
  );
}
