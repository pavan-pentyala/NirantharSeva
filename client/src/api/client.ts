/** Mirrors server/app/schemas/sync.py — the frozen push/pull contract. */

const API_BASE = "/api";
const TOKEN_KEY = "nirantharseva_token";

/** Raw stored JWT, or null if never logged in. Client-side decoding of
 * this token (client/src/auth/session.ts) is a UI convenience only — the
 * server never trusts a client's claimed identity (ADR-006); it re-resolves
 * role/org from app_user on every request. */
export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export interface Op {
  op_id: string;
  entity: string;
  entity_id: string;
  operation: string;
  payload: Record<string, unknown>;
  lamport: number;
  device_time: string;
}

export type OpStatus = "accepted" | "accepted_stale" | "conflict" | "rejected";

export interface OpResult {
  op_id: string;
  status: OpStatus;
  server_seq: number | null;
  detail: Record<string, unknown> | null;
}

export interface PushResponse {
  results: OpResult[];
  server_lamport: number;
}

/** Generic pull envelope (D3, docs/decisions/ADR-004.md). Fields the sync
 * engine itself reads stay flat; everything only the domain reads is in
 * `payload`. `entity_type` is always "referral" since the toy model's drop
 * (migration 0006, Phase 4.3). payload is {from_state, to_state,
 * actor_role, actor_user_id, patient_name, age, sex, reason, priority,
 * target_org_name} (D14/ADR-010) — folded into referral_cache by
 * client/src/sync/engine.ts's applyPulledEvents. */
export interface EventOut {
  seq: number;
  entity_type: string;
  entity_id: string;
  op_id: string;
  device_id: string;
  lamport: number;
  device_time: string;
  server_time: string;
  payload: Record<string, unknown>;
}

export interface PullResponse {
  events: EventOut[];
  cursor: number;
  has_more: boolean;
}

function authHeader(): Record<string, string> {
  const token = localStorage.getItem(TOKEN_KEY);
  return token ? { authorization: `Bearer ${token}` } : {};
}

export async function login(username: string, password: string): Promise<void> {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) throw new Error(`login failed: ${res.status}`);
  const body = (await res.json()) as { access_token: string };
  localStorage.setItem(TOKEN_KEY, body.access_token);
}

export async function push(deviceId: string, ops: Op[]): Promise<PushResponse> {
  const res = await fetch(`${API_BASE}/sync/push`, {
    method: "POST",
    headers: { "content-type": "application/json", ...authHeader() },
    body: JSON.stringify({ device_id: deviceId, ops }),
  });
  if (!res.ok) throw new Error(`push failed: ${res.status}`);
  return res.json();
}

export async function pull(since: number, limit = 500): Promise<PullResponse> {
  const res = await fetch(`${API_BASE}/sync/pull?since=${since}&limit=${limit}`, {
    headers: authHeader(),
  });
  if (!res.ok) throw new Error(`pull failed: ${res.status}`);
  return res.json();
}

export interface OrgUnit {
  id: string;
  name: string;
  type: string;
  parent_id: string | null;
}

/** P4.2 — org names/hierarchy, not patient data, unscoped server-side
 * (app/api/org_units.py). Rarely changes; the client caches the result
 * rather than calling this on every screen render (client/src/db/schema.ts's
 * org_cache). */
export async function listOrgUnits(): Promise<OrgUnit[]> {
  const res = await fetch(`${API_BASE}/org_units`, { headers: authHeader() });
  if (!res.ok) throw new Error(`org_units failed: ${res.status}`);
  const body = (await res.json()) as { org_units: OrgUnit[] };
  return body.org_units;
}

/** Mirrors server/app/schemas/identity.py. Screen 6 — docs/decisions/
 * ADR-013.md: a plain REST pair, never the outbox. */
export interface IdentityReviewPatient {
  id: string;
  name: string;
  age: number | null;
  sex: string | null;
  phone: string | null;
  village_name: string | null;
  last_seen_reason: string | null;
  last_seen_at: string | null;
}

export interface IdentityReviewRow {
  id: string;
  score: number;
  method: string;
  created_at: string;
  existing: IdentityReviewPatient;
  new: IdentityReviewPatient;
}

export async function listIdentityReviews(): Promise<IdentityReviewRow[]> {
  const res = await fetch(`${API_BASE}/identity/reviews`, { headers: authHeader() });
  if (!res.ok) throw new Error(`identity reviews failed: ${res.status}`);
  const body = (await res.json()) as { reviews: IdentityReviewRow[] };
  return body.reviews;
}

export type IdentityDecision = "merge" | "keep_separate";

export interface IdentityDecisionResult {
  id: string;
  status: "merged" | "kept_separate";
}

export async function decideIdentityReview(
  reviewId: string,
  decision: IdentityDecision,
): Promise<IdentityDecisionResult> {
  const res = await fetch(`${API_BASE}/identity/reviews/${reviewId}/decide`, {
    method: "POST",
    headers: { "content-type": "application/json", ...authHeader() },
    body: JSON.stringify({ decision }),
  });
  if (!res.ok) throw new Error(`decide failed: ${res.status}`);
  return res.json();
}
