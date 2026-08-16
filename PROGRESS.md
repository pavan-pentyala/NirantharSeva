# PROGRESS

> Claude Code reads this at the start of every session and rewrites it at the
> end. It is the only memory that survives between sessions. Keep it honest —
> an optimistic PROGRESS file is worse than no PROGRESS file, because the next
> session builds on top of something that does not exist.

**Last updated:** 2026-08-16
**Last session model:** Sonnet 5

---

## Current phase

Phase 0 — code is built, committed, pushed, and verified locally. **Not yet
marked complete** — GitHub Actions has not been confirmed green by the user
(no `gh` CLI in this environment to check it directly). Next phase is P1.1
(server sync core) per the approved plan, on the user's go-ahead.

## Done

- Read handoff, preflight, implementation plan, ADR template.
- Preflight green. Two ADRs written (ADR-001, ADR-002), commit `d1fbd71`.
- Phase 0 + Phase 1 build plan approved by the user; saved at
  `C:\Users\pavan\.claude\plans\kind-spinning-fountain.md`. P1 split into
  P1.1 (server) and P1.2 (client) at the user's direction.
- **Phase 0 built, commit `3e73369`, pushed to `origin/main`.**

## Phase 0 — what was built

- Full repository layout per plan §2.2. Empty dirs (`docs/mom`,
  `docs/screenshots`, `experiments`, `generator`, `results`,
  `server/app/linkage`) carry `.gitkeep`.
- `docker-compose.yml` — four services: `db` (Postgres 16, healthcheck),
  `api`, `scheduler` (separate service from `api`, per plan — needed for E4),
  `client`. Named volume `server_venv` at `/app/.venv` so the bind-mounted
  `./server:/app` (for live reload) does not shadow the venv baked into the
  image — same trick already used for `client`'s `node_modules`. This bug
  was caught and fixed during verification, not assumed away.
- `db/init/01-create-test-db.sh` — creates `nirantharseva_test` alongside
  `nirantharseva` on first container start, so `make test` / CI never touch
  dev data.
- `server/app/clock.py` — `Clock` protocol, `RealClock`, `SimulatedClock`,
  `CLOCK_MODE` env switch, FastAPI dependency. Exactly ADR-001.
- `server/app/db.py` — async engine/session factory, `acquire_seq_lock()`
  wrapping `pg_advisory_xact_lock(4711)`. Exactly ADR-002. Not yet called by
  anything — P1.1 is the first caller.
- `server/app/api/auth.py` — JWT (PyJWT) + argon2id login against
  `DEV_USERS` env var. `get_current_user` dependency. No user table (P0
  decision, see below).
- `server/app/instrumentation/logging.py` — stdlib JSON formatter,
  `op_id`/`referral_id`/`device_id`/`run_id` as fields.
- Alembic wired async (`alembic/env.py`), baseline revision `0001` is empty.
- `server/app/scheduler/run.py` — stub entrypoint, takes the clock, sleeps.
  Real escalation sweep is Phase 5.
- Client: Vite + React 18 + TS, one screen (`App.tsx`) that fetches
  `/api/health` through the dev proxy and shows the result.
- `.github/workflows/ci.yml` — three jobs: **clock-discipline** (greps
  `server/app` for `datetime.now(`/`datetime.utcnow(`/`time.time(` outside
  `clock.py`, fails the build if found — this is ADR-001's rule enforced,
  not just documented, and was added beyond what the plan asked for);
  **server** (uv sync, ruff check + format check, alembic upgrade, pytest,
  against a real `postgres:16` service container); **client** (npm ci,
  typecheck, build).
- Tests: `tests/unit/test_clock.py`, `tests/unit/test_auth.py` (login,
  wrong password, unknown user, token roundtrip, tampered token — all
  hermetic, cache-cleared between runs), `tests/integration/test_health.py`
  (real Postgres round trip). **11/11 passing.**

## Verified, by running it, not by inspection

- `docker compose down -v` then `docker compose up -d --build` from a fully
  clean state (no volumes) — all four containers reach a healthy/running
  state.
- `curl localhost:8000/health` returns `{"status":"ok",...}`.
- `curl -X POST localhost:8000/auth/login ...` returns a valid JWT, HTTP 200.
- `curl localhost:5173/` serves the Vite app; `curl localhost:5173/api/health`
  proxies through to the API correctly.
- The exact containerized command the Makefile's `test` target runs
  (`docker compose run --rm ... api sh -c "alembic upgrade head && pytest"`)
  — 11/11 pass.
- `ruff check` and `ruff format --check` — clean, run inside the container.
- Client `npm run typecheck` and `npm run build` — clean.
- The ADR-001 CI grep was tested against a deliberately introduced violation
  (a throwaway file calling `datetime.datetime.now()`) — it caught it, then
  the clean tree was reconfirmed to pass.
- `.env` confirmed never committed (`git ls-files` and `git log` both clean).

## NOT verified

- **GitHub Actions itself has not been confirmed green.** The push happened
  (`3e73369` is on `origin/main`), but there is no `gh` CLI in this
  environment and no way to poll the Actions API without one. **The user
  needs to check the Actions tab.** Everything the CI job does was run
  locally in the identical containerized form, so it should pass, but "should
  pass locally" is not the same claim as "passed in CI".
