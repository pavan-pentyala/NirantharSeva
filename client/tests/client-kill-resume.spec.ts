import { test, expect } from "@playwright/test";
import { loginToken, pullAllOpIds } from "./helpers";

/** Ported from the toy model to a real referral create at Phase 4.3
 * (D1/D7 — the toy model was dropped, migration 0006). Same shape as
 * before: intercept /sync/push so it never responds, save while the
 * request is hanging, "kill" the tab, reopen on the same (persisted)
 * context, and confirm the retry lands exactly once. */
test("client killed mid-push resumes from inflight and lands exactly once", async ({ context, request }) => {
  const page1 = await context.newPage();
  await page1.goto("/login");
  await page1.getByTestId("username-input").fill("asha_a");
  await page1.getByTestId("password-input").fill("dev");
  await page1.getByTestId("login-button").click();
  await expect(page1).toHaveURL(/\/referrals$/);

  // Simulate the request being in flight when the tab dies: intercept
  // /sync/push and never respond. flush() has already marked the op
  // 'inflight' in IndexedDB by the time the fetch is sent, so that state
  // is durable even though the response never arrives.
  await page1.route("**/sync/push", async () => {
    await new Promise(() => {}); // never resolves
  });

  // No "Test Patient" boilerplate and a random hex suffix: sharing those
  // two words with other spec files' fixture names scores 85.5 via
  // rapidfuzz once create_referral resolves through the real fuzzy
  // pipeline (P6.2) — harmless to this test itself, but it queues a
  // spurious identity_review pair that would clutter a live demo of
  // Screen 6. See docs/OBSERVATIONS.md.
  await page1.getByTestId("new-referral-button").click();
  await page1.getByTestId("patient-name-input").fill(`Resume After Kill ${crypto.randomUUID().slice(0, 8)}`);
  await page1.getByTestId("save-referral-button").click();
  await expect(page1.getByText("Referral saved")).toBeVisible();

  const opId: string = await page1.evaluate(async () => {
    const rows = await window.__db.outbox.toArray();
    return rows[0].op_id;
  });

  await expect
    .poll(async () => {
      const row = await page1.evaluate(async (id: string) => {
        const r = await window.__db.outbox.get(id);
        return r?.status ?? null;
      }, opId);
      return row;
    })
    .toBe("inflight");

  // "kill" the tab — close it while the push is still hanging.
  await page1.close();

  // "reload" — a fresh page against the same persistent context, so it
  // sees the same IndexedDB and the same (still-valid) login session. No
  // route interception this time: the retry goes through for real.
  const page2 = await context.newPage();
  await page2.goto("/referrals");
  await expect(page2).toHaveURL(/\/referrals$/);

  await expect
    .poll(
      async () => {
        const row = await page2.evaluate(async (id: string) => {
          const r = await window.__db.outbox.get(id);
          return r?.status ?? null;
        }, opId);
        return row;
      },
      { timeout: 20000 },
    )
    .toBe("synced");

  const token = await loginToken(request);
  const counts = await pullAllOpIds(request, token);
  expect(counts.get(opId)).toBe(1); // exactly once — not lost, not duplicated

  await page2.close();
});
