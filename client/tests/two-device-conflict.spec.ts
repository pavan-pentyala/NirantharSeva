import { test, expect } from "@playwright/test";
import { loginToken, pullAllOpIds } from "./helpers";

/** docs/PHASE7_PLAN.md P7.2, §13.3's fifth E4 row: two real devices, both
 * offline, both transition the same referral. Device 1 and device 2 are
 * the same actor (asha_a) on two separate browser contexts — her phone and
 * a shared tablet, say — each with its own IndexedDB and its own
 * device_id (client/src/db/meta.ts).
 *
 * Device 2 never creates anything itself; it only ever PULLS the referral
 * device 1 created. Two things have to be made deterministic for the
 * result to be a real ADR-003 row 5 conflict, both found by actually
 * running this spec alongside the rest of the suite rather than in
 * isolation:
 *
 * 1. **Ordering.** "Bring device 1 online, wait, then bring device 2
 *    online" only orders the JS-level `await`s, not the two devices'
 *    actual HTTP requests — under load, device 2's request reached the
 *    server before device 1's confirmed commit was visible. A route gate
 *    makes the server-side arrival order deterministic instead: device 2
 *    goes online for real (matching what a real device would do), but its
 *    `/sync/push` request is held at the network layer until device 1's
 *    has already committed.
 * 2. **The lamport itself.** `server/app/sync/push.py`'s `server_lamport`
 *    (merged into every device's local counter on every push and pull) is
 *    a GLOBAL max across the whole `referral_event` table, not scoped to
 *    this referral, this org, or even this test run — so on a persistent
 *    dev database, both devices' local lamport counters drift upward
 *    across every OTHER concurrently-running spec's ops AND every earlier
 *    run of this very spec, through two different channels (device 1's
 *    own push responses; device 2's pulled-event maxes) that do not
 *    inflate by the same amount. The "naturally tied lamport" this spec's
 *    first draft relied on only held in isolation, and even a large
 *    hardcoded constant for device 2 eventually stopped being "ahead" once
 *    enough repeated runs had pushed device 1's OWN baseline past it too
 *    (found by watching this exact spec's repeated runs do that). Reading
 *    device 1's actual current lamport and adding a large margin to it —
 *    the same deterministic idea `server/scripts/demo_walk.py` already
 *    uses server-side to land on a specific ADR-003 row, just anchored to
 *    a live value instead of a constant — keeps `incoming_lamport >=
 *    current_lamport` true regardless of how high the shared ceiling has
 *    already climbed, so device 2 lands on row 5 (conflict) rather than
 *    row 4 (a merely late write) even when the two local counters are
 *    nowhere near their own private "1" and "2".
 *
 * What server/scripts/load_cohort.py's P7.1 loader could not exercise
 * (flagged at the time): this needs two real IndexedDB outboxes going
 * offline independently, which only a real browser can do.
 */
