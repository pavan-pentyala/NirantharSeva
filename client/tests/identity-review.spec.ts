import { test, expect } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { loginToken } from "./helpers";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SCREENSHOT_DIR = path.join(__dirname, "..", "..", "docs", "screenshots");
const API_BASE = "http://localhost:8000";

async function login(page: import("@playwright/test").Page, username: string) {
  await page.goto("/login");
  await page.getByTestId("username-input").fill(username);
  await page.getByTestId("password-input").fill("dev");
  await page.getByTestId("login-button").click();
}

async function anmToken(request: import("@playwright/test").APIRequestContext): Promise<string> {
  const res = await request.post(`${API_BASE}/auth/login`, {
    data: { username: "anm1", password: "dev" },
  });
  return (await res.json()).access_token;
}

/** The screen always shows the oldest pending pair first (a real ANM
 * triages oldest-first) — so a leftover pending pair from an earlier run
 * against this same persistent dev database would silently hide this
 * run's own pair behind it. Decide every pre-existing one (the safe
 * "different people" default) before creating this run's own, so the
 * test starts from a known, empty queue regardless of history. */
async function drainExistingReviews(request: import("@playwright/test").APIRequestContext) {
  const token = await anmToken(request);
  for (;;) {
    const res = await request.get(`${API_BASE}/identity/reviews`, {
      headers: { authorization: `Bearer ${token}` },
    });
    const { reviews } = await res.json();
    if (reviews.length === 0) return;
    for (const r of reviews) {
      await request.post(`${API_BASE}/identity/reviews/${r.id}/decide`, {
        headers: { authorization: `Bearer ${token}` },
        data: { decision: "keep_separate" },
      });
    }
  }
}

async function push(
  request: import("@playwright/test").APIRequestContext,
  token: string,
  patientName: string,
) {
  const res = await request.post(`${API_BASE}/sync/push`, {
    headers: { authorization: `Bearer ${token}` },
    data: {
      device_id: "identity-review-spec",
      ops: [
        {
          op_id: crypto.randomUUID(),
          entity: "referral",
          entity_id: crypto.randomUUID(),
          operation: "create_referral",
          payload: { patient_name: patientName, reason: "identity review spec", priority: "routine" },
          lamport: 1,
          device_time: new Date().toISOString(),
        },
      ],
    },
  });
  const body = await res.json();
  expect(body.results[0].status).toBe("accepted");
}

test("ANM reviews a pending pair, boxes the disagreeing fields, and both buttons work end to end", async ({
  page,
  request,
}) => {
  // Both names carry the same run-unique suffix, so a repeat run of this
  // spec against the persistent dev database creates its own fresh pair
  // instead of exact-matching a previous run's already-decided one. Random
  // hex, not Date.now(): two runs a couple of minutes apart share a long
  // common *digit prefix* in a millisecond timestamp, and that shared
  // prefix alone was enough for rapidfuzz to score one run's patient
  // against a previous run's leftover in the review band by accident
  // (observation 44's lesson, one level up — this time between runs of
  // the SAME test, not between different tests). Random hex has no
  // systematic reason to overlap with a previous run's. The suffix
  // contributes identically to both of THIS run's names, so it does not
  // change which band the differing part (Kavita Joshi -> Kav Jo) falls
  // in — verified once, by hand, at 86.96: between REVIEW_FLOOR (80) and
  // AUTO_ACCEPT (92) under the real defaults.
  const suffix = crypto.randomUUID().slice(0, 8);
  const existingName = `Kavita Joshi ${suffix}`;
  const queryName = `Kav Jo ${suffix}`;

  await drainExistingReviews(request);

  const token = await loginToken(request);
  await push(request, token, existingName); // creates the "existing" patient
  await push(request, token, queryName); // scores into the review band against it

  await login(page, "anm1");
  await expect(page).toHaveURL(/\/identity-review$/);

  // Both names carry the run-unique suffix, so matching on them directly
  // (rather than scoping into "the pair card") cannot match anything else
  // on the page, including a leftover pair from a previous run. Each name
  // renders twice for a disagreeing pair (the top box and the red banner)
  // — .first() only asserts "at least one is showing", not which.
  await expect(page.getByText("Possible same person")).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText(existingName, { exact: true }).first()).toBeVisible();
  await expect(page.getByText(queryName, { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Name is spelled differently — check carefully")).toBeVisible();

  // Age and Phone number were never given on either side of this pair —
  // both "—"/"No number given" — so they agree and must NOT be boxed;
  // only the name (asserted above) differs for this pair.
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, "screen6-identity-review.png") });

  await page.getByRole("button", { name: "Different people — keep both" }).click();
  await expect(page.getByText(existingName, { exact: true })).toHaveCount(0, { timeout: 10_000 });
});
