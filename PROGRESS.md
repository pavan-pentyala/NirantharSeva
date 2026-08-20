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

**Phase 4 is complete** — P4.1, P4.2 and P4.3 all done. Phase 5
(escalation scheduler + SSE dashboard, Screen 4) has not started.

## Done

- Phases 0–3: complete. `docs/PHASE2_PLAN.md` / `docs/PHASE3_PLAN.md` for
  what; ADR-001–008 for why.
- Phase 4, all three sub-phases (`docs/PHASE4_PLAN.md`, D13–D16, ADR-009,
  ADR-010): server contract + client data layer, the five real screens,
  then PWA + the toy model's removal.
- The Phase 1 toy model is **gone** — migration `0006` drops `toy`/
  `toy_event`; no `ToyPage`, no `toy_cache` reads/writes, no toy branch in
  `push.py`/`pull.py`/`applyPulledEvents`. ADR-005's D7 exception ended
  exactly here, as planned.

## Not done / in progress

- Phase 5: not started, needs the user's go-ahead (handoff R1).
- **The real-phone airplane-mode recording is not done** — it is the one
  P4.3 exit criterion I cannot satisfy from here (it needs a physical
  phone). Everything it would demonstrate is covered automatically by
  `client/tests/offline-sync.spec.ts`. See "Open item" below.
- No known open bugs.

## Exit criteria status

All of P4.1, P4.2 and P4.3's criteria in `docs/PHASE4_PLAN.md` are met and
checked against real commands, **except** the real-phone recording (above).
Two criteria needed judgement rather than a clean yes/no:

- `grep -rn toy_ client/src` returns **2 matches, both required** —
  `version(1)`'s shipped declaration (never edit shipped schema history)
  and `version(4)`'s `toy_cache: null`, which *is* Dexie's drop syntax.
  `server/app` is clean. Full reasoning: observation 30.
- `offline-sync.spec.ts` runs against the **built** app on `:4173`, not the
  dev server — `injectManifest` only produces a real precache in a
  production build. Observation 33.

## Open item for the user

The real-phone clip (plan §8.5, Review-III fallback) needs a physical
Android phone: open the app, add to home screen, turn on airplane mode,
create a referral, turn signal back on, record it syncing. Ten minutes of
your time; I have no way to do it. Tell me if you'd rather drop it — the
automated test already proves the same behaviour, so it's presentation
evidence rather than verification.

## Next concrete step

Wait for the user's go-ahead on Phase 5 (escalation scheduler, SSE, the
supervisor dashboard that currently renders as a placeholder at
`/supervisor`). `react-router-dom` (yes) / `dexie-react-hooks` (no,
hand-rolled `useLiveQuery` instead) / `vite-plugin-pwa` (yes, named in the
original plan) are settled — do not re-ask.

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
Expect `187 passed`, clean.

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
