import { Navigate, Outlet } from "react-router-dom";
import { isAuthenticated } from "./session";

/** Client-side gate only, for navigation UX — the server enforces the real
 * boundary on every request (ADR-006). A tampered or missing token here
 * just bounces the screen to /login, nothing more. */
export function RequireAuth() {
  if (!isAuthenticated()) return <Navigate to="/login" replace />;
  return <Outlet />;
}
