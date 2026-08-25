#!/bin/bash
# The demo runner. docs/PHASE9_PLAN.md P9.1 (D46-D49), docs/IMPLEMENTATION_PLAN.md
# §14. Resets the application database, seeds a small cohort *of states* (not
# volume — D48), starts a demo-scale scheduler, and prints the walkthrough.
# docs/DEMO_SCRIPT.md is the companion document to read while rehearsing;
# this script's own output is the reminder while presenting.
#
# D46: the real logic lives here, not in the Makefile — `make` is not
#      installed on the reference machine. `make demo` just calls this file.
# D47: "reset" means DROP/CREATE the application database, not
#      `docker compose down -v` — that would stop the client and any running
#      preview mid-preparation. The stack stays up.
# D48: seeds for states, not volume: one referral the MO can advance on
#      Screen 5, one already overdue so Screen 4 is not empty on arrival, one
#      pending identity-review pair for Screen 6. The headline "breaches
#      live while you watch" referral is deliberately NOT pre-seeded here —
#      docs/DEMO_SCRIPT.md has the presenter create it live on Screen 2,
#      which is a stronger demo than a referral that mysteriously already
#      existed. This script's only job for that moment is to make sure the
#      demo-scale scheduler is already running before they do it.
# D49: prints the dashboard URL — a container cannot open a host browser.
#
# Every referral below is created through the real /sync/push, not
# hand-INSERTed — ADR-015's discipline, following server/scripts/demo_walk.py's
# own precedent (a different script, kept as-is; that one proves a full
# conflict walk for verify_replay, this one seeds a demo).
#
# Usage: bash server/scripts/demo.sh   (also invoked by `make demo`)

set -euo pipefail

cd "$(dirname "$0")/../.."

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

DB_NAME="${POSTGRES_DB:-nirantharseva}"
PG_USER="${POSTGRES_USER:-postgres}"
API_URL="http://localhost:8000"
CLIENT_URL="http://localhost:5173"

log() { echo ">> $*"; }

wait_for_health() {
  for _ in $(seq 1 60); do
    if curl -s -o /dev/null -w '%{http_code}' "$API_URL/health" 2>/dev/null | grep -q 200; then
      return 0
    fi
    sleep 1
  done
  echo "FAIL: api never answered $API_URL/health. Check 'docker compose logs api'." >&2
  exit 1
}

login() {
  curl -s -X POST "$API_URL/auth/login" -H 'content-type: application/json' \
    -d "{\"username\":\"$1\",\"password\":\"dev\"}" \
    | python3 -c "import json,sys; print(json.load(sys.stdin)['access_token'])"
}

now_iso() { python3 -c "from datetime import datetime, timezone; print(datetime.now(timezone.utc).isoformat())"; }

# push_op <token> <device_id> <entity_id> <operation> <payload_json> <lamport>
push_op() {
  local token="$1" device="$2" entity_id="$3" operation="$4" payload="$5" lamport="$6"
  local op_id
  op_id=$(python3 -c "import uuid; print(uuid.uuid4())")
  local resp
  resp=$(curl -s -X POST "$API_URL/sync/push" -H "authorization: Bearer $token" \
    -H 'content-type: application/json' \
    -d "{\"device_id\":\"$device\",\"ops\":[{\"op_id\":\"$op_id\",\"entity\":\"referral\",\"entity_id\":\"$entity_id\",\"operation\":\"$operation\",\"payload\":$payload,\"lamport\":$lamport,\"device_time\":\"$(now_iso)\"}]}")
  python3 -c "
import json, sys
r = json.loads('''$resp''')
status = r['results'][0]['status']
assert status in ('accepted', 'accepted_stale'), f'push failed for entity $entity_id: {r}'
"
}

log "Bringing the stack up (safe to run against an already-up stack)..."
docker compose up -d --build

log "Waiting for the database..."
for _ in $(seq 1 30); do
  if docker compose exec -T db pg_isready -U "$PG_USER" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

log "Waiting for the API..."
wait_for_health

log "Resetting the database ($DB_NAME) — D47: drop/recreate, not 'down -v'..."
docker compose exec -T db psql -U "$PG_USER" -d postgres -v ON_ERROR_STOP=1 \
  -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$DB_NAME' AND pid <> pg_backend_pid();" \
  -c "DROP DATABASE IF EXISTS $DB_NAME;" \
  -c "CREATE DATABASE $DB_NAME;" \
  > /dev/null

log "Restarting the API so its dashboard-stream LISTEN connection is fresh, not stale against the recreated database..."
docker compose restart api > /dev/null
wait_for_health

log "Migrating and seeding the fixture district..."
docker compose run --rm api sh -c "alembic upgrade head && python -m app.seed"

log "Clearing any leftover demo-scale scheduler from a previous run..."
docker rm -f demo-scheduler >/dev/null 2>&1 || true

log "Starting the demo-scale scheduler (SLA_SCALE=0.0004, SWEEP_INTERVAL_SECONDS=5)..."
docker compose run --rm -d --name demo-scheduler \
  -e SLA_SCALE=0.0004 -e SWEEP_INTERVAL_SECONDS=5 scheduler > /dev/null