- Stack is still running (`docker compose ps` shows all four up) so the user
  can poke at it immediately without a rebuild.

## Settled decisions (from kickoff)

- **Name:** NirantharSeva everywhere. `setucare` in the plan is the old name.
- **Python tooling:** `uv`. `uv.lock` committed.
- **UI design brief:** not ready, not needed until Phase 4.
- **Git hosting:** GitHub, private repo, GitHub Actions for CI.
- **Schedule:** plan §4 dates are tentative; no revised calendar needed —
  phase order is what matters.

## Exit criteria status — Phase 0 (Week 1)

- [x] `docker compose up` starts db, api, scheduler, client — verified cold
- [x] API health check returns 200
- [ ] GitHub Actions workflow green on push — **user must confirm**
- [x] `Clock` protocol with `RealClock` and `SimulatedClock`, wired as a
      dependency, `CLOCK_MODE` env var working — unit tested
- [x] `pg_advisory_xact_lock(4711)` helper in place (`acquire_seq_lock` in
      `app/db.py`) — not yet called by anything; P1.1 is the first caller
- [x] ADR-001 and ADR-002 written
- [ ] Review-0 submitted ← the user's task, not Claude's

**Phase 0 is not marked complete** until GitHub Actions is confirmed green.
Verify yourself:

```bash
git log --oneline -1                 # should show 3e73369 or later
# open the Actions tab on GitHub, or:
docker compose up -d                 # if stack isn't already running
curl -s localhost:8000/health
curl -s -X POST localhost:8000/auth/login -H 'content-type: application/json' \
  -d '{"username":"asha1","password":"dev"}'
# open http://localhost:5173 — should show status/clock_mode/server_time
```

## Next concrete step

1. **User confirms GitHub Actions is green** on commit `3e73369`.
2. On the user's go-ahead, start **Phase 1.1 — server sync core**, per the
   approved plan: alembic revision 0002 (toy/toy_event/sync_receipt/
   request_timing tables), `app/sync/push.py` (the four-step algorithm —
   claim receipt, acquire_seq_lock, apply, finalize, all one transaction),
   `app/sync/pull.py`, `app/schemas/sync.py` (frozen API contract — do not
   alter without asking), timing middleware, and the integration/property/
   unit tests listed in the plan. Stop after P1.1, verify, report, wait —
   do not roll into P1.2.

## Decisions taken by Claude Code without asking

_(one line each, so the user can overrule)_

- Renamed the implementation plan file to `docs/IMPLEMENTATION_PLAN.md`.
- Postgres database name is lowercase `nirantharseva`.
- `PyJWT` + `argon2-cffi` for the "JWT + argon2id" the plan names without
  specifying libraries.
- `ruff` for lint and format.
- Stdlib JSON log formatter rather than `structlog`.
- No `app_user` table in P0 — dev users come from `DEV_USERS` env var.
- Timing middleware and `request_timing` land in P1.1, not P0.
- **ADR-001's CI grep** — enforces the no-direct-clock rule at build time,
  beyond what the plan explicitly asked for.
- **`server_venv` named volume** in Compose — without it the bind mount for
  live-reload silently wipes the built virtualenv on every container start.
  Found this by actually running the stack, not by inspection.
- **Separate `nirantharseva_test` database**, created by
  `db/init/01-create-test-db.sh`, so tests never run against dev data. The
  plan did not specify this; it is the obvious safe default.
- Client `npm audit` flags a moderate vulnerability in `esbuild` (via Vite's
  dev server accepting requests from any origin — dev-server-only, not a
  production build issue). Fixing requires Vite 6 to 8, a breaking change the
  plan does not call for. Left as-is; documented here rather than silently
  ignored. Low real-world risk for a solo local-dev project.
- `client/tsconfig.tsbuildinfo` added to `.gitignore` — build artifact,
  should never have been staged.

## Open questions for the user

- Private repo means GitHub Actions minutes are metered (2000/month free).
  Fine now; worth knowing before P8's heavier CI.
- **`make` is not installed on this Windows host, and it is not in
  `docs/SETUP_PREFLIGHT.md`'s checklist either — a gap in that document.**
  Every Makefile target was verified by running the equivalent
  `docker compose` command directly, so nothing is blocked, but `make up` /
  `make test` etc. will not work until `make` exists on PATH. Two options:
  install GNU Make for Windows (`winget install ezwinports.make` — not run,
  needs your OK since it is new host software), or keep using the equivalent
  `docker compose` commands directly. Your call.

## Known problems and workarounds

- Host Python is 3.14.7; project pins 3.12 via `uv`. Container is
  `python:3.12-slim`. Do not build against 3.14.
- `uv` is installed via winget; if a fresh shell can not find it, use the
  full path `C:\Users\pavan\AppData\Local\Microsoft\WinGet\Links\uv.exe`.
- `run_id` shows as `""` rather than `null` in `/health` when `RUN_ID` is set
  to an empty string in `.env` — cosmetic, not a correctness issue. P1.1 sets
  it per-experiment-run explicitly.
