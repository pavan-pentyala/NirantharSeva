import { clearToken, getToken } from "../api/client";

export interface Session {
  username: string;
  role: string;
  orgUnitId: string;
}

function base64UrlDecode(segment: string): string {
  const padded = segment
    .replace(/-/g, "+")
    .replace(/_/g, "/")
    .padEnd(Math.ceil(segment.length / 4) * 4, "=");
  return atob(padded);
}

/** Decodes the stored JWT's claims for UI routing/display only — which
 * screen to land on after login, what the role chip shows — never a
 * security boundary. The server independently re-verifies the signature
 * and re-resolves role/org from app_user on every request (ADR-006); a
 * stale or tampered read here can only mis-route the UI, never grant
 * access the server wouldn't already grant on its own. */
export function getSession(): Session | null {
  const token = getToken();
  if (!token) return null;
  const parts = token.split(".");
  if (parts.length !== 3) return null;
  try {
    const claims = JSON.parse(base64UrlDecode(parts[1])) as {
      sub: string;
      role: string;
      org_unit_id: string;
      exp: number;
    };
    if (claims.exp * 1000 <= Date.now()) return null;
    return { username: claims.sub, role: claims.role, orgUnitId: claims.org_unit_id };
  } catch {
    return null;
  }
}

export function isAuthenticated(): boolean {
  return getSession() !== null;
}

/** P7.3 B4: clears the token only. Deliberately does not touch Dexie — the
 * outbox and every cache table survive a logout untouched, so a referral
 * queued but not yet sent is never lost by logging out. */
export function clearSession(): void {
  clearToken();
}
