#!/bin/bash
# P9.2 (D44, docs/PHASE9_PLAN.md) — starts one condition's api instance for
# the advisory-lock write-latency measurement. Does NOT run k6 and does
# NOT touch app/db.py — those two steps are deliberately done by hand
# between calls to this script, so the one genuinely dangerous action in
# this phase (temporarily neutralising the lock) stays a supervised,
# one-off edit rather than something a script automates.
#
# RUN_ID has to be set before the api process starts (Settings() is
# read once, lru_cached) — so each condition gets its OWN api container,
# not a shared hot-reloaded one, even though only app/db.py's code
# actually differs between them. The scratch database itself is only
# reset+seeded on the first ("on") call; the second ("off") call reuses
# it, so request_timing accumulates rows for both conditions (tagged by
# run_id) in one place — same as P8.3's E5 comparing before/after on one
# persistent dataset rather than two.
#
# Usage:
#   bash server/scripts/measure_lock.sh e5_lock_on  reset     # first call
#   bash server/scripts/measure_lock.sh e5_lock_off noreset   # second call
# Prints TARGET_ORG_ID on its last line.

set -euo pipefail

cd "$(dirname "$0")/../.."

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

RUN_ID="${1:?usage: measure_lock.sh <run_id> <reset|noreset>}"
RESET="${2:?usage: measure_lock.sh <run_id> <reset|noreset>}"

PG_USER="${POSTGRES_USER:-postgres}"
LOCK_DB="nirantharseva_lock_scratch"
LOCK_DB_URL="postgresql+asyncpg://${PG_USER}:${POSTGRES_PASSWORD:-dev}@db:5432/${LOCK_DB}"

log() { echo ">> [$RUN_ID] $*" >&2; }

if [ "$RESET" = "reset" ]; then
  log "Resetting scratch database ($LOCK_DB) — never the dev database..."
  docker compose exec -T db psql -U "$PG_USER" -d postgres -v ON_ERROR_STOP=1 \
    -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$LOCK_DB' AND pid <> pg_backend_pid();" \
    -c "DROP DATABASE IF EXISTS $LOCK_DB;" \
    -c "CREATE DATABASE $LOCK_DB;" \
    > /dev/null
fi

log "Clearing any leftover lock-test-api from a previous condition..."
docker rm -f lock-test-api >/dev/null 2>&1 || true

log "Starting the api instance for this condition (RUN_ID=$RUN_ID) against the scratch database..."
docker compose run --rm -d --name lock-test-api \
  -e DATABASE_URL="$LOCK_DB_URL" -e RUN_ID="$RUN_ID" api > /dev/null

log "Waiting for it to answer /health..."
CODE="000"
for _ in $(seq 1 60); do
  CODE=$(docker exec lock-test-api curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/health 2>/dev/null || echo "000")
  if [ "$CODE" = "200" ]; then break; fi
  sleep 1
done
if [ "$CODE" != "200" ]; then
  echo "FAIL: lock-test-api never answered /health. Check 'docker logs lock-test-api'." >&2
  exit 1
fi

if [ "$RESET" = "reset" ]; then
  log "Seeding the fixture district..."
  docker compose run --rm -e DATABASE_URL="$LOCK_DB_URL" api python -m app.seed > /dev/null
fi

TARGET_ORG_ID=$(docker compose exec -T db psql -U "$PG_USER" -d "$LOCK_DB" -tAc \
  "SELECT id FROM org_unit WHERE name = 'PHC Ramnagar';" | tr -d '[:space:]')

log "Ready. lock-test-api is up, reachable at http://lock-test-api:8000 from other compose services."
echo "$TARGET_ORG_ID"
