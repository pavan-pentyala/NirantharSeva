#!/bin/bash
# Fault test: kill the API mid-batch, retry, verify idempotent recovery.
# Plan §5.6: "docker kill the API mid-batch; retry; final state identical,
# no duplicates." This is I1 under real process death, not just a mocked
# exception.
#
# Ported onto referrals back in Phase 2.1 (D1, docs/PHASE2_PLAN.md), ahead
# of the two Playwright fault tests, because this one needs no UI — pure
# curl — so it could move onto the real domain surface without waiting for
# the real screens to exist.
#
# This is NOT part of CI — it manipulates real containers (docker kill /
# docker compose up) and is meant to be run on demand, on the host, with
# the stack already up. Run from anywhere; it cds to the repo root itself.
#
# P2.2: logs in as asha_a (server/app/seed.py's D4 fixture), so the district
# must be seeded first — `docker compose run --rm api python -m app.seed`.
#
# Usage: bash server/tests/fault/kill_api.sh

set -euo pipefail

cd "$(dirname "$0")/../../.."

BATCH_SIZE=20
PATIENT_ID=$(python3 -c "import uuid; print(uuid.uuid4())")

echo "Seeding one patient row for the batch to reference: $PATIENT_ID"
docker compose exec -T db psql -U postgres -d nirantharseva -v ON_ERROR_STOP=1 -c \
  "INSERT INTO patient (id, name, normalized_name, created_at) VALUES ('$PATIENT_ID', 'Fault Test Patient', 'fault test patient', now());" \
  > /dev/null

BATCH_JSON=$(python3 - "$PATIENT_ID" "$BATCH_SIZE" <<'PY'
import json
import sys
import uuid

patient_id, n = sys.argv[1], int(sys.argv[2])
ops = [
    {
        "op_id": str(uuid.uuid4()),
        "entity": "referral",
        "entity_id": str(uuid.uuid4()),
        "operation": "create_referral",
        "payload": {"patient_id": patient_id, "reason": "fault test", "priority": "normal"},
        "lamport": i + 1,
        "device_time": "2026-08-10T09:00:00Z",
    }
    for i in range(n)
]
print(json.dumps({"device_id": "fault-test", "ops": ops}))
PY
)

BATCH_FILE=$(mktemp)
echo "$BATCH_JSON" > "$BATCH_FILE"
trap 'rm -f "$BATCH_FILE"' EXIT

login() {
  curl -s -X POST localhost:8000/auth/login -H 'content-type: application/json' \
    -d '{"username":"asha_a","password":"dev"}' \
    | python3 -c "import json,sys; print(json.load(sys.stdin)['access_token'])"
}

echo "patient_id under test: $PATIENT_ID"
echo "Logging in..."
TOKEN=$(login)

echo "Sending a batch of $BATCH_SIZE ops, killing the API shortly after..."
curl -s -X POST localhost:8000/sync/push -H "authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' -d @"$BATCH_FILE" > /tmp/kill_api_first_response.json &
CURL_PID=$!

sleep 0.05
docker compose kill api
echo "API killed mid-batch. Waiting for the interrupted request to give up..."
wait "$CURL_PID" || true

echo "Restarting the API..."
docker compose up -d api > /dev/null

echo "Waiting for /health..."
for _ in $(seq 1 30); do
  if curl -s -o /dev/null -w '%{http_code}' localhost:8000/health 2>/dev/null | grep -q 200; then
    break
  fi
  sleep 1
done

echo "Retrying the exact same batch..."
TOKEN=$(login)
RETRY_RESPONSE=$(curl -s -X POST localhost:8000/sync/push -H "authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' -d @"$BATCH_FILE")

# Each op in the batch created its own referral (distinct entity_id, same
# patient) — so count events transitively via the patient rather than by a
# single shared entity_id.
COUNT=$(docker compose exec -T db psql -U postgres -d nirantharseva -tAc \
  "select count(*) from referral_event e join referral r on r.id = e.referral_id
   where r.patient_id = '$PATIENT_ID';" | tr -d '[:space:]')

echo "referral_event rows for patient $PATIENT_ID: $COUNT (expected $BATCH_SIZE)"

if [ "$COUNT" != "$BATCH_SIZE" ]; then
  echo "FAIL: expected exactly $BATCH_SIZE events, found $COUNT — retry was not idempotent."
  exit 1
fi

python3 -c "
import json
r = json.loads('''$RETRY_RESPONSE''')
assert len(r['results']) == $BATCH_SIZE, f\"expected $BATCH_SIZE results, got {len(r['results'])}\"
statuses = {x['status'] for x in r['results']}
assert statuses <= {'accepted', 'accepted_stale', 'conflict', 'rejected'}, f'non-terminal status found: {statuses}'
print('Retry response: all', len(r['results']), 'results have terminal status', statuses)
"

echo "PASS: $BATCH_SIZE ops landed exactly once after the API was killed mid-batch and the batch was retried."
