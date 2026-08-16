#!/bin/bash
# Fault test: kill the API mid-batch, retry, verify idempotent recovery.
# Plan §5.6: "docker kill the API mid-batch; retry; final state identical,
# no duplicates." This is I1 under real process death, not just a mocked
# exception.
#
# This is NOT part of CI — it manipulates real containers (docker kill /
# docker compose up) and is meant to be run on demand, on the host, with
# the stack already up. Run from anywhere; it cds to the repo root itself.
#
# Usage: bash server/tests/fault/kill_api.sh

set -euo pipefail

cd "$(dirname "$0")/../../.."

BATCH_SIZE=20
TOY_ID=$(python3 -c "import uuid; print(uuid.uuid4())")

BATCH_JSON=$(python3 - "$TOY_ID" "$BATCH_SIZE" <<'PY'
import json
import sys
import uuid

toy_id, n = sys.argv[1], int(sys.argv[2])
ops = [
    {
        "op_id": str(uuid.uuid4()),
        "entity": "toy",
        "entity_id": toy_id,
        "operation": "set_value",
        "payload": {"value": i},
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
    -d '{"username":"asha1","password":"dev"}' \
    | python3 -c "import json,sys; print(json.load(sys.stdin)['access_token'])"
}

echo "toy_id under test: $TOY_ID"
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

COUNT=$(docker compose exec -T db psql -U postgres -d nirantharseva -tAc \
  "select count(*) from toy_event where toy_id = '$TOY_ID';" | tr -d '[:space:]')

echo "toy_event rows for $TOY_ID: $COUNT (expected $BATCH_SIZE)"

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
