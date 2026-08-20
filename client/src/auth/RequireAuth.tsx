import { useEffect } from "react";
import { Navigate, Outlet } from "react-router-dom";
import { refreshOrgCache, startAutoFlush } from "../sync/engine";
import { isAuthenticated } from "./session";

/** Client-side gate only, for navigation UX — the server enforces the real
 * boundary on every request (ADR-006). A tampered or missing token here
 * just bounces the screen to /login, nothing more.
 *
 * Also where the sync engine actually starts on a fresh app boot with an
 * already-valid session (a reopened tab, a reload, a PWA relaunch) — not
 * just right after typing a password. LoginPage's own startAutoFlush()
 * call only covers the login moment itself; without this, a device that
 * reopens the app with a still-valid token never begins flushing its
 * outbox at all. Found by client-kill-resume.spec.ts's port to a real
 * screen (Phase 4.3) — the "kill and reopen" step exercises exactly this
 * path and the toy harness never had an equivalent gap to expose.
 * startAutoFlush() is idempotent (its own internal guard), so calling it
 * again here alongside LoginPage's own call is safe. */
export function RequireAuth() {
  useEffect(() => {
    if (isAuthenticated()) {
      startAutoFlush();
      void refreshOrgCache();
    }
  }, []);

  if (!isAuthenticated()) return <Navigate to="/login" replace />;
  return <Outlet />;
}
