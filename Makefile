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

# Seeds the D4 fixture district (docs/PHASE2_PLAN.md) — idempotent.
# P7.3 C5: prints the three offline-demo paths, ranked, so the sequence is
# not improvised while being watched. docs/IMPLEMENTATION_PLAN.md §14 ranks
# them; docs/Observations_for_report.md has the write-up for the report.
demo:
	docker compose run --rm api sh -c "alembic upgrade head && python -m app.seed"
	@echo ""
	@echo "Offline demo paths, ranked:"
	@echo "  1. Browser DevTools 'offline' checkbox — primary path, instant, reliable."
	@echo "  2. docker compose stop api — exercises the retry path (E4's fault injection)."
	@echo "  3. Real phone, airplane mode, added to home screen — fallback of last resort."

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
