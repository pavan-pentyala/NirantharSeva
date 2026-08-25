// P9.2 (D44, docs/PHASE9_PLAN.md). Measures acquire_seq_lock's
// (app/db.py, ADR-002) write-latency cost — the sentence
// docs/IMPLEMENTATION_PLAN.md §3 promised and E5 (P8.3) never produced,
// because E5's own profile (10 VUs, sleep(1), three reads per write) barely
// contends: concurrent /sync/push calls almost never overlap under it, so
// the lock would measure ~0ms whether or not it does anything. This script
// is deliberately different: no sleep(), all-write VUs running back to
// back, so pushes actually queue on the advisory lock.
//
// Two scenarios, not one, run concurrently — writers hammer /sync/push
// (the only endpoint that calls acquire_seq_lock), readers hit /dashboard
// and /referrals as a noise control (neither touches the lock at all). If
// the read numbers move as much as the write numbers between the lock-on
// and lock-off runs, the difference is sampling noise, not the lock.
//
// request_timing (queried directly, plan §12's own "a query, not a re-run"
// discipline) is the actual source of the numbers — this script's own
// --summary-export is a cross-check only, same as E5.
//
// Run against a SCRATCH database only, via a separate one-off api
// container — never the dev stack. See server/scripts/measure_lock.sh for
// the full on/off harness; this file is just the k6 workload.
//   docker compose --profile load run --rm \
//     -e BASE_URL=http://lock-test-api:8000 \
//     -e MO_USERNAME=mo1 -e ASHA_USERNAME=asha_a -e TARGET_ORG_ID=... \
//     -e WRITE_VUS=25 -e READ_VUS=5 -e DURATION=30s \
//     k6 run /scripts/lock.js --summary-export=/results/e5_lock/k6_lock_on_summary.json

import http from "k6/http";
import { check } from "k6";

const BASE_URL = __ENV.BASE_URL || "http://api:8000";
const MO_USERNAME = __ENV.MO_USERNAME;
const ASHA_USERNAME = __ENV.ASHA_USERNAME;
const TARGET_ORG_ID = __ENV.TARGET_ORG_ID;
const DEV_PASSWORD = "dev"; // app/seed.py's own constant

const WRITE_VUS = Number(__ENV.WRITE_VUS || 25);
const READ_VUS = Number(__ENV.READ_VUS || 5);
const DURATION = __ENV.DURATION || "30s";

export const options = {
  scenarios: {
    writers: {
      executor: "constant-vus",
      vus: WRITE_VUS,
      duration: DURATION,
      exec: "writeReferral",
    },
    readers: {
      executor: "constant-vus",
      vus: READ_VUS,
      duration: DURATION,
      exec: "readOnly",
    },
  },
};

function uuidv4() {
  // Load-test data only, never a security boundary — see load.js's
  // identical helper for why Math.random is fine here.
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

// Writers: back-to-back create_referral, no sleep() — this is what actually
// produces lock contention. Every push here is a new referral (a fresh
// event append), so every one of them calls acquire_seq_lock.
export function writeReferral(data) {
  const ashaHeaders = {
    headers: {
      Authorization: `Bearer ${data.ashaToken}`,
      "Content-Type": "application/json",
    },
  };
  const body = JSON.stringify({
    device_id: `k6-lock-vu-${__VU}`,
    ops: [
      {
        op_id: uuidv4(),
        entity: "referral",
        entity_id: uuidv4(),
        operation: "create_referral",
        payload: {
          patient_name: `K6 Lock Patient ${__VU}-${__ITER}`,
          age: 30,
          sex: "F",
          phone: null,
          reason: "k6 lock-contention test",
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
}

// Readers: the noise control. Neither endpoint calls acquire_seq_lock —
// their latency should be statistically identical whether the lock is on
// or off. Also no sleep(), for the same reason: a busy read path is a
// more honest control for "is anything about this API generally slower
// right now," not just "is the lock slower."
export function readOnly(data) {
  const moHeaders = { headers: { Authorization: `Bearer ${data.moToken}` } };
  check(http.get(`${BASE_URL}/dashboard`, moHeaders), {
    "dashboard 200": (r) => r.status === 200,
  });
  check(http.get(`${BASE_URL}/referrals?limit=50`, moHeaders), {
    "referrals 200": (r) => r.status === 200,
  });
}
