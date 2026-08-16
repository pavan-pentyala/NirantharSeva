# PROGRESS

> Claude Code reads this at the start of every session and rewrites it at the
> end. It is the only memory that survives between sessions. Keep it honest —
> an optimistic PROGRESS file is worse than no PROGRESS file, because the next
> session builds on top of something that does not exist.

**Last updated:** 2026-08-16
**Last session model:** Sonnet 5

---

## Current phase

Phase 1.1 (server sync core) — built, committed, pushed, verified. **Not yet
marked complete** — same reason as Phase 0: no `gh` CLI in this environment,
so GitHub Actions has not been confirmed green on either push. Next is
**Phase 1.2 — client sync engine**, on the user's go-ahead.

## Done

- Read handoff, preflight, implementation plan, ADR template.
- Preflight green. Two ADRs written (ADR-001, ADR-002), commit `d1fbd71`.
- Phase 0 + Phase 1 build plan approved by the user; saved at
  `C:\Users\pavan\.claude\plans\kind-spinning-fountain.md`. P1 split into
  P1.1 (server) and P1.2 (client) at the user's direction.
- **Phase 0 built, commit `3e73369`.** PROGRESS/decision updates in
  `6064dea`, `2cb34b4`.
- **Phase 1.1 built, commit `982f203`, pushed to `origin/main`.**

## Phase 1.1 — what was built

- Alembic `0002`: `toy`, `toy_event`, `sync_receipt`, `request_timing`. No
  DB-side `now()` default on any timestamp column — every one is written
  from the injected Clock (ADR-001), so `CLOCK_MODE=simulated` runs stay
  internally coherent.
- `server/app/sync/push.py` — `handle_push()` follows plan §5.3 exactly:
  claim the `op_id` via `INSERT ... ON CONFLICT DO NOTHING RETURNING`
  first; a second submission of the same `op_id` replays the stored
  receipt and touches nothing else. One transaction per op.
  `apply_operation()` resolves concurrent writes to the same entity as a
  Lamport-clock **last-writer-wins register**: after appending the event,
  whichever event has the highest `(lamport, device_id)` for that entity
  wins, independent of arrival order. This was a real design decision, not
  in the plan's bare `CREATE TABLE toy(...)` — see "Decisions" below for
  why it does not need a schema change and why it makes `accepted_stale`
  mean something concrete (recorded per I2, but not the current winner).
- `server/app/sync/pull.py` — `seq > since`, ordered, fetches `limit+1` to
  compute `has_more` precisely without an extra count query.
- `server/app/schemas/sync.py` — the push/pull contract from plan §5.2/5.4.
  **Frozen — do not change without asking the user.**
- `server/app/instrumentation/timing.py` — every request now lands in
  `request_timing` (middleware was wired in Phase 0, unused until now).
- `server/app/sync/lamport.py` — `merge_lamport()`, the same max-merge
  formula the client uses after a pull (plan §5.4), used server-side to
  compute the push response's `server_lamport`.
- `server/app/sync/conflicts.py` — stub; real decision table is Phase 2
  §6.3.
