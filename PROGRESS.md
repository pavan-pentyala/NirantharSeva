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
**Last session model:** Sonnet 5 (P5.1 implementation). Planning was Opus.

## Current phase

**P5.1 is code-complete and verified** — SLA profiles, the escalation
sweep, and the escalation lifecycle. Server only, no migration, `alembic
heads` still `0006`. **Waiting for the user to review before starting
P5.2** (SSE transport + Screen 4, `docs/PHASE5_PLAN.md`) — do not start it
without an explicit go-ahead (handoff R1).

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
  PHASE5_PLAN's "What P5.1 must prove" table. `docs/PHASE2_OBSERVATIONS.md`
  Phase 5 section, observations 34–36.

## Not done / in progress

- P5.2 (SSE transport, `GET /dashboard/stream`, Screen 4): not started.
  Needs its own go-ahead.
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
honours a `SimulatedClock`, `SLA_SCALE` changes the window, the
`datetime.now()` grep is clean, `ruff` and the full suite (197 tests) are
green.

One small decision made without asking, flagged here per handoff §7:
**`escalation.escalated_to_user_id` is left `NULL`.** The plan's own sweep
snippet doesn't populate it either, and resolving `sla_profile.escalate_to_role`
to one specific `app_user` needs a rule (which org? which user if several
share the role?) that build order item 3/4 doesn't specify — "Not in this
plan" only says the column *is* populated eventually, "but nothing acts on
it beyond display." Left for P5.2 or later if the dashboard ends up needing
a specific name rather than just the role.

## Open item for the user

**The real-phone clip** (plan §8.5, the Review-III fallback) is still
owed, and is being kept. Needs a physical Android phone: open the app, add
to home screen, airplane mode, create a referral, restore signal, record it
syncing. Ten minutes; nothing in this repo can do it. Note where the file
lands here once recorded — it is deliberately not committed (large binary).

## Next concrete step

**Start P5.2** on the user's go-ahead: SSE transport (`GET
/dashboard/stream`, ADR-011/ADR-012) + Screen 4, per `docs/PHASE5_PLAN.md`.

## Verify the current state yourself

Client. **Both** servers must be up: `:5173` (dev, four specs) and `:4173`
(the built app with its real PWA precache — `offline-sync.spec.ts` only).

```bash
docker compose up -d --build
docker compose exec client npx tsc --noEmit && docker compose exec client npm run build
docker compose exec -d client npm run preview        # starts :4173
cd client && npx playwright test                     # expect 5 passed
```

Server (`alembic heads` should print `0006`):

```bash
docker compose exec db psql -U postgres -c "DROP DATABASE IF EXISTS nirantharseva_test;" -c "CREATE DATABASE nirantharseva_test;"
docker compose run --rm -e DATABASE_URL="postgresql+asyncpg://postgres:dev@db:5432/nirantharseva_test" \
  api sh -c "alembic upgrade head && python -m app.seed && ruff check . && ruff format --check . && pytest -q && python -m app.verify_replay"
```
Expect `197 passed`, clean.

Escalation sweep, specifically (P5.1's headline, without waiting for a real
SLA window):

```bash
docker compose exec -T db psql -U postgres -d nirantharseva -c "SELECT state, max_hours, escalate_to_role FROM sla_profile ORDER BY state;"
docker compose run --rm -e SLA_SCALE=0.0001 -e SWEEP_INTERVAL_SECONDS=2 -d --name sweep-demo scheduler
# wait ~5s, then:
docker compose exec -T db psql -U postgres -d nirantharseva -c "SELECT referral_id, breached_state, resolved_at FROM escalation;"
docker stop sweep-demo && docker rm sweep-demo   # -d means --rm does not apply; clean up by hand
```
**This escalates real dev-database referrals** — observation 35 in
`docs/PHASE2_OBSERVATIONS.md` is the story of this exact command's
foreground (`timeout`-wrapped, non-`-d`) form outliving its tool call and
quietly re-escalating a "fresh" reseed for several minutes. Run it `-d` (as
above, not foreground-and-killed) and stop/rm it explicitly, or run it
against `nirantharseva_test` instead of `nirantharseva`, and reseed
afterward (`docker compose exec api python -m app.seed` only re-adds
missing rows — it does not undo an escalation).

To see the screens by hand: open `http://localhost:5173/login`, log in as
`asha_a`/`dev` (or `mo1`/`dev` for Screen 5). `/supervisor` and
`/identity-review` are reachable directly as placeholders.

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
