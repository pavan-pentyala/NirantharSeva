import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { login } from "../api/client";
import { getSession, isAuthenticated } from "../auth/session";
import { DemoMarker } from "../components/DemoMarker";
import { refreshOrgCache, startAutoFlush } from "../sync/engine";
import { homeRouteFor } from "../routes";
import styles from "./LoginPage.module.css";

export default function LoginPage() {
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (isAuthenticated()) {
    const session = getSession();
    return <Navigate to={homeRouteFor(session?.role ?? "")} replace />;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(username, password);
      startAutoFlush();
      void refreshOrgCache();
      const session = getSession();
      navigate(homeRouteFor(session?.role ?? ""), { replace: true });
    } catch {
      setError("Wrong username or password.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className={styles.page}>
      <DemoMarker />
      <div className={styles.content}>
        <div className={styles.brand}>
          <div className={styles.brandName}>NirantharSeva</div>
          <div className={styles.brandTagline}>Referral tracking</div>
        </div>

        <form className={styles.form} onSubmit={handleSubmit}>
          <label className={styles.field}>
            <span className={styles.label}>Username</span>
            <input
              className={styles.input}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              data-testid="username-input"
            />
          </label>

          <label className={styles.field}>
            <span className={styles.label}>Password</span>
            <input
              className={styles.input}
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              data-testid="password-input"
            />
          </label>

          {error && (
            <div className={styles.error} role="alert">
              {error}
            </div>
          )}

          <button className={styles.submit} type="submit" disabled={submitting} data-testid="login-button">
            Log in
          </button>
        </form>

        <div className={styles.footer}>Works without signal. You stay logged in on this phone.</div>
      </div>
    </div>
  );
}
