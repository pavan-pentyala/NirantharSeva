/** Mirrors server/app/schemas/sync.py — the frozen push/pull contract. */

const API_BASE = "/api";
const TOKEN_KEY = "nirantharseva_token";

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
 * `payload`, discriminated by `entity_type`. For entity_type "toy": payload
 * is {old_value, new_value}. For "referral": payload is {from_state,
 * to_state, actor_role, actor_user_id} — referral events are not yet
 * applied to any client cache (D1: the referral UI lands at Phase 4). */
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

/** Dev-only: the harness auto-logs in as a fixed user. Real auth/session
 * management is out of scope until the real UI lands (Phase 2+). */
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
