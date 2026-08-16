import { test, expect } from "@playwright/test";
import { loginToken, pullAllOpIds } from "./helpers";

test("client killed mid-push resumes from inflight and lands exactly once", async ({ context, request }) => {
  const page1 = await context.newPage();
  await page1.goto("/");
  await expect(page1.getByTestId("status-line")).toBeVisible();

  // Simulate the request being in flight when the tab dies: intercept
  // /sync/push and never respond. flush() has already marked the op
  // 'inflight' in IndexedDB by the time the fetch is sent, so that state
  // is durable even though the response never arrives.
  await page1.route("**/sync/push", async () => {
    await new Promise(() => {}); // never resolves
  });

  await page1.getByTestId("value-input").fill("777");
  await page1.getByTestId("save-button").click();

  await expect(page1.getByTestId("pending-count")).toHaveText("1");

  const opId: string = await page1.evaluate(async () => {
    const rows = await window.__db.outbox.toArray();
    return rows[0].op_id;
  });

  const statusWhileKilled: string = await page1.evaluate(async (id: string) => {
    const row = await window.__db.outbox.get(id);
    return row!.status;
  }, opId);
  expect(statusWhileKilled).toBe("inflight");

  // "kill" the tab — close it while the push is still hanging.
  await page1.close();

  // "reload" — a fresh page against the same persistent context, so it
  // sees the same IndexedDB. No route interception this time: the retry
  // goes through for real.
  const page2 = await context.newPage();
  await page2.goto("/");
  await expect(page2.getByTestId("status-line")).toBeVisible();

  // The retry can complete in single-digit milliseconds — faster than the
  // harness's 500ms display-poll interval — so the UI's pending-count text
  // can skip straight from its initial "0" to a real "0" without ever
  // rendering the intermediate "1". Poll the actual IndexedDB row instead
  // of the UI text; that is the state that matters for correctness.
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
