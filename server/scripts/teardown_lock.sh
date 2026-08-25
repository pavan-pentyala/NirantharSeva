#!/bin/bash
# P9.2 companion to measure_lock.sh. Writes server/results/e5_lock/
# table_e5_lock_latency.csv from request_timing (both run_ids, one query,
# same "request_timing is the source of truth" discipline as E5 — plan
# §12), stops lock-test-api, and drops the scratch database. Run this
# AFTER both k6-lock runs (on and off) and after app/db.py's edit has
# already been reverted and verified clean — this script does not check
# that for you.
#
# Usage: bash server/scripts/teardown_lock.sh

set -euo pipefail

cd "$(dirname "$0")/../.."

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

PG_USER="${POSTGRES_USER:-postgres}"
LOCK_DB="nirantharseva_lock_scratch"
OUT_DIR="server/results/e5_lock"
mkdir -p "$OUT_DIR"

echo ">> Writing table_e5_lock_latency.csv from request_timing..."
docker compose exec -T db psql -U "$PG_USER" -d "$LOCK_DB" -v ON_ERROR_STOP=1 -c "
COPY (
  SELECT
    run_id,
    endpoint,
    method,
    count(*) AS n,
    round(percentile_cont(0.5) WITHIN GROUP (ORDER BY duration_ms)::numeric, 2) AS p50_ms,
    round(percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms)::numeric, 2) AS p95_ms
  FROM request_timing
  WHERE run_id IN ('e5_lock_on', 'e5_lock_off')
  GROUP BY run_id, endpoint, method
  ORDER BY endpoint, method, run_id DESC
) TO STDOUT WITH CSV HEADER
" > "$OUT_DIR/table_e5_lock_latency.csv"

echo ">> Row counts by run_id (sanity check both conditions actually produced data):"
docker compose exec -T db psql -U "$PG_USER" -d "$LOCK_DB" -c \
  "SELECT run_id, count(*) FROM request_timing WHERE run_id IN ('e5_lock_on','e5_lock_off') GROUP BY run_id;"

echo ">> Stopping lock-test-api..."
docker stop lock-test-api > /dev/null 2>&1 || true

echo ">> Dropping the scratch database..."
docker compose exec -T db psql -U "$PG_USER" -d postgres -v ON_ERROR_STOP=1 \
  -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$LOCK_DB' AND pid <> pg_backend_pid();" \
  -c "DROP DATABASE IF EXISTS $LOCK_DB;" \
  > /dev/null

echo ">> Done. $OUT_DIR/table_e5_lock_latency.csv written."