log "Seeding: a referral ready for the MO to advance on Screen 5 (Ramesh Kumar, on the way)..."
ASHA_A_TOKEN=$(login asha_a)
RAMESH_ID=$(python3 -c "import uuid; print(uuid.uuid4())")
push_op "$ASHA_A_TOKEN" demo-asha-a "$RAMESH_ID" create_referral \
  '{"patient_name":"Ramesh Kumar","reason":"chest pain, referred for evaluation","priority":"urgent"}' 1
push_op "$ASHA_A_TOKEN" demo-asha-a "$RAMESH_ID" transition \
  '{"from_state":"CREATED","to_state":"IN_TRANSIT"}' 2

log "Seeding: a referral already overdue, so Screen 4 is not empty on arrival (Suresh Yadav)..."
ASHA_B_TOKEN=$(login asha_b)
SURESH_ID=$(python3 -c "import uuid; print(uuid.uuid4())")
push_op "$ASHA_B_TOKEN" demo-asha-b "$SURESH_ID" create_referral \
  '{"patient_name":"Suresh Yadav","reason":"suspected fracture, referred for evaluation","priority":"urgent"}' 1

log "Waiting for the demo-scale scheduler to escalate it (up to ~2 minutes)..."
ESCALATED=""
for _ in $(seq 1 24); do
  STATE=$(docker compose exec -T db psql -U "$PG_USER" -d "$DB_NAME" -tAc \
    "SELECT current_state FROM referral WHERE id = '$SURESH_ID';" | tr -d '[:space:]')
  if [ "$STATE" = "ESCALATED" ]; then
    ESCALATED="yes"
    break
  fi
  sleep 5
done
if [ -z "$ESCALATED" ]; then
  echo "FAIL: Suresh Yadav's referral never escalated within 2 minutes." >&2
  echo "Check 'docker logs demo-scheduler' and that app/domain/escalation.py's" >&2
  echo "CAST(:sla_scale AS double precision) is still in place (observation 37)." >&2
  exit 1
fi
log "Confirmed escalated."

log "Seeding: a pending identity-review pair for Screen 6 (Lakshmy Devi vs. the seeded Lakshmi Devi)..."
LAKSHMY_ID=$(python3 -c "import uuid; print(uuid.uuid4())")
push_op "$ASHA_A_TOKEN" demo-asha-a "$LAKSHMY_ID" create_referral \
  '{"patient_name":"Lakshmy Devi","reason":"follow-up","priority":"routine"}' 3

echo ""
echo "=================================================================="
echo " Demo-ready."
echo "=================================================================="
echo ""
echo "  Client:      $CLIENT_URL"
echo "  Dashboard:   $CLIENT_URL/supervisor   (log in as supervisor1)"
echo "  API health:  $API_URL/health"
echo ""
echo "  User          Password  Role         Lands on"
echo "  asha_a        dev       ASHA         /referrals"
echo "  mo1           dev       MO           /mo/incoming"
echo "  supervisor1   dev       SUPERVISOR   /supervisor"
echo "  anm1          dev       ANM          /identity-review"
echo ""
echo "  Demo-scale scheduler: running as container 'demo-scheduler'"
echo "  (SLA_SCALE=0.0004, SWEEP_INTERVAL_SECONDS=5 — a 24h SLA breaches in"
echo "  ~35s, a 48h one in ~70s). Referrals will keep accumulating in the"
echo "  overdue list the longer the stack stays up — that is this setting"
echo "  working as intended, not a bug. Stop it when you are done:"
echo "    docker stop demo-scheduler"
echo ""
echo "  Seeded: Suresh Yadav's referral is already overdue on supervisor1's"
echo "  dashboard now. Ramesh Kumar's is on the way, for mo1 to advance."
echo "  A Lakshmy Devi / Lakshmi Devi pair is waiting in anm1's"
echo "  identity-review queue."
echo ""
echo "  NOTE: at this scale, EVERY open referral breaches within about a"
echo "  minute, including the two fixture ones from 'python -m app.seed'"
echo "  (Lakshmi Devi, Fatima Begum) and Ramesh Kumar himself. The longer"
echo "  you wait before opening the dashboard, the more overdue rows you'll"
echo "  see, not just Suresh Yadav's — that's the setting working as"
echo "  intended (verified in rehearsal), not something to be surprised by."
echo "  mo1 can still advance an already-overdue Ramesh Kumar; doing so"
echo "  resolves his escalation, same as advancing him earlier would."
echo ""
echo "  Full click path, timing, and what to say: docs/DEMO_SCRIPT.md"
echo ""
echo "  Scenario, in order:"
echo "   1. asha_a      -> /referrals       her own village's referrals"
echo "   2. asha_a      -> /referrals/new    create ONE more referral now —"
echo "                                       this is the one you'll watch"
echo "                                       breach live in step 6"
echo "   3. asha_a      -> /referrals/:id    open it, show the timeline"
echo "   4. mo1         -> /mo/incoming      advance Ramesh Kumar"
echo "   5. anm1        -> /identity-review  decide the Lakshmy/Lakshmi pair"
echo "   6. supervisor1 -> /supervisor       watch step 2's referral flip to"
echo "                                       overdue, live, no reload"
echo ""