test("two devices offline, same referral, same transition -> one accepted, one conflict, nothing lost", async ({
  browser,
  request,
}) => {
  test.setTimeout(120_000);
  const context1 = await browser.newContext();
  const context2 = await browser.newContext();
  const page1 = await context1.newPage();
  const page2 = await context2.newPage();

  try {
    // Device 1: log in, create the referral online.
    await page1.goto("/login");
    await page1.getByTestId("username-input").fill("asha_a");
    await page1.getByTestId("password-input").fill("dev");
    await page1.getByTestId("login-button").click();
    await expect(page1).toHaveURL(/\/referrals$/);

    const patientName = `Two Device Conflict Fixture ${crypto.randomUUID().slice(0, 8)}`;
    await page1.getByTestId("new-referral-button").click();
    await page1.getByTestId("patient-name-input").fill(patientName);
    await page1.getByTestId("save-referral-button").click();
    await expect(page1.getByText("Referral saved")).toBeVisible();
    await page1.getByText("Back to my referrals").click();
    await expect(page1).toHaveURL(/\/referrals$/);

    const createOpId: string = await page1.evaluate(
      async () => (await window.__db.outbox.toArray())[0].op_id,
    );
    const entityId: string = await page1.evaluate(
      async () => (await window.__db.outbox.toArray())[0].entity_id,
    );

    // Confirmed on the server before device 2 tries to pull it — the
    // "Referral saved" text only means the outbox write landed locally.
    // Generous timeouts throughout this spec (here and below): every poll
    // waits on a real network round trip against the shared dev API, which
    // can be slow under a full-suite run sharing it across parallel workers.
    await expect
      .poll(
        async () =>
          page1.evaluate(
            async (id: string) => (await window.__db.outbox.get(id))?.status,
            createOpId,
          ),
        { timeout: 20_000 },
      )
      .toBe("synced");

    // Device 2: log in as the SAME actor, a separate browser context —
    // her other device. Pulls the referral into its own cache.
    await page2.goto("/login");
    await page2.getByTestId("username-input").fill("asha_a");
    await page2.getByTestId("password-input").fill("dev");
    await page2.getByTestId("login-button").click();
    await expect(page2).toHaveURL(/\/referrals$/);
    // A longer-than-default timeout: this waits on a real network pull
    // completing, and under a full-suite run (7 parallel workers sharing
    // one dev API/Postgres) that can take longer than Playwright's 5s
    // default — the exact same class of slowdown dashboard.spec.ts already
    // budgets extra time for on its own network-bound assertions.
    await expect(page2.getByTestId("referral-row").filter({ hasText: patientName })).toBeVisible({
      timeout: 20_000,
    });

    // Force device 2's local lamport counter comfortably ahead of device
    // 1's (see module docstring, point 2) — relative to device 1's OWN
    // observed lamport, not a hardcoded constant: server_lamport is a
    // GLOBAL max merged into every device's local counter on every push,
    // so on a persistent dev database that both devices — and every
    // earlier run of this same spec — have been writing to, an absolute
    // constant eventually gets overtaken by device 1's own accumulated
    // baseline too (found by watching this spec's own repeated runs push
    // that ceiling higher each time). A margin measured from device 1's
    // actual current value is safe regardless of how high the shared
    // ceiling has already climbed.
    const device1Lamport: number = await page1.evaluate(
      async () => ((await window.__db.sync_meta.get("lamport"))?.value as number) ?? 0,
    );
    await page2.evaluate(async (base: number) => {
      await window.__db.sync_meta.put({ key: "lamport", value: base + 1_000_000 });
    }, device1Lamport);

    // Both devices navigate to the referral WHILE STILL ONLINE — dev mode
    // (localhost:5173) has no PWA precache (unlike offline-sync.spec.ts,
    // which runs against the built app on :4173 for exactly that reason),
    // so a page.goto() while offline would be a real network request for
    // the document itself, not a client-side route change, and would fail.
    await page1.goto(`/referrals/${entityId}`);
    await page2.getByTestId("referral-row").filter({ hasText: patientName }).click();
    await expect(page2).toHaveURL(new RegExp(`/referrals/${entityId}$`));

    // Now both devices go offline independently, and both queue the
    // identical transition (CREATED -> IN_TRANSIT) via client-side state
    // only — no navigation, so no network request is needed for the click.
    await context1.setOffline(true);
    await context2.setOffline(true);

    await page1.getByTestId("referral-action-button").click();
    await page2.getByTestId("referral-action-button").click();

    // The click handler awaits an async Dexie transaction before the
    // outbox row exists (client/src/sync/engine.ts's transitionReferral) —
    // Playwright's click() only waits for the DOM event, not for that, so
    // read the op_id only once the row has actually landed.
    const hasTransitionOp = (page: typeof page1) =>
      page.evaluate(async () => (await window.__db.outbox.toArray()).some((r) => r.operation === "transition"));
    await expect.poll(() => hasTransitionOp(page1), { timeout: 20_000 }).toBe(true);
    await expect.poll(() => hasTransitionOp(page2), { timeout: 20_000 }).toBe(true);

    const transitionOpId1: string = await page1.evaluate(async () => {
      const rows = await window.__db.outbox.toArray();
      return rows.find((r) => r.operation === "transition")!.op_id;
    });
    const transitionOpId2: string = await page2.evaluate(async () => {
      const rows = await window.__db.outbox.toArray();
      return rows.find((r) => r.operation === "transition")!.op_id;
    });
    // Client-generated (crypto.randomUUID()), always distinct regardless
    // of the forced lamport above.
    expect(transitionOpId1).not.toBe(transitionOpId2);

    // Device 2's browser goes online for real, but its /sync/push request
    // is held at the network layer (module docstring, point 1) until
    // device 1's write has committed.
    let releaseDevice2Push = () => {};
    const device2PushHeld = new Promise<void>((resolve) => {
      releaseDevice2Push = resolve;
    });
    await page2.route("**/sync/push", async (route) => {
      await device2PushHeld;
      await route.continue();
    });

    await context2.setOffline(false); // triggers flush(), held at the route above
    await context1.setOffline(false);
    await expect
      .poll(
        async () =>
          page1.evaluate(
            async (id: string) => (await window.__db.outbox.get(id))?.status,
            transitionOpId1,
          ),
        { timeout: 20_000 },
      )
      .toBe("synced");

    // Device 1's write is now committed server-side — only now let device
    // 2's already-queued request through. It loses: the referral has
    // already moved to IN_TRANSIT, and its forced-high lamport still
    // satisfies incoming_lamport >= current_lamport (ADR-003 row 5, not
    // row 4 — a merely late write).
    releaseDevice2Push();
    await expect
      .poll(
        async () =>
          page2.evaluate(
            async (id: string) => (await window.__db.outbox.get(id))?.status,
            transitionOpId2,
          ),
        { timeout: 20_000 },
      )
      .toBe("conflict");

    // I6: the losing write is never deleted. All three ops — the create
    // and both transitions — are visible through a real pull, each
    // exactly once. (This is also this spec's proof of the "one
    // sync_conflict row" half of the exit criterion: the server code path
    // that decides "conflict" is the same one-INSERT branch
    // tests/integration/test_demo_walk.py already pins server-side at
    // exactly one row per conflict decision — this spec proves a real
    // two-device scenario reaches that decision, not a hand-built one.)
    const token = await loginToken(request);
    const counts = await pullAllOpIds(request, token);
    expect(counts.get(createOpId)).toBe(1);
    expect(counts.get(transitionOpId1)).toBe(1);
    expect(counts.get(transitionOpId2)).toBe(1);

    // Both devices converge on the real (winning) state, even the one
    // whose own attempt lost — applyResults() re-pulls on anything not
    // "accepted" and overwrites the optimistic local guess with it.
    await expect(page1.getByText("On the way").first()).toBeVisible({ timeout: 20_000 });
    await expect(page2.getByText("On the way").first()).toBeVisible({ timeout: 20_000 });
  } finally {
    await context1.close();
    await context2.close();
  }
});
