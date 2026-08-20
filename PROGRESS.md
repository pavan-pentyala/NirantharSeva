# PROGRESS

> Read at the start of every session, rewritten at the end. Its only job is
> to answer: where are we, what's next, what should I know before I start.
> The how/why already live elsewhere — ADRs for architecture decisions,
> `docs/PHASE*_PLAN.md` for what each phase built and why, git log for what
> changed and when, `docs/PHASE2_OBSERVATIONS.md` for hard-won lessons
> (append-only, one section per phase). Keep this file short: duplicating
> those here just gives a future session more text to read for the same
> information, at lower quality.

**Last updated:** 2026-08-20
**Last session model:** Sonnet 5 (P5.1 and P5.2 implementation, same
session). Planning was Opus.

## Current phase

**Phase 5 is code-complete and verified** — P5.1 (SLA profiles, the
escalation sweep, escalation lifecycle) and P5.2 (LISTEN/NOTIFY, the
dashboard endpoints, Screen 4, the D20 overlay on Screens 1/3/5), built in
one session. Server only added two new endpoints, no migration — `alembic
heads` is still `0006`. **Waiting for the user to review.** Phase 6
(identity resolution) has not been planned yet — that needs its own
planning session (Opus) before implementation starts.

## Done

- Phases 0–3: complete. `docs/PHASE2_PLAN.md` / `docs/PHASE3_PLAN.md` for
  what; ADR-001–008 for why.
- Phase 4, all three sub-phases (`docs/PHASE4_PLAN.md`, D13–D16, ADR-009,
  ADR-010): server contract + client data layer, the five real screens,
  then PWA + the toy model's removal.
- The Phase 1 toy model is **gone** — migration `0006` drops `toy`/
  `toy_event`. ADR-005's D7 exception ended exactly here, as planned.
- Phase 5 planning: D17–D22 decided with the user, ADR-011 (LISTEN/NOTIFY)
  and ADR-012 (SSE query-token auth) written. P5.1/P5.2 split approved.
