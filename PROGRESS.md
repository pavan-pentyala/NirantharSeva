# PROGRESS

> Claude Code reads this at the start of every session and rewrites it at the
> end. It is the only memory that survives between sessions. Keep it honest —
> an optimistic PROGRESS file is worse than no PROGRESS file, because the next
> session builds on top of something that does not exist.

**Last updated:** 2026-08-16
**Last session model:** Sonnet 5

---

## Current phase

**Phase 1 (sync core) is complete — both P1.1 and P1.2.** All five exit
criteria from plan §5.6 are met and verified by running them, not by
inspection. **Not yet marked "done"** in the strict sense used elsewhere in
this file — GitHub Actions has still not been confirmed green by the user on
any of the pushes so far (no `gh` CLI in this environment). Next is
**Phase 2 — domain, state machine, RBAC** (plan §6), on the user's go-ahead.
Phase 2 is design-and-schema work first — read plan §6 in full before writing
any code, and the schema/state-machine decisions there are squarely "ask the
user" territory per handoff §2, not "decide yourself."

## Done

- Read handoff, preflight, implementation plan, ADR template.
- Preflight green. Two ADRs written (ADR-001, ADR-002), commit `d1fbd71`.
- Phase 0 + Phase 1 build plan approved by the user; saved at
  `C:\Users\pavan\.claude\plans\kind-spinning-fountain.md`.
- **Phase 0 built, commit `3e73369`.**
- **Phase 1.1 (server sync core) built, commit `982f203`.**
- **Phase 1.2 (client sync engine) built, commit `5038708`, pushed.**
- PROGRESS/decision-log updates: `6064dea`, `2cb34b4`, `c49a30d`.

## Phase 1.2 — what was built

- `client/src/db/schema.ts` — Dexie `outbox` / `toy_cache` / `sync_meta`.
  `toy_cache` also carries `lamport`/`device_id` (not just `value`) so the
  client can replay pulled events using the same last-writer-wins
  comparison the server uses in `apply_operation()`, rather than naively
  taking whichever event arrived last in a pull.
- `client/src/db/meta.ts` — device_id / lamport / cursor / last-sync-at,
  all persisted in `sync_meta`. `mergeLamport()` mirrors the server's
  `app/sync/lamport.py`.
- `client/src/api/client.ts` — thin fetch wrapper matching
  `app/schemas/sync.py` exactly (the frozen contract).
- `client/src/sync/engine.ts` — `flush()` (single-flight guard, marks the
  batch `inflight` before the request so a crash mid-request is safe to
  retry — the server is idempotent by `op_id`), `applyResults()`
  (accepted/accepted_stale → synced; conflict/rejected → re-pull and
  overwrite, never a hand-written inverse op), `pullAndApply()` (folds
  pulled events into `toy_cache` via the LWW rule), `startAutoFlush()`
  (wires the four triggers: `online`, 15s timer, after every mutation,
  `visibilitychange`).
- `client/src/pages/ToyPage.tsx` — the minimal harness: number input, Save
  button, status line (online/offline, pending count, last sync). Reads
  only from the local cache (handoff §8). Wired into `App.tsx`.
- Fault tests, all three from plan §5.6, all become experiment E4:
  - `client/tests/offline-sync.spec.ts` (Playwright) — 50 ops created
    offline, reconnect, all 50 land exactly once. Verified both
    client-side (outbox all `synced`) and server-side (each generated
    `op_id` appears in a pull exactly once — not zero, not more).
  - `client/tests/client-kill-resume.spec.ts` (Playwright) — intercepts
    `/sync/push` to hang forever, closes the tab while the op is
    `inflight`, reopens a fresh page against the same persistent
    IndexedDB, confirms the retry lands exactly once.
  - `server/tests/fault/kill_api.sh` — `docker kill`s the API mid-batch
    (20 ops), restarts it, retries the identical batch, confirms exactly
    20 `toy_event` rows exist for that entity — not 40, not fewer. **Not
    part of CI's automated pytest run** — it manipulates real containers,
    run on demand: `bash server/tests/fault/kill_api.sh`.
- `.github/workflows/ci.yml` — new `e2e` job. Runs `docker compose`
  directly (not uv/npm on the runner) so the environment matches local dev
  exactly and `kill_api.sh`'s `docker compose kill` works unmodified. Runs
  Playwright, then the kill_api fault script, then tears the stack down.

