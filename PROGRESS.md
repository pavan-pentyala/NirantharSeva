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
any of the pushes so far (no `gh` CLI in this environment).

**Phase 2 is planned and approved, not started.** The plan is
`docs/PHASE2_PLAN.md` — read it in full alongside plan §6. It is split into
**P2.1** (schema, state machine, conflict policy) and **P2.2** (auth on the
real user table, RBAC, org scoping). The four open questions in plan §6 were
put to the user and answered before planning; they are recorded as D1–D4 in
that file. **Do not re-litigate D1–D4** — they are settled.

Phase 2 will be implemented in a **new session**. Step 0 of that session is
ADR-003 and ADR-004, which are Opus work; the code is Sonnet work.

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

### Phase 2 decisions (D1–D4) — settled, do not re-litigate

Full reasoning in `docs/PHASE2_PLAN.md`. Summarised here because this file
is what a new session reads first.

- **D1 — the toy model survives until Phase 4.** Plan §6 says "throw away
  `toy`", but the toy is what Phase 1's three fault tests (= experiment E4)
  drive, and two of them are Playwright tests needing a screen that will not
  exist for referrals until P4. Toy tables and `ToyPage` stay **frozen** (no
  new work) through P2 and P3. `kill_api.sh` ports to referrals in P2.1. The
  two Playwright tests port at P4, and the toy is dropped then, in its own
  migration.
- **D2 — `user_role` has five values**, adding `SYSTEM`. Plan §6.1 defines
  four but §6.2 assigns `ESCALATED`/`LOST` to `Role.SYSTEM`; the P5 scheduler
  writes exactly those. `actor_role` is therefore never null;
  `actor_user_id` is null for system events. `app_user.role` is never
  `SYSTEM`, by convention not constraint.
- **D3 — `/sync/pull` becomes a generic envelope with a typed `payload`.**
  Sync-level fields stay flat, type-specific fields move into `payload`,
  mirroring the push `Op` contract. **This is a deliberate breaking change
  to a frozen contract**, made once at the last cheap moment; it avoids
  re-cutting again when P6 adds patient events. The client and both
  Playwright fault tests must be updated in the same commit.
- **D4 — seed data is a small hand-written fixture** (one PHC → one
  sub-centre → two villages, one user per role, ~4 patients, 2 referrals).
  Enough to prove scoping. Replaced wholesale by the P7 generator.

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
2. In a **new session**, start **P2.1** per `docs/PHASE2_PLAN.md`:
   - **Step 0, on Opus:** write ADR-003 (conflict resolution policy) and
     ADR-004 (the generic sync envelope). ADR-005 (org-subtree visibility)
     comes later, in P2.2, next to the code it governs.
   - **Then switch to Sonnet** for the code: migration `0003`,
     `app/domain/states.py`, `app/sync/conflicts.py`, the referral dispatch
     in `apply_operation`, the pull-envelope change, and the tests.
   - Stop at the end of P2.1, report, wait. Do not roll into P2.2.

   The three things most likely to go wrong in P2.1, all called out in the
   plan file: a `rejected` op that quietly appends an event anyway (assert
   row counts, not just status); `DEFAULT now()` sneaking into migration
   `0003` because plan §6.1 literally writes it (use the injected Clock);
   and breaking the two Playwright fault tests when the pull envelope
   changes shape (they are the regression check that the toy path still
   works).

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
- **Created `docs/PHASE2_PLAN.md`**, a per-phase plan document. Plan §2.2's
  directory layout does not list such a file — it assumes
  `IMPLEMENTATION_PLAN.md` plus `PROGRESS.md` are enough. Added it because
  Phase 2 is being implemented in a fresh session and the D1–D4 decisions
  need to survive in the repository, not in a chat transcript. If this
  proves to be clutter, fold it into `PROGRESS.md` and delete it.
- **Phase 2 is split into P2.1 and P2.2**, proposed rather than requested.
  Reason: §6.5's four exit criteria divide cleanly into domain correctness
  (first three) and visibility (fourth), and Phase 1's split worked well.
  Overrule this if you want it built in one session.

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
