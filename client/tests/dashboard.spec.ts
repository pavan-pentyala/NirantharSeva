import { test, expect } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SCREENSHOT_DIR = path.join(__dirname, "..", "..", "docs", "screenshots");

async function login(page: import("@playwright/test").Page, username: string) {
  await page.goto("/login");
  await page.getByTestId("username-input").fill(username);
  await page.getByTestId("password-input").fill("dev");
  await page.getByTestId("login-button").click();
}

test("supervisor dashboard loads its steady-state stat strip from the live stream", async ({ page }) => {
  await login(page, "supervisor1");
  await expect(page).toHaveURL(/\/supervisor$/);

  // The first SSE message on connect (docs/decisions/ADR-011.md) — no
  // referral list wait needed, just that the stream delivered a real
  // snapshot and Screen 4 rendered it from Dexie, not from the network
  // directly (docs/PHASE5_PLAN.md "Traps").
  await expect(page.getByText("Live")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("Open referrals")).toBeVisible();
  await expect(page.getByText("Overdue — act now")).toBeVisible();
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, "screen4-supervisor-dashboard.png") });
});

test("EventSource recovers after a connectivity drop and the dashboard re-converges", async ({
  page,
  context,
}) => {
  // Stands in for docs/PHASE5_PLAN.md P5.2's "kill and restart the API"
  // exit criterion: a Playwright spec running inside the client container
  // has no way to restart a sibling container, but EventSource's own
  // reconnect logic (plan §9.2 — the reason SSE was chosen over a
  // hand-rolled fetch loop) doesn't distinguish "the server restarted"
  // from "the network dropped and came back" — both are the same
  // native-retry path, and this exercises it the same way
  // offline-sync.spec.ts already exercises the ordinary sync engine's
  // recovery.
  await login(page, "supervisor1");
  await expect(page.getByText("Live")).toBeVisible({ timeout: 15_000 });

  await context.setOffline(true);
  await page.waitForTimeout(1000);
  await context.setOffline(false);

  await expect(page.getByText("Live")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("Open referrals")).toBeVisible();
});

/** P5.2's headline (docs/PHASE5_PLAN.md, plan §9.3): a breach appears on
 * the dashboard live, with no page refresh, and the escalated referral
 * keeps its real state label on Screens 1/3/5 (D20).
 *
 * Requires demo config — the sweep only escalates a referral once its SLA
 * window has actually elapsed, and there is no API path that lets a test
 * backdate that window (state_entered_at is set from the server's own
 * clock at write time, never from client input). Start a second, demo-scale
 * scheduler alongside the ordinary one before running this file:
 *   docker compose run --rm -d --name demo-scheduler \
 *     -e SLA_SCALE=0.0004 -e SWEEP_INTERVAL_SECONDS=5 scheduler
 * (0.0004 * 24h ≈ 35s for the CREATED SLA, ≈ 69s for IN_TRANSIT's 48h —
 * both comfortably inside this file's wait timeouts). Stop it after with
 * `docker stop demo-scheduler` (it was started with --rm, so stopping it
 * also removes it — no separate `docker rm` needed, and `docker ps -a`
 * is worth checking anyway; see docs/PHASE2_OBSERVATIONS.md observation 35
 * for why a container from this exact pattern can outlive expectations).
 * The ordinary `scheduler` service keeps running throughout at its own
 * production-scale config regardless — this is additive, not a swap.
 */
