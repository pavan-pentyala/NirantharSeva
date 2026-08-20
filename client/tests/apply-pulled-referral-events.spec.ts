import { test, expect } from "@playwright/test";

// P4.1 item 7: applyPulledEvents' referral branch must use the same
// left-to-right advancement rule app/domain/states.py's replay_steps
// encodes server-side (D14) — an event advances referral_cache only when
// its from_state matches the state already folded in, not whichever event
// has the highest lamport. This fixture is modeled on the demo walk's own
// conflict (scripts/demo_walk.py steps 1/2/4, docs/PHASE3_PLAN.md D12):
// step 2 legitimately advances CREATED -> IN_TRANSIT at lamport 11; step 4
// is a genuine conflict with a *higher* lamport (20) but the same
// from_state (CREATED) the cache has already moved past. A lamport-only
// fold would wrongly let step 4 win; the from_state rule must not.
const REFERRAL_ID = "22222222-2222-2222-2222-222222222222";

const PATIENT_SNAPSHOT = {
  patient_name: "Lakshmi Devi",
  age: 45,
  sex: "F",
  reason: "fever, referred for evaluation",
  priority: "normal",
  target_org_name: "PHC Ramnagar",
};

const EVENTS = [
  {
    seq: 101,
    entity_type: "referral",
    entity_id: REFERRAL_ID,
    op_id: "11111111-0000-0000-0000-000000000001",
    device_id: "demo-phone-a",
    lamport: 10,
    device_time: "2026-08-19T09:00:00Z",
    server_time: "2026-08-19T09:00:01Z",
    payload: { from_state: null, to_state: "CREATED", actor_role: "ASHA", actor_user_id: "u1", ...PATIENT_SNAPSHOT },
  },
  {
    seq: 102,
    entity_type: "referral",
    entity_id: REFERRAL_ID,
    op_id: "11111111-0000-0000-0000-000000000002",
    device_id: "demo-phone-a",
    lamport: 11,
    device_time: "2026-08-19T09:01:00Z",
    server_time: "2026-08-19T09:01:01Z",
    payload: {
      from_state: "CREATED",
      to_state: "IN_TRANSIT",
      actor_role: "ASHA",
      actor_user_id: "u1",
      ...PATIENT_SNAPSHOT,
    },
  },
  {
    // The conflict pair's losing side: same from_state as the event above,
    // but arrives after the cache has already advanced past it, and its
    // lamport (20) is higher than the winner's (11).
    seq: 103,
    entity_type: "referral",
    entity_id: REFERRAL_ID,
    op_id: "11111111-0000-0000-0000-000000000004",
    device_id: "demo-phone-b",
    lamport: 20,
    device_time: "2026-08-19T09:02:00Z",
    server_time: "2026-08-19T09:02:01Z",
    payload: {
      from_state: "CREATED",
      to_state: "IN_TRANSIT",
      actor_role: "ANM",
      actor_user_id: "u2",
      ...PATIENT_SNAPSHOT,
    },
  },
];

test("applyPulledEvents only advances referral_cache when from_state matches the fold so far, not the higher-lamport event", async ({
  page,
}) => {
  // Any mounted page exposes window.__db/__engine (set up in main.tsx at
  // module load); /login is the one reachable without a session, since
  // the Phase 1 toy harness that used to sit at "/" is gone (Phase 4.3,
  // migration 0006).
  await page.goto("/login");
  await expect(page.getByTestId("username-input")).toBeVisible();

  const row = await page.evaluate(async (events) => {
    await window.__engine.applyPulledEvents(events as never);
    return window.__db.referral_cache.get("22222222-2222-2222-2222-222222222222");
  }, EVENTS);

  expect(row).toBeTruthy();
  // Step 2 won — not step 4, despite its higher lamport.
  expect(row!.current_state).toBe("IN_TRANSIT");
  expect(row!.lamport).toBe(11);
  expect(row!.device_id).toBe("demo-phone-a");
  expect(row!.patient_name).toBe("Lakshmi Devi");

  const cacheCount = await page.evaluate(() => window.__db.referral_cache.count());
  expect(cacheCount).toBe(1); // one referral, one row — the conflict wrote nothing extra
});
