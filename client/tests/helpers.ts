import type { APIRequestContext } from "@playwright/test";

const API_BASE = "http://localhost:8000";

export async function loginToken(request: APIRequestContext): Promise<string> {
  const res = await request.post(`${API_BASE}/auth/login`, {
    data: { username: "asha1", password: "dev" },
  });
  const body = await res.json();
  return body.access_token;
}

/** Pulls every event since seq 0, following has_more, and returns how many
 * times each op_id appeared — duplicates are visible, not silently deduped. */
export async function pullAllOpIds(
  request: APIRequestContext,
  token: string,
): Promise<Map<string, number>> {
  const counts = new Map<string, number>();
  let since = 0;
  for (;;) {
    const res = await request.get(`${API_BASE}/sync/pull?since=${since}&limit=1000`, {
      headers: { authorization: `Bearer ${token}` },
    });
    const body = await res.json();
    for (const e of body.events) {
      counts.set(e.op_id, (counts.get(e.op_id) ?? 0) + 1);
    }
    since = body.cursor;
    if (!body.has_more) break;
  }
  return counts;
}
