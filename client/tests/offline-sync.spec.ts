import { test, expect } from "@playwright/test";
import { loginToken, pullAllOpIds } from "./helpers";

test("50 ops created offline all land exactly once after reconnect", async ({ page, context, request }) => {
  await page.goto("/");
  await expect(page.getByTestId("status-line")).toBeVisible();

  await context.setOffline(true);
  await expect(page.getByTestId("online-state")).toHaveText("offline");

  for (let i = 0; i < 50; i++) {
    await page.getByTestId("value-input").fill(String(i));
    await page.getByTestId("save-button").click();
  }

  await expect(page.getByTestId("pending-count")).toHaveText("50");

  const createdOpIds: string[] = await page.evaluate(async () => {
    const rows = await window.__db.outbox.toArray();
    return rows.map((r) => r.op_id);
  });
  expect(createdOpIds).toHaveLength(50);
  expect(new Set(createdOpIds).size).toBe(50); // all distinct, generated client-side

  await context.setOffline(false);
  await expect(page.getByTestId("online-state")).toHaveText("online");

  await expect(page.getByTestId("pending-count")).toHaveText("0", { timeout: 20000 });

  const outboxAfter: { op_id: string; status: string }[] = await page.evaluate(async () => {
    const rows = await window.__db.outbox.toArray();
    return rows.map((r) => ({ op_id: r.op_id, status: r.status }));
  });
  const byId = new Map(outboxAfter.map((r) => [r.op_id, r.status]));
  for (const opId of createdOpIds) {
    expect(byId.get(opId)).toBe("synced");
  }

  const token = await loginToken(request);
  const serverCounts = await pullAllOpIds(request, token);
  for (const opId of createdOpIds) {
    expect(serverCounts.get(opId)).toBe(1); // exactly once, not zero, not more
  }
});
