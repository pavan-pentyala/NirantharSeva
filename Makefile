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

demo:
	@echo "make demo: not implemented until Phase 4 (needs seeded referral data)."

experiments:
	@echo "make experiments: not implemented until Phase 8."
