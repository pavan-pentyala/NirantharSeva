import { useNavigate } from "react-router-dom";
import { clearSession } from "../auth/session";
import styles from "./LogoutButton.module.css";

/** P7.3 B4. Clears the stored JWT only — never Dexie. Clearing the outbox
 * on logout would silently destroy any referral queued but not yet sent,
 * which is the exact failure this project exists to prevent. */
export function LogoutButton() {
  const navigate = useNavigate();

  function handleLogout() {
    clearSession();
    navigate("/login", { replace: true });
  }

  return (
    <button type="button" className={styles.button} onClick={handleLogout}>
      Log out
    </button>
  );
}
