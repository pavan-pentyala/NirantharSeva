import { test, expect } from "@playwright/test";

// P4.1 item 7: createReferral writes its outbox entry and its optimistic
// referral_cache row inside one Dexie transaction (plan §8.3). This forces
// the outbox write to fail — a pre-seeded row occupying the exact op_id
// createReferral's own crypto.randomUUID() call is made to return, so
// Dexie's add() throws a ConstraintError on the duplicate primary key —
// and checks that the referral_cache write inside the same transaction
// never landed either. Without db.transaction(), the cache write (which
// happens after the outbox write in program order) could still succeed on
// its own even though the outbox write failed.
test("createReferral's outbox+cache write is atomic — an induced mid-transaction failure leaves neither table changed", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.getByTestId("status-line")).toBeVisible();

  const result = await page.evaluate(async () => {
    const conflictingOpId = crypto.randomUUID();
    await window.__db.outbox.add({
      op_id: conflictingOpId,
      entity: "toy",
      entity_id: "seed",
      operation: "set_value",
      payload: { value: 0 },
      lamport: 0,
      device_time: new Date().toISOString(),
      status: "synced",
    });

    // getDeviceId() also calls crypto.randomUUID() the first time it runs
    // on a fresh IndexedDB — pre-seed the row so createReferral's own
    // opId is deterministically the *first* call the override below sees.
    if (!(await window.__db.sync_meta.get("device_id"))) {
      await window.__db.sync_meta.put({ key: "device_id", value: crypto.randomUUID() });
    }

    const originalRandomUUID = crypto.randomUUID.bind(crypto);
    let calls = 0;
    // createReferral's first crypto.randomUUID() call generates op_id —
    // hand back the id already occupying the outbox's primary key.
    crypto.randomUUID = (() => {
      calls += 1;
      return calls === 1 ? conflictingOpId : originalRandomUUID();
    }) as typeof crypto.randomUUID;

    let threw = false;
    try {
      await window.__engine.createReferral({ patientName: "Atomicity Test Patient" });
    } catch {
      threw = true;
    } finally {
      crypto.randomUUID = originalRandomUUID;
    }

    return {
      threw,
      outboxCount: await window.__db.outbox.count(),
      referralCacheCount: await window.__db.referral_cache.count(),
    };
  });

  expect(result.threw).toBe(true);
  // Only the pre-seeded row — createReferral's own outbox.add() never landed.
  expect(result.outboxCount).toBe(1);
  // Rolled back with it, same transaction — never left orphaned in the cache.
  expect(result.referralCacheCount).toBe(0);
});
