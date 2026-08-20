import { test, expect } from "@playwright/test";
import { loginToken, pullAllOpIds } from "./helpers";

/** Ported from the toy model to the real referral screens at Phase 4.3
 * (D1/D7 — the toy model was dropped, migration 0006). This is plan §8.5's
 * own exit criterion, verbatim: offline, create three referrals, advance
 * one, reload the page, data still present, go online, all sync exactly
 * once. The reload step is why this needs the PWA shell precache
 * (client/src/sw.ts) to actually work — without it, a page reload while
 * offline has nothing to serve the app's own HTML/JS/CSS from.
 *
 * Runs against the built-and-previewed app (localhost:4173), not the dev
 * server (5173): vite-plugin-pwa's injectManifest strategy only injects a
 * real (non-empty) precache manifest into a production build — dev mode
 * has no equivalent, so a reload-while-offline against `vite dev` cannot
 * actually demonstrate this. Build and preview before running this file:
 *   docker compose exec client sh -c "npm run build && npm run preview" &
 */
test.use({ baseURL: "http://localhost:4173" });

test("offline: create three referrals, advance one, reload, data survives, then sync exactly once online", async ({
  page,
  context,
  request,
}) => {
  await page.goto("/login");
  await page.getByTestId("username-input").fill("asha_a");
  await page.getByTestId("password-input").fill("dev");
  await page.getByTestId("login-button").click();
  await expect(page).toHaveURL(/\/referrals$/);

  await context.setOffline(true);

  const patientNames = [0, 1, 2].map((i) => `Offline Fault Test Patient ${Date.now()}-${i}`);
  for (const name of patientNames) {
    await page.getByTestId("new-referral-button").click();
    await page.getByTestId("patient-name-input").fill(name);
    await page.getByTestId("save-referral-button").click();
    await expect(page.getByText("No signal right now")).toBeVisible();
    await page.getByText("Back to my referrals").click();
    await expect(page).toHaveURL(/\/referrals$/);
  }

  for (const name of patientNames) {
    await expect(page.getByTestId("referral-row").filter({ hasText: name })).toBeVisible();
  }

  // Advance one of the three (CREATED -> IN_TRANSIT, the ASHA's own
  // GUARDS-permitted action — see docs/PHASE2_OBSERVATIONS.md's P4.2
  // section on why Screen 3 never offers her actions she doesn't have).
  const advancedName = patientNames[0];
  await page.getByTestId("referral-row").filter({ hasText: advancedName }).click();
  await page.getByTestId("referral-action-button").click();
  await expect(page.getByText("Waiting for the centre to confirm arrival.").first()).toBeVisible();

  const opIdsBeforeReload: string[] = await page.evaluate(async () => {
    const rows = await window.__db.outbox.toArray();
    return rows.map((r) => r.op_id);
  });
  expect(opIdsBeforeReload).toHaveLength(4); // 3 creates + 1 transition
  expect(new Set(opIdsBeforeReload).size).toBe(4); // all distinct, generated client-side

  // Reload while still offline — the PWA shell precache is what makes this
  // possible at all; IndexedDB itself would survive a reload regardless.
  await page.reload();
  await expect(page).toHaveURL(/\/referrals\/[0-9a-f-]+$/);
  await expect(page.getByText(advancedName)).toBeVisible();
  await expect(page.getByText("On the way")).toBeVisible();

  await page.goto("/referrals");
  for (const name of patientNames) {
    await expect(page.getByTestId("referral-row").filter({ hasText: name })).toBeVisible();
  }

  const opIdsAfterReload: string[] = await page.evaluate(async () => {
    const rows = await window.__db.outbox.toArray();
    return rows.map((r) => r.op_id);
  });
  expect(new Set(opIdsAfterReload)).toEqual(new Set(opIdsBeforeReload)); // nothing lost, nothing duplicated by the reload

  await context.setOffline(false);

  for (const opId of opIdsBeforeReload) {
    await expect
      .poll(
        async () => {
          const status = await page.evaluate(
            async (id) => (await window.__db.outbox.get(id))?.status,
            opId,
          );
          return status;
        },
        { timeout: 20_000 },
      )
      .toBe("synced");
  }

  const token = await loginToken(request);
  const serverCounts = await pullAllOpIds(request, token);
  for (const opId of opIdsBeforeReload) {
    expect(serverCounts.get(opId)).toBe(1); // exactly once, not zero, not more
  }
});