test("a new breach appears on the supervisor dashboard without a page refresh", async ({
  page,
  context,
}) => {
  test.setTimeout(150_000);
  // Random hex, not Date.now() (two runs would otherwise create near-
  // identical names that clear AUTO_ACCEPT against each other), and no
  // "Test Patient" boilerplate shared with other spec files' fixture
  // names (that alone still scores in the review band and would queue a
  // spurious identity_review pair, cluttering a live demo of Screen 6) —
  // now that create_referral resolves patients through the real fuzzy
  // pipeline (P6.2). See docs/PHASE2_OBSERVATIONS.md.
  const patientName = `Breach Watch Fixture ${crypto.randomUUID().slice(0, 8)}`;

  await login(page, "asha_a");
  await expect(page).toHaveURL(/\/referrals$/);
  await page.getByTestId("new-referral-button").click();
  await page.getByTestId("patient-name-input").fill(patientName);
  await page.getByTestId("save-referral-button").click();
  await expect(page.getByText("Referral saved")).toBeVisible();
  await page.getByText("Back to my referrals").click();
  await expect(page).toHaveURL(/\/referrals$/);

  const supervisorContext = await context.browser()!.newContext();
  const supervisorPage = await supervisorContext.newPage();
  await login(supervisorPage, "supervisor1");
  await expect(supervisorPage).toHaveURL(/\/supervisor$/);
  await expect(supervisorPage.getByText("Live")).toBeVisible({ timeout: 15_000 });

  // No reload anywhere between here and the assertion — the point of the
  // whole feature is that this row arrives on the already-open connection.
  const row = supervisorPage.getByText(patientName, { exact: true });
  await expect(row).toBeVisible({ timeout: 120_000 });
  await expect(supervisorPage.getByText("New overdue referral:")).toBeVisible();
  await supervisorPage.screenshot({
    path: path.join(SCREENSHOT_DIR, "screen4-supervisor-dashboard-new-breach.png"),
  });
  await supervisorContext.close();

  // D20 on Screen 1: the row keeps its real state label (this referral
  // never left CREATED) and gains the overdue treatment, not the word
  // "Overdue" replacing the label.
  await page.reload();
  const ashaRow = page.getByTestId("referral-row").filter({ hasText: patientName });
  await expect(ashaRow).toBeVisible();
  await expect(ashaRow.getByText("Not travelled yet")).toBeVisible();
  await ashaRow.scrollIntoViewIfNeeded();
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, "screen1-d20-overdue-overlay.png") });

  // D20 on Screen 3: real state label + overdue banner + the action she'd
  // have had anyway ("Mark as sent" for CREATED), not "no action at all".
  await ashaRow.click();
  await expect(page).toHaveURL(/\/referrals\/[0-9a-f-]+$/);
  await expect(page.getByText("Not travelled yet")).toBeVisible();
  await expect(page.getByText("This referral is overdue. The supervisor has been told.")).toBeVisible();
  await expect(page.getByTestId("referral-action-button")).toHaveText("Mark as sent");
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, "screen3-d20-overdue-overlay.png") });
});

/** D20 on Screen 5, and D22's resolution path exercised from the client
 * side: a referral breached in IN_TRANSIT must still appear under MO's
 * "On the way" tab (not vanish, since GUARDS[ESCALATED]={SYSTEM} means it
 * is technically in a state no MO tab matches) with the overlay treatment,
 * and her "Arrived" button must still work — which requires
 * IncomingReferralsPage to send from_state="ESCALATED" (the real
 * current_state), not the display state, exactly the bug this phase's own
 * first draft had (moActionFor re-derived from currentState inside
 * handleAdvance, which has no MO_ACTIONS entry for "ESCALATED" and
 * silently no-opped the button). Needs demo config — see the previous
 * test's docstring for how to run the scheduler for this file.
 */
test("an IN_TRANSIT breach still shows on MO's board with a working action button", async ({
  page,
}) => {
  test.setTimeout(150_000);
  // Random hex, no shared boilerplate — see the first test in this file.
  const patientName = `Overlay Relay Fixture ${crypto.randomUUID().slice(0, 8)}`;

  await login(page, "asha_a");
  await expect(page).toHaveURL(/\/referrals$/);
  await page.getByTestId("new-referral-button").click();
  await page.getByTestId("patient-name-input").fill(patientName);
  await page.getByTestId("save-referral-button").click();
  await expect(page.getByText("Referral saved")).toBeVisible();
  await page.getByText("Back to my referrals").click();
  await expect(page).toHaveURL(/\/referrals$/);

  const ashaRow = page.getByTestId("referral-row").filter({ hasText: patientName });
  await ashaRow.click();
  await expect(page).toHaveURL(/\/referrals\/[0-9a-f-]+$/);
  await page.getByTestId("referral-action-button").click(); // CREATED -> IN_TRANSIT
  await expect(page.getByText("On the way")).toBeVisible();

  const moPage = await page.context().browser()!.newContext().then((c) => c.newPage());
  await login(moPage, "mo1");
  await expect(moPage).toHaveURL(/\/mo\/incoming$/);

  const moCard = moPage.getByTestId("incoming-card").filter({ hasText: patientName });
  await expect(moCard).toBeVisible(); // present immediately — it's IN_TRANSIT already, not yet overdue
  // The actual wait: genuinely for the escalation, not just for the card
  // to exist (it already does). cardOverdue only applies once
  // current_state flips to ESCALATED — a hashed CSS-module class name
  // still contains the original name as a substring.
  await expect(moCard).toHaveClass(/cardOverdue/, { timeout: 100_000 });
  await expect(moCard.getByText("On the way")).toBeVisible(); // real state label, not "Overdue"
  await moPage.screenshot({ path: path.join(SCREENSHOT_DIR, "screen5-d20-overdue-overlay.png") });

  await moCard.getByTestId("advance-button").click(); // resolves the escalation (D22) and moves to ARRIVED
  await expect(moCard).toBeHidden();
  await moPage.getByText("At the centre").click();
  await expect(moPage.getByTestId("incoming-card").filter({ hasText: patientName })).toBeVisible();
});