- Tests (25 total, all new since Phase 0's 11): idempotent-replay
  (`test_push_idempotent.py`), concurrent-write cursor-gap check
  (`test_pull_cursor.py` — 20 concurrent pushes through the real ASGI app,
  asserts the pull afterwards has no missing `seq`), `request_timing`
  coverage, and two Hypothesis property tests in `test_permutation.py`:
  permutation invariance (three orderings of the same op set converge to
  the same final value) and retry-order idempotence (a shuffled retry
  batch produces byte-identical per-op results). Plan §5.6 calls the
  permutation test out as worth a paragraph in Chapter 4.

## Two real bugs found and fixed while making this pass

- **Windows `ProactorEventLoop` + asyncpg across pytest-asyncio's
  function-scoped event loop.** The module-level `app.db.engine`'s
  connection pool got bound to whichever event loop first used it; the
  next test's fresh loop then broke it (`AttributeError: 'NoneType' object
  has no attribute 'send'`). Fixed with
  `asyncio_default_fixture_loop_scope = "session"` and
  `asyncio_default_test_loop_scope = "session"` in `pyproject.toml`, so the
  whole test session shares one loop. Confirmed the same fix holds inside
  the Linux container too, not just on the Windows host.
- **SQLAlchemy's `text()` will not treat `:name::type` as a bind
  parameter** — it deliberately backs off to avoid clashing with
  Postgres's `::` cast syntax, so `detail=:d::jsonb` silently left `:d`
  unsubstituted and Postgres saw a syntax error. Fixed with
  `CAST(:d AS jsonb)`. Separately, raw `text()` queries get no help from
  SQLAlchemy's JSONB type layer for encoding/decoding — the dict is
  hand-`json.dumps`ed going in and `json.loads`ed coming back out
  (`_decode_detail()` in `push.py`) at that boundary.

## Verified, by running it, not by inspection

- Full suite green (25/25) via `uv run pytest` locally against the real
  `nirantharseva_test` database.
- Same 25/25 green via the exact containerized CI-equivalent command:
  `docker compose run --rm ... api sh -c "alembic upgrade head && ruff
  check . && ruff format --check . && pytest -v"`.
- Cold start (`docker compose down -v` then `up -d --build`) applies both
  migrations (`0001` then `0002`) cleanly and all four services reach a
  healthy state.
- Manual push → replay (identical response, event count still 1) → pull,
  against the live dev database via curl.
- The concurrency test (`test_pull_cursor.py`) and both property tests run
  clean across multiple repeated runs (not just once) — checked for
  flakiness deliberately given they exercise timing-sensitive paths.
- ADR-001's clock-discipline grep still passes with the new code.
- `ruff check` / `ruff format --check` clean; no new dependencies added
  (`uv.lock` untouched by this phase — confirmed via diff before
  committing).

## NOT verified

- **GitHub Actions has still not been confirmed green** — on Phase 0
  (`3e73369`) or Phase 1.1 (`982f203`). Same reason as before: no `gh` CLI
  here. Everything CI does was run locally in the identical containerized
  form and passed, but that is not the same claim as "CI passed." **User:
  please check the Actions tab for both.**
- Stack is running (`docker compose ps` — all four up) so it can be poked
  at directly without a rebuild.

## Settled decisions (carried forward)

- **Name:** NirantharSeva everywhere.
- **Python tooling:** `uv`. `uv.lock` committed.
- **UI design brief:** not ready, not needed until Phase 4.
- **Git hosting:** GitHub, private repo, GitHub Actions for CI.
- **Schedule:** plan §4 dates are tentative; phase order is what matters.
- **`make` will not be installed** — use the equivalent `docker compose`
  command from the Makefile directly.
- **Screenshots are not required** — do not raise this again.

## Exit criteria status — Phase 1.1

- [x] POST the same batch five times → row created once, five identical
      responses
- [x] Hypothesis permutation test passes
- [x] Pull returns a gap-free ordered scan under concurrent writers
- [x] Every request appears in `request_timing`
- [ ] CI green — **user must confirm** (see NOT verified)

**Phase 1.1 is not marked complete** until GitHub Actions is confirmed
green. Verify yourself:

```bash
git log --oneline -1                 # should show 982f203 or later
docker compose up -d                 # if stack isn't already running
docker compose run --rm \
  -e DATABASE_URL="postgresql+asyncpg://postgres:dev@db:5432/nirantharseva_test" \
  api sh -c "alembic upgrade head && pytest -v"
```

## Exit criteria status — Phase 0 (Week 1), for reference

- [x] `docker compose up` starts db, api, scheduler, client
- [x] API health check returns 200
- [ ] GitHub Actions workflow green on push — user must confirm
- [x] `Clock` protocol wired, `CLOCK_MODE` working
- [x] `pg_advisory_xact_lock(4711)` helper in place — now actually called,
      by `handle_push()` in Phase 1.1
- [x] ADR-001 and ADR-002 written
- [ ] Review-0 submitted — the user's task, not Claude's

## Next concrete step

1. **User confirms GitHub Actions is green** on `3e73369` and `982f203`.
2. On the user's go-ahead, start **Phase 1.2 — client sync engine**, per
   the approved plan: Dexie schema (`outbox`, `toy_cache`, `sync_meta`),
   the `flush()` single-flight loop with the four triggers (`online`
   event, 15s timer, after every local mutation, `visibilitychange`),
   `applyResults()` (accepted/accepted_stale → synced; conflict/rejected →
   re-pull and overwrite, never hand-written inverse ops), the minimal
   `ToyPage.tsx` harness (number input, Save button, online/pending/last-
   sync status line — no PWA, no service worker, those are Phase 4), and
   the three fault tests from plan §5.6 (50 ops offline → reconnect;
   `docker kill` the API mid-batch; kill the client mid-push). These three
   become experiment E4. Stop after P1.2, verify, report, wait.

## Decisions taken by Claude Code without asking

_(one line each, so the user can overrule)_

- Renamed the implementation plan file to `docs/IMPLEMENTATION_PLAN.md`.
- Postgres database name is lowercase `nirantharseva`.
- `PyJWT` + `argon2-cffi`, `ruff` for lint/format, stdlib JSON log
  formatter, no `app_user` table in P0 — dev users come from `DEV_USERS`.
- **ADR-001's CI grep** — enforces the no-direct-clock rule at build time.
- **`server_venv` named volume** in Compose — the bind mount for live
  reload otherwise wipes the built virtualenv.
- **Separate `nirantharseva_test` database** — tests never touch dev data.
- **The LWW-register conflict resolution in `apply_operation()`** — the
  plan's toy schema (`toy(id, value, updated_at)`) has no lamport column,
  and the plan does not spell out how "final state" should converge under
  permuted delivery order. Rather than add a `lamport` column to `toy`
  (a schema change beyond what was approved) I compute the winner by
  re-querying `toy_event` for the highest `(lamport, device_id)` after
  every append, and write only *that* event's value into the `toy.value`
  cache. No schema change; the property test needs this to hold, and it
  is what gives `accepted_stale` a real meaning. Flagging this because
  it is a real design decision, not a formatting choice.
- **`asyncio_default_fixture_loop_scope`/`asyncio_default_test_loop_scope
  = "session"`** in `pyproject.toml` — required for asyncpg to work
  correctly across the whole pytest session; see "bugs found" above.
- Client `npm audit` flags a moderate `esbuild`/Vite dev-server-only
  vulnerability; fixing needs a Vite 6→8 breaking bump. Left as-is,
  documented, low real-world risk for solo local dev.
- `client/tsconfig.tsbuildinfo` added to `.gitignore`.

## Open questions for the user

- Private repo means GitHub Actions minutes are metered (2000/month free).
  Fine now; worth knowing before P8's heavier CI.

## Known problems and workarounds

- Host Python is 3.14.7; project pins 3.12 via `uv`. Container is
  `python:3.12-slim`. Do not build against 3.14.
- `uv` is installed via winget; if a fresh shell can not find it, use the
  full path `C:\Users\pavan\AppData\Local\Microsoft\WinGet\Links\uv.exe`.
- `run_id` shows as `""` rather than `null` in `/health` and in
  `toy`/`toy_event` rows when `RUN_ID` is set to an empty string in
  `.env` — cosmetic, not a correctness issue. Real experiment runs (P8)
  set it explicitly per run.
