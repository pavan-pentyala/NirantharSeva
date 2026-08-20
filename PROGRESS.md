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
**Last session model:** Sonnet 5

## Current phase

Phase 4, sub-phase **P4.2 of 3 — done**. P4.3 (PWA, migration `0006` drops
the toy model, port the fault tests onto the real screens, real-phone
recording) has not started.

## Done

- Phases 0–3: complete. `docs/PHASE2_PLAN.md` / `docs/PHASE3_PLAN.md` for
  what; ADR-001–008 for why.
- Phase 4 planning: D13–D16 decided (`docs/PHASE4_PLAN.md`, ADR-009,
  ADR-010).
- P4.1 (server contract + client data layer) and P4.2 (the five real
  screens, `GET /org_units`, Dexie `referral_event_cache`/`org_cache`):
  built, tested, committed.

## Not done / in progress

- P4.3: not started, needs the user's go-ahead (handoff R1).
- No known open bugs. P4.2 found and fixed one real bug in the client-side
  referral fold (`docs/PHASE2_OBSERVATIONS.md`, Phase 4, observation 23) —
  fixed and verified in the same session, not carried forward as a TODO.

## Exit criteria status

P4.1 and P4.2: every criterion in `docs/PHASE4_PLAN.md` is `[x]`, checked
against real commands, not asserted. One unrelated pre-existing test
failure — see Known problems below, not a P4 regression.

## Next concrete step

Wait for the user's go-ahead on P4.3. `react-router-dom` (yes) /
`dexie-react-hooks` (no, hand-rolled `useLiveQuery` instead) are already
settled — do not re-ask.

## Open question for the user

An earlier session recorded "screenshots are not required, do not raise
again." `CLAUDE.md`'s own R9 asks for a screenshot the first time a screen
works, and P4.2 took 9 into `docs/screenshots/`. Flagged, not resolved —
say which one should win.

## Verify the current state yourself

```bash
docker compose up -d --build
docker compose exec client npx tsc --noEmit && docker compose exec client npm run build
cd client && npx playwright test        # expect 5 passed
```

```bash
docker compose exec db psql -U postgres -c "DROP DATABASE IF EXISTS nirantharseva_test;" -c "CREATE DATABASE nirantharseva_test;"
docker compose run --rm -e DATABASE_URL="postgresql+asyncpg://postgres:dev@db:5432/nirantharseva_test" \
  api sh -c "alembic upgrade head && python -m app.seed && ruff check . && ruff format --check . && pytest -q && python -m app.verify_replay"
```
Expect `189 passed, 1 failed` — the failure is
`test_concurrent_pushes_leave_no_gap_in_the_pull_cursor`, environment-
specific to this machine (see Known problems), not a regression.

To see the screens by hand: open `http://localhost:5173/login`, log in as
`asha_a`/`dev` (or `mo1`/`dev` for Screen 5). `/supervisor` and
`/identity-review` are reachable directly as placeholders.

## Settled decisions (do not re-ask)

- Name: NirantharSeva everywhere.
- Python: `uv`, lockfile committed. Node: `npm`, lockfile committed.
- Git hosting: GitHub, private repo, GitHub Actions CI.
- `make` is not installed — use the `docker compose` equivalents (Makefile
  documents the mapping).
- `react-router-dom`: yes. `dexie-react-hooks`: no.
- GitHub Actions minutes: not a concern.
- Review-I is a literature review/survey, not a live demo — no rehearsal
  needed.
- All Phase 2/3/4-planning decisions (D1–D16): settled — see the relevant
  `PHASE*_PLAN.md` / ADR.

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
- A long-running `vite dev` inside Docker doesn't always pick up file
  changes through the Windows bind mount. `docker compose restart client`
  fixes it — try this before debugging a test failure that looks like an
  app bug.
- `test_concurrent_pushes_leave_no_gap_in_the_pull_cursor` fails on this
  machine even on old commits where CI is green on GitHub's runner —
  environment-specific, not a regression, not investigated further
  (`docs/PHASE2_OBSERVATIONS.md`, Phase 4, observation 22).
- A persistent test-database volume across many manual `pytest` runs can
  eventually break `/sync/pull?limit=1000`-based tests. Reset with the
  `DROP DATABASE`/`CREATE DATABASE` commands above before trusting a red
  run that touches pull.
- Grep-based exit criteria match your own explanatory comments, not just
  the code — reword the comment, don't weaken the grep.
- **The rest of the hard-won detail lives in `docs/PHASE2_OBSERVATIONS.md`**
  — read it before touching `server/` or `client/src/sync/`. Append-only,
  one section per phase, never rewritten.