## Real bugs found and fixed while making the fault tests pass

- **A stale Docker volume served pre-Dexie code for over an hour.** Both
  the client and server images use a named volume
  (`client_node_modules`, `server_venv`) so the bind-mounted source
  directory (needed for live reload) doesn't shadow the dependencies
  baked into the image. Named volumes are still **reused across `--build`**
  unless explicitly recreated with `-V` — `docker compose up --build`
  alone silently keeps serving the old `node_modules`. This is now
  documented with a comment directly in `docker-compose.yml`.
- **React 18 StrictMode double-invokes effects in dev mode.** The
  `ToyPage` mount effect does `await login(); stop = startAutoFlush();` —
  StrictMode's simulated unmount runs the cleanup *before* that `await`
  resolves, so it captures `stop` as still `undefined` and the cleanup is
  a no-op. Without a guard this leaves two 15-second intervals and two
  sets of `online`/`visibilitychange` listeners running concurrently.
  Fixed with a module-level "started once" guard in `startAutoFlush()`
  (`client/src/sync/engine.ts`).
- **The flakiness chased while debugging `client-kill-resume.spec.ts`
  turned out to be a test bug, not an engine bug.** React's
  `pendingCount` state starts at `0`, and the actual retry after "reload"
  completes in single-digit milliseconds — faster than the harness's own
  500ms display-poll interval. A UI-text assertion of `"0 pending"` could
  therefore pass against the stale *initial* render, before any real poll
  had run at all. Fixed by polling the actual IndexedDB row via
  `expect.poll()` instead of asserting on the UI text for correctness —
  the UI text is still checked, just not relied on for the pass/fail
  signal.

## Decision put to the user mid-phase

