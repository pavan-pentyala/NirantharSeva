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

experiments:
	@echo "make experiments: not implemented until Phase 8."
