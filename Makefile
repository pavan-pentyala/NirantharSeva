-include .env
export

.PHONY: up down test lint demo experiments logs

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f

lint:
	docker compose run --rm api sh -c "ruff check . && ruff format --check ."

# Tests run against a separate database (nirantharseva_test, created by
# db/init/01-create-test-db.sh) so `make test` never touches dev data.
test:
	docker compose run --rm \
		-e DATABASE_URL=postgresql+asyncpg://${POSTGRES_USER:-postgres}:${POSTGRES_PASSWORD:-dev}@db:5432/${POSTGRES_DB:-nirantharseva}_test \
		api sh -c "alembic upgrade head && pytest"

# Thin wrapper (D46, docs/PHASE9_PLAN.md P9.1) — the real logic lives in
# server/scripts/demo.sh because `make` is not installed on the reference
# machine, so the script must work invoked directly too. Resets the app
# database, seeds demo states, starts a demo-scale scheduler, prints the
# click path. docs/DEMO_SCRIPT.md is the full walkthrough.
demo:
	bash server/scripts/demo.sh

# Runs one experiment's grid, then regenerates its tables/figures/dashboard.
# EXP is required, not defaulted — wall-clock cost ranges from ~30s (E3) to
# ~3.7h (E2), all measured not estimated (docs/PHASE8_PLAN.md, PROGRESS.md),
# so there is no safe default to run without saying which one you mean.
#   make experiments EXP=E1
experiments:
	@if [ -z "$(EXP)" ]; then \
		echo "Usage: make experiments EXP=<E1|E2|E3|E6>"; \
		echo ""; \
		echo "Wall-clock budget (measured, not estimated — docs/PHASE8_PLAN.md):"; \
		echo "  E1  ~65 min   (45 cells)"; \
		echo "  E2  ~3.7 h    (12 cells, E2_LOAD_STEP_HOURS=12)"; \
		echo "  E3  ~30 s     (18 rows, single-pass, no clock stepping)"; \
		echo "  E6  ~56 min   (3 cells, full P7.1-scale cohort)"; \
		exit 1; \
	fi
	@exp_dir=$$(echo "$(EXP)" | tr '[:upper:]' '[:lower:]'); \
	MSYS_NO_PATHCONV=1 docker compose run --rm api python -m experiments.runner --exp $(EXP) --out /app/results/$$exp_dir/ && \
	MSYS_NO_PATHCONV=1 docker compose run --rm api python -m experiments.analysis --exp $(EXP) --in /app/results/$$exp_dir/ --out /app/results/$$exp_dir/
