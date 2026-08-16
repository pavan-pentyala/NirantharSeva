# NirantharSeva

Offline-first referral continuity system for community health workflows.
Individual MTech case-study project.

See `CLAUDE.md` and `docs/HANDOFF_CLAUDE_CODE.md` for how this repository is
built. See `docs/IMPLEMENTATION_PLAN.md` for what is being built.

## Run it

```bash
cp .env.example .env
make up
```

- API: http://localhost:8000/health
- Client: http://localhost:5173

## Test it

```bash
make test
```

Runs against a separate `nirantharseva_test` database — never against dev data.

## Stack

PostgreSQL 16 · FastAPI + SQLAlchemy + Alembic · APScheduler · React 18 +
TypeScript + Vite · Dexie.js · JWT + argon2id · Docker Compose · GitHub Actions ·
pytest + Hypothesis · Playwright · k6

Everything runs through Docker Compose. Nothing is installed on the host.