`docs/SETUP_PREFLIGHT.md` flagged Playwright's ~1-2GB browser download as
a Phase-4 concern, not now. But P1.2's fault tests need a real browser and
real IndexedDB to be genuine — a lighter Node + `fake-indexeddb` approach
was offered as the alternative. **User chose: install Playwright now.**
Chromium is installed at `C:\Users\pavan\AppData\Local\ms-playwright\`.
This also means CI's new `e2e` job downloads a browser on every run —
adds real minutes to the private repo's metered Actions usage (see open
questions).

## Verified, by running it, not by inspection

- Full cold start from a wiped volume state
  (`docker compose down -v` then `up -d --build`) — all four services
  healthy, both migrations (`0001`, `0002`) applied cleanly.
- Server suite: 25/25 green via the exact containerized command CI uses.
- Both Playwright fault tests: green, individually and together, across
  five repeated runs each (checked deliberately for flakiness given they
  are timing-sensitive).
- `kill_api.sh`: green across three repeated runs.
- Client `npm run typecheck` and `npm run build`: clean.
- All of the above run **in sequence against the same cold-started stack**,
  matching the new CI `e2e` job's actual order, not just individually.

## NOT verified

- **GitHub Actions has still not been confirmed green** — not on `3e73369`
  (Phase 0), not on `982f203` (Phase 1.1), not on `5038708` (Phase 1.2).
  Same reason every time: no `gh` CLI in this environment. Everything CI
  does was run locally in the identical or near-identical form and
  passed, but that is not the same claim as "CI passed." **User: please
  check the Actions tab for all three.** The new `e2e` job in particular
  is worth watching — it is the most complex job (docker compose + a
  browser download + two kinds of fault test) and has not run on GitHub's
  runners even once yet, only on this machine.
- Stack is running; `docker compose ps` shows all four up.

## Settled decisions (carried forward)

- **Name:** NirantharSeva everywhere.
- **Python tooling:** `uv`. `uv.lock` committed.
- **UI design brief:** not ready, not needed until Phase 4.
- **Git hosting:** GitHub, private repo, GitHub Actions for CI.
- **Schedule:** plan §4 dates are tentative; phase order is what matters.
- **`make` will not be installed** — use the equivalent `docker compose`
  command from the Makefile directly.
- **Screenshots are not required** — do not raise this again.
- **Playwright installed now, not deferred to Phase 4** (see above).

## Exit criteria status — Phase 1 (plan §5.6, all five)

- [x] 50 ops created offline → reconnect → all 50 land exactly once
- [x] `docker kill` the API mid-batch → retry → final state identical, no
      duplicates
- [x] Kill the client mid-push → reload → ops resume and land exactly once
- [x] Same batch POSTed 5× → created once, 5 identical responses
- [x] Hypothesis permutation property test passes

**All five met.** GitHub Actions confirmation is the only thing standing
between this and an unqualified "Phase 1 done."

## Exit criteria status — Phase 0 and 1.1, for reference

Both fully met locally; same GitHub Actions caveat as above. See commit
messages on `3e73369` and `982f203` for detail if needed — not repeating
the full checklist here to keep this file from growing without bound.

## Next concrete step

1. **User confirms GitHub Actions is green** on `3e73369`, `982f203`, and
   `5038708` — especially the new `e2e` job, which has never run on
   GitHub's infrastructure.
2. On the user's go-ahead, start **Phase 2 — domain, state machine, RBAC**
   (plan §6, week 3). This is a bigger phase than P0/P1.1/P1.2: it
   introduces the real schema (patients, referrals, org units, roles),
   throws away the toy model, builds the state machine as pure functions
   (plan §6.2), the conflict decision table (§6.3, replacing the P1.1 stub
   in `app/sync/conflicts.py`), and RBAC scoping by org subtree (§6.4).
   **Read plan §6 in full before starting, and expect to stop and ask the
   user about the schema** — handoff §2 requires it, and P2 is where the
   schema stops being a throwaway toy and becomes the real one.

## Decisions taken by Claude Code without asking

_(one line each, so the user can overrule)_

- Renamed the implementation plan file to `docs/IMPLEMENTATION_PLAN.md`.
- Postgres database name is lowercase `nirantharseva`.
- `PyJWT` + `argon2-cffi`, `ruff` for lint/format, stdlib JSON log
  formatter, no `app_user` table in P0 — dev users come from `DEV_USERS`.
- **ADR-001's CI grep** — enforces the no-direct-clock rule at build time.
- **`server_venv` / `client_node_modules` named volumes** in Compose — the
  bind mount for live reload otherwise wipes the built dependencies.
- **Separate `nirantharseva_test` database** — tests never touch dev data.
- **The LWW-register conflict resolution in `apply_operation()`** (P1.1) —
  the plan's toy schema has no lamport column; resolved by re-querying
  `toy_event` for the highest `(lamport, device_id)` rather than adding a
  column. Mirrored client-side in `toy_cache` for the same reason.
- **`asyncio_default_fixture_loop_scope`/`asyncio_default_test_loop_scope
  = "session"`** — required for asyncpg across the whole pytest session
  on this Windows host (and confirmed necessary in the Linux container
  too).
- Client `npm audit` flags a moderate `esbuild`/Vite dev-server-only
  vulnerability; fixing needs a Vite 6→8 breaking bump. Left as-is,
  documented, low real-world risk for solo local dev.
- **`startAutoFlush()`'s module-level guard against double-starting**
  (P1.2) — StrictMode's double effect invocation would otherwise leave
  two intervals and two listener sets running.
- **CI's new `e2e` job runs `docker compose` directly**, not uv/npm on
  the bare runner — chosen so `kill_api.sh` works identically in CI and
  locally, at the cost of a slower job (image builds + browser download
  on every run).

## Open questions for the user

- Private repo means GitHub Actions minutes are metered (2000/month
  free). The new `e2e` job downloads a Playwright browser on every run
  and builds Docker images — this is the heaviest job so far and will
  consume more of that budget than P0/P1.1's jobs did. Worth watching,
  especially once P8's load tests add more CI weight.

## Known problems and workarounds

- Host Python is 3.14.7; project pins 3.12 via `uv`. Container is
  `python:3.12-slim`. Do not build against 3.14.
- `uv` is installed via winget; if a fresh shell can not find it, use the
  full path `C:\Users\pavan\AppData\Local\Microsoft\WinGet\Links\uv.exe`.
- `run_id` shows as `""` rather than `null` in `/health` and in
  `toy`/`toy_event` rows when `RUN_ID` is set to an empty string in
  `.env` — cosmetic, not a correctness issue. Real experiment runs (P8)
  set it explicitly per run.
- **Named Docker volumes (`server_venv`, `client_node_modules`) need `-V`
  to refresh after a dependency change**, e.g.
  `docker compose up -d --build -V <service>`. Plain `--build` alone is
  not enough and fails silently (old dependencies keep being served,
  with a confusing "module not found" error at runtime, not build time).