- **P5.1** (`docs/PHASE5_PLAN.md` build order): `SLA_SCALE` +
  `SWEEP_INTERVAL_SECONDS` config (D17); five `sla_profile` seed rows, one
  per escalatable state; `app/domain/escalation.py`'s `sweep()`; the
  system-event append (extracted into `app/sync/event_log.py`'s
  `insert_referral_event`, shared with `push.py`); escalation resolution on
  exit from `ESCALATED` in `push.py`'s `_apply_referral_transition` (D22);
  `app/scheduler/run.py` now runs `sweep()` on an `AsyncIOScheduler`
  interval instead of `sleep(3600)`. `apscheduler` added as a dependency
  (already named in the plan's stack list). 10 new tests in
  `tests/integration/test_escalation_sweep.py`, one per row of
  PHASE5_PLAN's "What P5.1 must prove" table.
- **P5.2** (`docs/PHASE5_PLAN.md` build order): `NOTIFY` inside the sweep's
  own transaction (`app/realtime.py` holds the dedicated `LISTEN`
  connection + subscriber fan-out, wired into `app/main.py`'s new
  `lifespan`); `GET /dashboard` and `GET /dashboard/stream`
  (`app/api/dashboard.py`, one shared org-scoped query, `stream_events()`
  pulled out as a standalone generator so it's testable without going
  through HTTP — see its docstring); `get_current_user_from_query_token`
  in `app/api/auth.py` (ADR-012); `app/api/scoping.py`'s call-site list
  updated. Client: Dexie v5 (`dashboard_stats_cache` +
  `dashboard_overdue_cache`), `client/src/sync/dashboardStream.ts`
  (`EventSource`, query-token auth), `client/src/domain/displayState.ts`
  (D20's derivation), `StatePill`'s new `overdue` prop, Screen 4
  (`SupervisorDashboardPage`), the D20 overlay applied to Screens 1, 3, 5.
  9 new/changed Playwright tests in `client/tests/dashboard.spec.ts`,
  including the plan's headline (a live breach, no reload) and one that
  specifically exercises D22's resolution path from the client side.
  `docs/PHASE2_OBSERVATIONS.md` Phase 5 section, observations 34–39.

## Not done / in progress

- Phase 6 (identity resolution + gold set + review queue): not planned.
  Needs an Opus planning session before any code.
- **The real-phone airplane-mode recording is not done.** User has said
  keep it — do not drop it, do not re-propose dropping it.
- No known open bugs.

## Exit criteria status

Phase 4: every criterion in `docs/PHASE4_PLAN.md` met and checked against
real commands, **except** the real-phone recording. Two needed judgement:

- `grep -rn toy_ client/src` returns **2 matches, both required** —
  `version(1)`'s shipped declaration (never edit shipped schema history)
  and `version(4)`'s `toy_cache: null`, which *is* Dexie's drop syntax.
  `server/app` is clean. Observation 30.
- `offline-sync.spec.ts` runs against the **built** app on `:4173`, not the
  dev server — `injectManifest` only produces a real precache in a
  production build. Observation 33.

P5.1: every criterion in `docs/PHASE5_PLAN.md` checked against real
commands — `alembic heads` is `0006`, seeding is idempotent, the sweep
escalates a breached referral and leaves within-SLA/dead/already-escalated
ones alone, two sweeps over one open breach produce one row/one event (the
partial index's doing — see the note in `test_escalation_sweep.py` on how
that's actually exercised, not just asserted), resolution-then-rebreach
produces a second row, `verify_replay` is clean after a sweep, the sweep
honours a `SimulatedClock`, `SLA_SCALE` changes the window (this specific
check had a real bug behind it — see "Known problems" below and
observation 37), the `datetime.now()` grep is clean.

P5.2: every criterion in `docs/PHASE5_PLAN.md` checked against real
commands and, for the headline one, a real browser — with demo config, a
referral created as `asha_a` appears on `supervisor1`'s dashboard with no
page reload (`client/tests/dashboard.spec.ts`, screenshots in
`docs/screenshots/`); `EventSource` recovers from a dropped connection
(simulated via `context.setOffline`, not a literal container kill — a
Playwright spec running inside the client container has no way to restart
a sibling container; see the test's own docstring); an escalated referral
keeps its real state label and the overdue treatment on Screens 1, 3 and 5,
and still offers its real action button (D20) — Screen 5 specifically
because that's where a real bug was in the first draft (observation 38);
subtree scoping is proven server-side (`test_dashboard.py`, two org
branches) and not re-proven client-side, since the client has no scoping
logic of its own to get wrong; no banned word in the dashboard's own copy,
read by hand; `tsc --noEmit`, `npm run build`, and both test suites (server
205, client 9) are green.

Two small decisions made without asking, flagged here per handoff §7:

- **`escalation.escalated_to_user_id` stays `NULL`.** Unchanged from P5.1 —
  the dashboard shows the ASHA's name by joining `origin_user_id`, not this
  column, so nothing in P5.2 needed it populated either.
- **No role-gate on `GET /dashboard`/`GET /dashboard/stream` beyond
  authentication + org-subtree scoping.** Matches every other read endpoint
  in this codebase (`GUARDS` governs writes, not reads) — any authenticated
  role can view the dashboard for their own subtree, same as `GET
  /referrals`.

## Open item for the user

**The real-phone clip** (plan §8.5, the Review-III fallback) is still
owed, and is being kept. Needs a physical Android phone: open the app, add
to home screen, airplane mode, create a referral, restore signal, record it
syncing. Ten minutes; nothing in this repo can do it. Note where the file
lands here once recorded — it is deliberately not committed (large binary).

## Next concrete step

**Phase 6 needs planning first** (identity resolution + gold set + review
queue) — an Opus session against `docs/IMPLEMENTATION_PLAN.md`'s Phase 6
section, the way `docs/PHASE5_PLAN.md` was written for this phase. Do not
start writing Phase 6 code without that plan existing and the user's
go-ahead on it.

## Verify the current state yourself

**Always `cd` into the repo root before any `docker compose` command —
never pass `-f <path>` from a different cwd.** Compose derives its project
name from the cwd's basename; a mismatched cwd made it recreate `db-1`
unexpectedly this session (data survived only because `pgdata` is a named
volume, not a bind mount — don't rely on that).

Client. **Playwright runs from the host** (`cd client && npx playwright
test`), not via `docker compose exec` — `client/tests/helpers.ts` calls
`http://localhost:8000` directly, which only resolves from the host (the
port Compose publishes), not from inside the `client` container's own
network namespace. The host needs its own `npx playwright install
chromium` once (separate from anything installed inside the container).
**Both** servers must be up: `:5173` (dev) and `:4173` (the built app with
its real PWA precache — `offline-sync.spec.ts` only).

```bash
docker compose up -d --build
docker compose exec client npx tsc --noEmit && docker compose exec client npm run build
docker compose exec -d client npm run preview        # starts :4173
cd client && npx playwright test                     # expect 9 passed, ~2 min (see below)
```

Two of those 9 tests need a demo-scale scheduler running first, or they'll
sit at their real-SLA pace instead of failing fast — start one before the
`npx playwright test` above:

```bash
docker compose run --rm -d --name demo-scheduler -e SLA_SCALE=0.0004 -e SWEEP_INTERVAL_SECONDS=5 scheduler
# ... run the tests ...
docker stop demo-scheduler   # started with --rm, so this also removes it
```

Server (`alembic heads` should print `0006`):

```bash
docker compose exec db psql -U postgres -c "DROP DATABASE IF EXISTS nirantharseva_test;" -c "CREATE DATABASE nirantharseva_test;"
docker compose run --rm -e DATABASE_URL="postgresql+asyncpg://postgres:dev@db:5432/nirantharseva_test" \
  api sh -c "alembic upgrade head && python -m app.seed && ruff check . && ruff format --check . && pytest -q && python -m app.verify_replay"
```
Expect `205 passed`, clean.

Escalation sweep + dashboard, specifically (Phase 5's headline, without
waiting for a real SLA window):

```bash
docker compose exec -T db psql -U postgres -d nirantharseva -c "SELECT state, max_hours, escalate_to_role FROM sla_profile ORDER BY state;"
docker compose run --rm -e SLA_SCALE=0.0004 -e SWEEP_INTERVAL_SECONDS=5 -d --name sweep-demo scheduler
# wait ~40s (CREATED's 24h SLA scaled), then:
docker compose exec -T db psql -U postgres -d nirantharseva -c "SELECT referral_id, breached_state, resolved_at FROM escalation;"
docker stop sweep-demo   # started with --rm, this also removes it — docker ps -a is worth checking anyway
```
**This escalates real dev-database referrals** — observations 35 and 39 in
`docs/PHASE2_OBSERVATIONS.md` are two separate incidents this session of a
container from exactly this pattern outliving its tool call and quietly
re-escalating a "fresh" reseed. Confirm `docker ps -a` shows only the four
real services before trusting a "clean" reseed, and after `docker compose
down -v` reports success — if it says a volume or network is "still in
use," an orphan is still attached and `down` did not actually clean up.
**`SLA_SCALE` must be a value PostgreSQL will bind as a float without an
explicit cast doing the work — see observation 37: `0.5` and `0.0004` are
fine, but do not remove the `CAST(:sla_scale AS double precision)` from
`app/domain/escalation.py`'s query, or every fractional scale silently
becomes 0 and everything escalates instantly.**

To see the screens by hand: open `http://localhost:5173/login`, log in as
`asha_a`/`dev`, `mo1`/`dev` for Screen 5, or `supervisor1`/`dev` for Screen
4 (`/supervisor`, now a real live dashboard, not a placeholder).
`/identity-review` is still a Phase 6 placeholder.

## Settled decisions (do not re-ask)

- Name: NirantharSeva everywhere.
- Python: `uv`, lockfile committed. Node: `npm`, lockfile committed.
- Git hosting: GitHub, private repo, GitHub Actions CI.
- `make` is not installed — use the `docker compose` equivalents (Makefile
  documents the mapping).
- `react-router-dom`: yes. `dexie-react-hooks`: no. `vite-plugin-pwa`: yes.
- GitHub Actions minutes: not a concern.
- Screenshots: either way is fine (user's answer) — `docs/screenshots/`
  currently holds one per screen plus the PWA offline-reload proof.
- Review-I is a literature review/survey, not a live demo — no rehearsal
  needed.
- The real-phone offline clip stays on the list. Do not propose dropping
  it again.
- All decisions D1–D22: settled — see the relevant `PHASE*_PLAN.md` / ADR.
  Phase 5's four (SSE query-token auth, LISTEN/NOTIFY, `SLA_SCALE`,
  P5.1/P5.2 split) were answered 2026-08-20; do not re-ask them.

## Known problems and workarounds

- **`app/domain/escalation.py`'s breach query needs `SLA_SCALE` explicitly
  cast to `double precision` — without it, any scale strictly between 0
  and 1 is silently truncated to integer 0 by asyncpg's prepared-statement
  type inference, and `make_interval`'s result becomes exactly zero, so
  every referral escalates the instant it's created regardless of its real
  age.** `SLA_SCALE=1.0` (production) hides this completely — this only
  shows up at demo-scale, which is exactly when someone is watching. Fixed
  this session; see observation 37 before touching that query again.
- Playwright runs from the **host** (`cd client && npx playwright test`),
  not `docker compose exec client npx playwright test` —
  `client/tests/helpers.ts` posts to `http://localhost:8000` directly,
  which is the *host's* published port, not reachable from inside the
  `client` container's own network namespace. The host needs its own
  Chromium (`npx playwright install chromium`), separate from anything
  installed inside the container.
- **Always `cd` into the repo root before `docker compose` commands** —
  invoking it with `-f <full-path>` from a different cwd made Compose
  recreate `db-1` unexpectedly this session (Compose derives its project
  name from the cwd's basename). No data was lost only because `pgdata` is
  a named volume, reattached to the new container rather than recreated —
  do not rely on that safety net a second time.
- Host Python is 3.14.7; project pins 3.12 via `uv` — never build against
  host Python.
- `uv` full path if a fresh shell can't find it:
  `C:\Users\pavan\AppData\Local\Microsoft\WinGet\Links\uv.exe`.
- Docker Desktop lives at
  `C:\Users\pavan\AppData\Local\Programs\DockerDesktop\Docker Desktop.exe`
  (not Program Files) — start it and wait ~1 minute if compose can't reach
  the daemon.
- Named volumes (`server_venv`, `client_node_modules`) need `-V` to refresh
  after a dependency change: `docker compose up -d --build -V <service>`.
  **`-V` did not actually do it for `server_venv` when adding apscheduler
  this session** — `scheduler` still raised `ModuleNotFoundError` after a
  `--build -V` bringing up both `api` and `scheduler` (a *shared* named
  volume, mounted by two services at once). What worked: `docker compose
  rm -sf api scheduler && docker volume rm nirantharseva_server_venv &&
  docker compose up -d --build api scheduler`. If `-V` alone doesn't fix a
  stale-dependency error, remove the volume by hand rather than assuming
  the container needs a deeper rebuild.
- A `docker compose run --rm` container killed via a wrapping `timeout`
  can outlive the tool call and survive a subsequent `docker compose down
  -v` (which will report the network/volume "still in use" — read that
  warning, it means an orphan is still attached). See observation 35,
  `docs/PHASE2_OBSERVATIONS.md`. Check with `docker ps -a` (not `docker
  compose ps`, which only lists service containers) after anything
  `timeout`-wrapped; clean up with `docker rm -f <name>` before trusting
  a "fresh" `down -v && up`.
- A long-running `vite dev` inside Docker doesn't always pick up file
  changes through the Windows bind mount. `docker compose restart client`
  fixes it — try this before debugging a test failure that looks like an
  app bug. **Hit twice in P4.3**; it costs a confusing red run every time.
- `docker compose restart client` also **kills the `:4173` preview
  server** (it isn't the container's main command). Restart it by hand
  afterwards or `offline-sync.spec.ts` fails for the wrong reason:
  `docker compose exec -d client npm run preview`.
- `test_concurrent_pushes_leave_no_gap_in_the_pull_cursor` used to fail
  intermittently on this machine while green in CI (observation 22). P4.3
  ported it off the toy model onto referral ops and it has passed on every
  run since — watch it, but it is no longer a known failure.
- A persistent test-database volume across many manual `pytest` runs can
  eventually break `/sync/pull?limit=1000`-based tests. Reset with the
  `DROP DATABASE`/`CREATE DATABASE` commands above before trusting a red
  run that touches pull.
- Grep-based exit criteria match your explanatory comments, your own
  identifiers, and your framework's required syntax — not just the code
  you meant to find. Read every match; never treat the hit count as
  pass/fail (observations 13, 29, 30).
- **The rest of the hard-won detail lives in `docs/PHASE2_OBSERVATIONS.md`**
  — read it before touching `server/` or `client/src/sync/`. Append-only,
  one section per phase, never rewritten.
