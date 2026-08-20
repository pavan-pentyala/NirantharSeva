# NirantharSeva

Offline-first referral continuity system for community health workflows.
Individual MTech case-study project.

See `CLAUDE.md` and `docs/HANDOFF_CLAUDE_CODE.md` for how this repository is
built. See `docs/IMPLEMENTATION_PLAN.md` for what is being built.

## Run it

```bash
cp .env.example .env
docker compose up --build
```

- API: http://localhost:8000/health
- Client: http://localhost:5173

`Makefile` documents these as `make up` / `make test` / etc., but `make`
itself is not installed on the reference dev machine — run the
`docker compose` commands directly, or use the Makefile as a command
reference on a machine that has `make`.

## Test it

```bash
docker compose run --rm \
  -e DATABASE_URL=postgresql+asyncpg://postgres:dev@db:5432/nirantharseva_test \
  api sh -c "alembic upgrade head && pytest"
```

Runs against a separate `nirantharseva_test` database — never against dev data.

## Stack

PostgreSQL 16 · FastAPI + SQLAlchemy + Alembic · APScheduler · React 18 +
TypeScript + Vite · Dexie.js · JWT + argon2id · Docker Compose · GitHub Actions ·
pytest + Hypothesis · Playwright · k6

Everything runs through Docker Compose. Nothing is installed on the host.
