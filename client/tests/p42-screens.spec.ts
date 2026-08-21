import { test, expect } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SCREENSHOT_DIR = path.join(__dirname, "..", "..", "docs", "screenshots");

test("ASHA creates a referral offline, it appears in the list and detail after reconnect, then MO advances it", async ({
  page,
  context,
}) => {
  // Random hex, not Date.now() (two runs would otherwise create near-
  // identical names that clear AUTO_ACCEPT against each other), and no
  // "Test Patient" boilerplate shared with other spec files' fixture
  // names (that alone still scores in the review band and would queue a
  // spurious identity_review pair, cluttering a live demo of Screen 6) —
  // now that create_referral resolves patients through the real fuzzy
  // pipeline (P6.2). See docs/PHASE2_OBSERVATIONS.md.
  const patientName = `Reconnect Sync Fixture ${crypto.randomUUID().slice(0, 8)}`;

  await page.goto("/login");
  await page.getByTestId("username-input").fill("asha_a");
  await page.getByTestId("password-input").fill("dev");
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, "screen7-login.png") });
  await page.getByTestId("login-button").click();
  await expect(page).toHaveURL(/\/referrals$/);
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, "screen1-asha-referral-list.png") });

  // Screen 2, offline.
  await context.setOffline(true);
  await page.getByTestId("new-referral-button").click();
  await expect(page).toHaveURL(/\/referrals\/new$/);
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, "screen2-create-referral-form.png") });

  await page.getByTestId("patient-name-input").fill(patientName);
  await page.getByTestId("save-referral-button").click();

  await expect(page.getByText("Referral saved")).toBeVisible();
  await expect(page.getByText("No signal right now")).toBeVisible();
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, "screen2-saved-offline-confirmation.png") });

  await page.getByText("Back to my referrals").click();
  await expect(page).toHaveURL(/\/referrals$/);

  const row = page.getByTestId("referral-row").filter({ hasText: patientName });
  await expect(row).toBeVisible();
  await expect(row.getByText("Waiting to send")).toBeVisible();
  await expect(row.getByText("Not travelled yet")).toBeVisible();
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, "screen1-offline-with-pending.png") });

  // Reconnect — the optimistic row must already be correct; only the
  // "Waiting to send" pill should disappear once it actually syncs.
  await context.setOffline(false);
  await expect(row.getByText("Waiting to send")).toBeHidden({ timeout: 20_000 });
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, "screen1-synced-with-new-referral.png") });

  await row.click();
  await expect(page).toHaveURL(/\/referrals\/[0-9a-f-]+$/);
  await expect(page.locator("text=" + patientName)).toBeVisible();
  // outbox status flips to "synced" inside flush(), a moment before the
  // same syncNow() call's subsequent pullAndApply() finishes writing
  // referral_event_cache — a slightly longer timeout than the default
  // covers that gap.
  await expect(page.getByText("Referral created")).toBeVisible({ timeout: 10_000 });
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, "screen3-referral-detail-created.png") });

  // ASHA's real action: mark as sent (CREATED -> IN_TRANSIT). Screen 3's
  // footer must show this, not the mockup's "Mark as arrived" (ARRIVED is
  // MO-only — see docs/PHASE2_OBSERVATIONS.md's P4.2 section).
  await page.getByTestId("referral-action-button").click();
  // Appears twice — once as the timeline's still-pending next step, once
  // as the footer's replacement for an action button she doesn't have.
  await expect(page.getByText("Waiting for the centre to confirm arrival.").first()).toBeVisible();

  // MO, a genuinely separate browser context — a second page on the same
  // context would share asha_a's already-valid token in localStorage, and
  // LoginPage would redirect away from /login before the form ever
  // rendered (RequireAuth's flip side: isAuthenticated() finding a token
  // that's still good).
  const moContext = await context.browser()!.newContext();
  const moPage = await moContext.newPage();
  await moPage.goto("/login");
  await moPage.getByTestId("username-input").fill("mo1");
  await moPage.getByTestId("password-input").fill("dev");
  await moPage.getByTestId("login-button").click();
  await expect(moPage).toHaveURL(/\/mo\/incoming$/);

  await expect
    .poll(async () => (await moPage.getByTestId("incoming-card").filter({ hasText: patientName }).count()) > 0, {
      timeout: 15_000,
    })
    .toBe(true);
  await moPage.screenshot({ path: path.join(SCREENSHOT_DIR, "screen5-mo-incoming-referrals.png") });

  // Tabs filter by exact state, so an advanced card moves to a different
  // tab rather than updating in place — matches Screen 5's "one tap per
  // state change, no drill-in" design (the card is gone from "On the way"
  // the instant it stops being IN_TRANSIT).
  await moPage.getByTestId("incoming-card").filter({ hasText: patientName }).getByTestId("advance-button").click();
  await moPage.getByText("At the centre").click();
  const atCentreCard = moPage.getByTestId("incoming-card").filter({ hasText: patientName });
  await expect(atCentreCard).toBeVisible({ timeout: 15_000 });

  await atCentreCard.getByTestId("advance-button").click();
  await moPage.getByText("Treated today").click();
  const treatedCard = moPage.getByTestId("incoming-card").filter({ hasText: patientName });
  await expect(treatedCard).toBeVisible({ timeout: 15_000 });
  await moContext.close();

  // A real screen since P6.2 (client/tests/identity-review.spec.ts covers
  // its actual review flow) — this is just "reachable, not a 404" for
  // asha_a, who has no pending pairs in her own village in this flow.
  await page.goto("/identity-review");
  await expect(page.getByText("Is this the same person?")).toBeVisible();
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, "screen6-identity-review-empty.png") });
});
