// E5 load script. docs/PHASE8_PLAN.md, docs/IMPLEMENTATION_PLAN.md §13.2.
//
// Genuinely new tooling in this repo (docker-compose.yml's "load" profile,
// PROGRESS.md's own P8.3 traps note). Hits the mix agreed with the user:
// GET /dashboard, GET /referrals, GET /sync/pull (read path — the "open
// loops" query E5's index question is about lives inside /dashboard's
// stats query, app/api/dashboard.py's _STATS_QUERY), and POST /sync/push
// (write path — the sync hot path this whole system exists for).
//
// request_timing (app/instrumentation/timing.py) is the actual source of
// the p50/p95 numbers Chapter 4 uses — plan §12's own design ("E5 is then
// a query, not a re-run"). This script's own --summary-export is a
// secondary, cross-check artifact, not the analysis source.
//
// Run twice per the before/after index comparison (see PROGRESS.md's "To
// verify P8.3 yourself"), with a different RUN_ID set on the api
// container each time so request_timing rows can be told apart:
//   docker compose --profile load run --rm \
//     -e MO_USERNAME=... -e ASHA_USERNAME=... -e TARGET_ORG_ID=... \
//     k6 run /scripts/load.js --summary-export=/results/k6_before_summary.json

import http from "k6/http";
import { check, sleep } from "k6";

const BASE_URL = __ENV.BASE_URL || "http://api:8000";
const MO_USERNAME = __ENV.MO_USERNAME;
const ASHA_USERNAME = __ENV.ASHA_USERNAME;
const TARGET_ORG_ID = __ENV.TARGET_ORG_ID;
const DEV_PASSWORD = "dev"; // app/seed.py's own constant

export const options = {
  vus: Number(__ENV.VUS || 10),
  duration: __ENV.DURATION || "40s",
};

function uuidv4() {
  // Load-test data only, never anything this repo treats as a security
  // boundary — Math.random is fine here, k6 has no built-in UUID helper.
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

function login(username) {
  const res = http.post(
    `${BASE_URL}/auth/login`,
    JSON.stringify({ username, password: DEV_PASSWORD }),
    { headers: { "Content-Type": "application/json" } }
  );
  check(res, { "login 200": (r) => r.status === 200 });
  return res.json("access_token");
}

export function setup() {
  return {
    moToken: login(MO_USERNAME),
    ashaToken: login(ASHA_USERNAME),
  };
}

export default function (data) {
  const moHeaders = { headers: { Authorization: `Bearer ${data.moToken}` } };
  const ashaHeaders = {
    headers: {
      Authorization: `Bearer ${data.ashaToken}`,
      "Content-Type": "application/json",
    },
  };

  // Read path — supervisor-breadth login (an MO at a facility sees every
  // referral routed to it), so these three queries touch a realistic
  // fraction of the loaded cohort, not just a handful of rows.
  check(http.get(`${BASE_URL}/dashboard`, moHeaders), {
    "dashboard 200": (r) => r.status === 200,
  });
  check(http.get(`${BASE_URL}/referrals?limit=50`, moHeaders), {
    "referrals 200": (r) => r.status === 200,
  });
  check(http.get(`${BASE_URL}/sync/pull?since=0&limit=200`, moHeaders), {
    "pull 200": (r) => r.status === 200,
  });

  // Write path — one new referral per iteration, same shape
  // scripts/load_cohort.py's own _create_op builds.
  const referralId = uuidv4();
  const body = JSON.stringify({
    device_id: `k6-vu-${__VU}`,
    ops: [
      {
        op_id: uuidv4(),
        entity: "referral",
        entity_id: referralId,
        operation: "create_referral",
        payload: {
          patient_name: `K6 Load Patient ${__VU}-${__ITER}`,
          age: 30,
          sex: "F",
          phone: null,
          reason: "k6 load test",
          priority: "routine",
          target_org_id: TARGET_ORG_ID,
        },
        lamport: 1,
        device_time: new Date().toISOString(),
      },
    ],
  });
  check(http.post(`${BASE_URL}/sync/push`, body, ashaHeaders), {
    "push 200": (r) => r.status === 200,
  });

  sleep(1);
}
