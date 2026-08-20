# PROGRESS

> Claude Code reads this at the start of every session and rewrites it at the
> end. It is the only memory that survives between sessions. Keep it honest —
> an optimistic PROGRESS file is worse than no PROGRESS file, because the next
> session builds on top of something that does not exist.

**Last updated:** 2026-08-20
**Last session model:** Sonnet 5 — P4.2 build (the five screens). Continued
straight from P4.1 in the same day.
**Files changed this session:** new server endpoint
`server/app/api/org_units.py` + `server/app/schemas/org_unit.py` (registered
in `server/app/main.py`), `server/tests/integration/test_org_units.py` (new);
client dependency `react-router-dom` added (`client/package.json`,
`client/package-lock.json`) — `dexie-react-hooks` was **not** approved, see
below; `client/src/db/schema.ts` (Dexie `version(3)`:
`referral_event_cache`, `org_cache`); `client/src/sync/engine.ts`
(`refreshOrgCache`, and a real bug fix in `applyPulledReferralEvent` — see
"Done this session" below); `client/src/api/client.ts` (`getToken`,
`listOrgUnits`); new: `client/src/auth/session.ts`,
`client/src/auth/RequireAuth.tsx`, `client/src/hooks/useLiveQuery.ts`,
`client/src/hooks/useSyncStatus.ts`, `client/src/domain/stateLabels.ts`,
`client/src/domain/referralActions.ts`, `client/src/domain/relativeTime.ts`,
`client/src/domain/timeline.ts`, `client/src/domain/formatAgeSex.ts`,
`client/src/routes.ts`, `client/src/styles/tokens.css`,
`client/src/vite-env.d.ts`; new components:
`DemoMarker`/`StatePill`/`SyncBand`/`WaitingToSendPill` (+ CSS Modules); new
pages: `LoginPage`, `ReferralListPage`, `CreateReferralPage`,
`ReferralDetailPage`, `IncomingReferralsPage`, `PlaceholderPage` (+ CSS
Modules); `client/src/App.tsx` (router — root `/` deliberately unchanged,
still the toy harness); `client/src/main.tsx` (`BrowserRouter`, tokens.css
import); `client/tests/p42-screens.spec.ts` (new, end-to-end);
`docs/PHASE2_OBSERVATIONS.md` (Phase 4 section extended, observations
23–29); `docs/screenshots/` (9 new PNGs, one per screen plus Screen 1's
three states).

---

## Current phase

**P4.2 of Phase 4 is done.** P4.3 (PWA, toy-model drop, fault-test port) has
not started — needs the user's go-ahead per handoff R1.

## Done this session (2026-08-20) — P4.2

Built in the order `docs/PHASE4_PLAN.md`'s P4.2 table gives, after
confirming `react-router-dom` (yes) and `dexie-react-hooks` (**no** — see
below) at the start of the session as the plan requires.

1. **Router + live query.** `react-router-dom` wraps `App.tsx`; root `/`
   deliberately keeps its exact pre-P4.2 content (the toy harness) so
   `client/tests/offline-sync.spec.ts` and `client-kill-resume.spec.ts` —
   E4's evidence — keep passing unported, per `docs/PHASE4_PLAN.md`'s own
   note that the port is P4.3's job. `dexie-react-hooks` was declined by the
   user, so `client/src/hooks/useLiveQuery.ts` is hand-rolled on top of
   Dexie core's own `liveQuery()` (already part of the `dexie` dependency —
   no new package needed for it).
2. **Design tokens** (`client/src/styles/tokens.css`) — colour, type scale,
   spacing/radius, transcribed from the design bundle's README.
3. **State → label lookup** (`client/src/domain/stateLabels.ts`) — the
   README's table, verbatim, the only place the two vocabularies meet.
4. **Screens 1, 2, 3, 5, 7**, real React/TS against the design bundle,
   reading only Dexie. Screens 4 and 6 are routed placeholders
   (`/supervisor`, `/identity-review`) naming which phase builds them for
   real.
5. **Sync band** (`client/src/components/SyncBand.tsx`) — amber/grey,
   banned-words-safe copy.
6. **Demo marker** on every real screen.
7. **Screenshots** — `docs/screenshots/`, 9 PNGs: all seven screens plus
   Screen 1's three states (synced, offline-with-pending, empty) separately.

**A real bug, not a design gap, found and fixed:** `applyPulledEvents`'
referral branch (P4.1) folded its "state so far" from `referral_cache`,
which `createReferral`/`transitionReferral` write to optimistically before
any round trip. The first real screen to create a referral and then wait
for its own confirming pull showed an empty timeline — the confirming
event's `from_state` never matched the already-optimistically-advanced
cache, so the fold silently refused to advance for *any* device confirming
its own write, referral creation included. Fixed by folding from
`referral_event_cache` (a table only the fold itself ever writes) instead of
`referral_cache` (which an optimistic UI write can move ahead of the fold at
any time) — full writeup in `docs/PHASE2_OBSERVATIONS.md`, observation 23,
including why P4.1's own fixture-based test never caught it.

**Decisions made with the user mid-session, not guessed at:**

- **Screen 3's mockup gives the ASHA buttons she doesn't have permission
  for** (`GUARDS` reserves `ARRIVED` for MO, `LOST` for SYSTEM alone). User
  chose "build only her real actions" — `CREATED → IN_TRANSIT` ("Mark as
  sent") and `BACK_REFERRED → CLOSED` ("Mark as care finished") are the only
  two buttons Screen 3 ever shows an ASHA; every other state shows a plain
  waiting line instead. Observation 25.
- **A new `GET /org_units` endpoint** — Screen 2 needs org names and nothing
  had ever exposed them to the client (the JWT carries only a bare
  `org_unit_id`). Asked before building, since it's a new API surface, not a
  client-only change. Deliberately unscoped, unlike `GET /referrals` — org
  names aren't patient data. Observation 27.

**Two more calls made alone and flagged here, not asked about separately —
both client-only or copy-only, no contract change:**

- `referral_event_cache` (Dexie `version(3)`) — Screen 3's timeline needs
  per-event history and P4.1's schema never anticipated that. Observation
  26.
- The timeline attributes events by role ("by the ASHA", "by the MO", "by
  the system"), not by name — no display name is available client-side for
  any actor, not even the one logged in (the JWT has a username, not
  `display_name`). Observation 28.

## Exit criteria status (P4.2, `docs/PHASE4_PLAN.md`)

- [x] All five screens navigable from a fresh login, reading only from
      Dexie — verified with `client/tests/p42-screens.spec.ts`, which
      toggles the network mid-test the same way the fault tests do; no
      screen blanked during the offline stretch.
- [x] Screen 1's three states (synced / offline-with-pending / empty) all
      reachable and visually distinct without a colour-only cue — three
      separate screenshots in `docs/screenshots/`
      (`screen1-asha-referral-list.png` caught it empty, on the first paint
      before the initial pull finishes — offline-first working as intended,
      not a race; `screen1-offline-with-pending.png`;
      `screen1-synced-with-new-referral.png`).
- [x] Screen 2 creates a referral for a brand-new patient name, offline, and
      it appears correctly in Screen 1 and Screen 3 after reconnect —
      `p42-screens.spec.ts`, end to end, including MO subsequently advancing
      it through the real state machine.
- [x] No banned word in any rendered screen's copy — verified by reading
      every source-level match by hand (a blind grep of the *built* JS
      bundle false-positives on internal identifiers like `syncNow` and
      `Op.payload`; see observation 29 for why that check needs a human, not
      a hit count).
- [x] Screens 4 and 6 render a placeholder, not a 404 or blank route —
      screenshotted, routed at `/supervisor` and `/identity-review`.
- [x] `tsc --noEmit` and `npm run build` clean.

## Verify this yourself

```bash
docker compose up -d --build   # if not already up
docker compose exec client npx tsc --noEmit
docker compose exec client npm run build
cd client && npx playwright test
```
Expect `5 passed` (the two P4.1 fixture tests, the two pre-existing fault
tests, and the new P4.2 end-to-end walkthrough).

To see the screens by hand: `docker compose up -d`, open
`http://localhost:5173/login`, log in as `asha_a`/`dev` (or `mo1`/`dev` for
Screen 5). `/supervisor` and `/identity-review` are reachable directly.

## Done in the P4.1 session (2026-08-20)

Built in the order `docs/PHASE4_PLAN.md`'s P4.1 table gives:

1. **Migration `0005`** — `patient.age`, `patient.sex`, `app_user.display_name`,
   all nullable, none backfilled with fake data. `0001`–`0004` untouched
   (verified with `git diff --stat`, clean).
2. **Patient resolution in `push.py`** (`_resolve_patient`, ADR-009) — tries
   `patient_id` first (pre-Phase-4 callers unchanged), falls back to
   `patient_name` (+ optional `age`/`sex`/`phone`): exact match on
   `(normalized_name, actor.org_unit_id)`, reuse if found, insert if not.
   Not fuzzy — the ADR names this as Phase 6's one call site to replace.
   `village_org_id` is the actor's own org unit, not a payload field — the
   design's Screen 2 shows "Village: yours," never a picker (observation 19,
   `docs/PHASE2_OBSERVATIONS.md`).
3. **Pull payload widened** (`pull.py`, ADR-010) — the referral branch's
   subquery now joins `patient` and `org_unit` before `LIMIT`, adding
   `patient_name`, `age`, `sex`, `reason`, `priority`, `target_org_name` to
   `payload`. Every referral event repeats the snapshot, not just
   `create_referral` — ADR-010's accepted cost.
4. **`app/seed.py`** — real `display_name`s for all five seeded users, `age`/`sex`
   for the four seeded patients.
5. **Dexie `version(2)`** (`client/src/db/schema.ts`) — `referral_cache`
   (populated), `patient_cache` (declared, empty — see observation 20,
   nothing on the wire keys a patient row yet), `outbox` gains an `entity_id`
   index.
6. **`engine.ts`** — `createReferral`/`transitionReferral` (cache + outbox
   in one Dexie transaction), and `applyPulledEvents`' new referral branch,
   which fold `advanced` the same way `app/domain/states.py`'s
   `replay_steps` does server-side: `from_state` must match the state
   already in `referral_cache`, lamport plays no part in the decision.
7. **Tests** — server: patient dedup + village-scoping + age/sex/phone
   persistence + backward-compat `patient_id` path + missing-both rejection
   (`test_patient_resolution.py`); widened pull payload on both
   `create_referral` and `transition` events (`test_pull_referral_payload.py`).
   Client (Playwright, driven through the existing `ToyPage`/`window.__engine`
   harness — no new screen, no new dependency): the Dexie transaction is
   atomic under an induced mid-transaction failure
   (`referral-cache-atomicity.spec.ts`); `applyPulledEvents` only advances
   the cache on `advanced=true`, using a fixture modeled on the demo walk's
   own conflict pair, specifically proving a *higher-lamport* losing event
   does not win (`apply-pulled-referral-events.spec.ts`).

Two things worth flagging, not silent calls — full reasoning in
`docs/PHASE2_OBSERVATIONS.md`'s new Phase 4 section:

- **ADR-009 says the payload "gains" `patient_name`; read as additive, not a
  replacement of `patient_id`** (observation 18). The other reading would
  have broken five existing test files and `scripts/demo_walk.py` — all
  still pass unmodified.
- **`patient_cache` is declared but left empty this sub-phase** (observation
  20) — `/sync/pull`'s widened payload carries a patient *snapshot*, not a
  `patient_id`, so there is no key to cache pulled patient rows under yet.
  If P4.2 needs something else from this table, that's worth a conversation
  before P4.2 starts.

## Exit criteria status (P4.1, `docs/PHASE4_PLAN.md`)

- [x] `alembic heads` is `0005`; `0001`–`0004` byte-identical to Phase 3's commit.
- [x] `python -m app.verify_replay` clean after seeding and a manual
      create+transition through the new push path (ran via `scripts/demo_walk.py`,
      which also exercises the backward-compatible `patient_id` path — same
      8-step output as Phase 3's record).
- [x] Two referrals, identical `(patient_name, village)` → one `patient` row;
      same name, different village → two rows. Both proven in
      `test_patient_resolution.py`.
- [x] A pulled `create_referral` event's payload contains `patient_name`,
      `age`, `sex`, `reason`, `priority`, `target_org_name`, all correct —
      proven in `test_pull_referral_payload.py`, plus a second test proving a
      `transition` event on the same referral repeats the snapshot.
- [x] `ruff check`, `ruff format --check`, `tsc --noEmit`, client `npm run
      build`, full server + client test suites — green, **with one exception**:
      `test_concurrent_pushes_leave_no_gap_in_the_pull_cursor`
      (`tests/integration/test_pull_cursor.py`) fails on this machine, and
      reproduces identically on commit `a4c27aa` (the committed Phase 3 state,
      before any P4.1 change) — see observation 22. Not caused by this
      session; not fixed by this session either, since it's outside P4.1's
      scope and touches sequencing code (ADR-002) nobody asked to change.
      Every other test (186 server + 4 client Playwright specs, including
      the two pre-existing fault tests) passed.
- [x] No file changed under `client/src/pages/`, `client/src/App.tsx`.

## Verify this yourself

```bash
docker compose exec db psql -U postgres -c "DROP DATABASE IF EXISTS nirantharseva_test;" -c "CREATE DATABASE nirantharseva_test;"
docker compose run --rm -e DATABASE_URL="postgresql+asyncpg://postgres:dev@db:5432/nirantharseva_test" \
  api sh -c "alembic upgrade head && python -m app.seed && ruff check . && ruff format --check . && pytest -q && python -m app.verify_replay"
```
Expect `186 passed, 1 failed` (the pre-existing failure above) unless you
also confirm it on `a4c27aa` — if it passes clean for you, that's useful
evidence this really is environment-specific and worth a closer look.

```bash
cd client && npm run typecheck && npm run build
docker compose up -d --build   # if not already up
npx playwright test
```
Expect `4 passed`.

---

## Done in the Phase 4 planning session (2026-08-19)

Read the design bundle (`docs/design_handoff_ui_screens/`, arrived and now
tracked in git — see below) against the server as it exists, and found three
places the design implies behaviour the current API cannot support:
`create_referral` requires a patient that already exists (design wants
inline creation of a new one), `/sync/pull`'s referral payload has no patient
name or reason (the client can't render a list row from it), and
`app_user.name` is both the login handle and the only display name. All
three raised with the user and decided — D13/D14/D15 in
`docs/PHASE4_PLAN.md`, ADR-009 and ADR-010 for the two with architectural
weight. Phase 4 itself splits into P4.1/P4.2/P4.3 (D16), each independently
testable, the same reasoning that split Phase 2.

Wrote `docs/PHASE4_PLAN.md` (build order, exit criteria, and traps per
sub-phase), ADR-009, ADR-010. Corrected `docs/UI_DESIGN_BRIEF.md` (it still
said "tell Claude Code whether this is filled in" — it's filled in and
confirmed) and one stale phase-number comment in
`client/src/api/client.ts`. Reverted `.gitignore`'s
`design_handoff_ui_screens/` line — that folder is now tracked; the brief
names its files by path, and an ignored folder would leave the brief pointing
at nothing for anyone else who clones the repo. If you want it un-tracked
again, say so — my reasoning is in `docs/PHASE4_PLAN.md`'s context section.

**Two dependency adds are still open, not assumed:** `react-router-dom` and
`dexie-react-hooks`, both needed at P4.2, both listed in `docs/PHASE4_PLAN.md`
waiting for a yes before that sub-phase starts.

## Done in the Phase 3 session (2026-08-19)

Built in the order `docs/PHASE3_PLAN.md`'s "Build order" table gives:

1. **`replay_steps()`** in `app/domain/states.py` (`110d2b2`) — a generator
   yielding the per-event `(advanced, state, lamport, winning_op_id)` fold.
   `replay_state()` is now a four-line wrapper over it; its signature, return
   type, and existing unit tests are unchanged.
2. **`app/sync/event_log.py`** (`2af5e2f`) — `triple()`, `fetch_triples()`,
   `replay_referral()`. `push.py` and
   `tests/property/test_referral_replay.py` both go through it now instead of
   each holding their own copy of the query and the row-to-tuple mapping.
3. **The bare `assert` in `push.py` downgraded to a structured ERROR log**
   (`27a46b0`) — carries `referral_id` and `op_id`; the write continues with
   the cached `current_state`, same as before. A new test proves a corrupted
   cache no longer 500s the request.
4. **Docstring fixes** (`de43687`) — `scoping.py` now enumerates its five
   `SUBTREE_CTE` call sites by name instead of counting them (ADR-005's
   "three" was already stale before this session; D6 and the timeline made it
   five). `replay_state`'s docstring no longer calls itself "the P3 replay
   endpoint" — it names `python -m app.verify_replay`.
5. **`app/verify_replay.py`** (`5a3b5a7`, ADR-007) — one `LEFT JOIN` scan
   over every referral and event, `REPEATABLE READ`, no advisory lock.
   `verify_all()` returns a report; the `__main__` block prints and sets the
   exit code. A zero-event referral is reported as its own violation, not
   skipped. Wired into CI's `server` job after `pytest`. Three integration
   tests, including a deliberately corrupted cache detected and restored in a
   `finally`.
6. **`GET /referrals/{id}/timeline`** (`14740e0`, ADR-008) — one query, an
   `INNER JOIN` of `referral` to `referral_event` filtered by the subtree
   predicate, so "doesn't exist," "out of scope," and "exists with zero
   events" all collapse to the same 404. `advanced` comes from
   `replay_steps`, zipped against the event rows with `strict=True`. No
   pagination — the fold is prefix-dependent, and the docstring says so.
7. **`scripts/demo_walk.py`** (`2ff889a`, D12) — drives a referral
   `CREATED → … → CLOSED` through the real `/sync/push` over HTTP, including
   a genuine two-device conflict and a stale write through the real
   `app/sync/conflicts.py`. Idempotent by I1 (`uuid5`-derived `op_id`s and
   `entity_id`), not a guard — verified manually by running it twice against
   the live stack: 8 `referral_event` rows and 1 `sync_conflict` row after
   the first run, identical counts after the second.
   `tests/integration/test_demo_walk.py` mirrors the same table against the
   ASGI test client and pins the shape in CI, including the second-run
   idempotency check.
8. **Cold-start pass**, this session, command-by-command (see below).

Two things worth flagging, not silent calls:

- **Grep-based exit criteria bit twice this phase** — `grep -rn "frm == state"
  server/app/` and `grep -rn "assert " server/app/sync/push.py` both initially
  matched twice/once-more than expected, because explanatory prose near the
  code contained the literal pattern the grep was hunting for. Both fixed by
  rewording, not by weakening the grep. Full account in
  `docs/PHASE2_OBSERVATIONS.md`'s new Phase 3 section, observation 13.
- **Step 3's own exit criteria required a new test**, which reads in tension
  with the build-order note that steps 1–4 have "no test edits other than
  rewiring `test_referral_replay.py`." Read the constraint as protecting the
  168 pre-existing tests from being altered to hide a regression, not as
  forbidding a new test for a newly introduced code path. No existing test
  was touched; one was added. Full reasoning in observation 16 of the same
  file.

## Exit criteria status

All 18 in `docs/PHASE3_PLAN.md` are `[x]`. Verify any of them yourself with
the commands in that file's "Verify Phase 3 yourself" section, or the
cold-start block below.

## Cold-start pass — run this session, command by command

```bash
docker compose down -v && docker compose up -d --build
docker compose run --rm api sh -c "alembic upgrade head && python -m app.seed"
docker compose run --rm api python scripts/demo_walk.py
docker compose run --rm api python -m app.verify_replay
```

Result: 8 steps, statuses `accepted, accepted, accepted_stale, conflict,
accepted, accepted, accepted, accepted` — matching the table in
`docs/PHASE3_PLAN.md` exactly. Verifier: `checked 3 referrals, 10 events —
I3 holds`.

```bash
TOKEN=$(curl -s -X POST localhost:8000/auth/login -H 'content-type: application/json' \
  -d '{"username":"asha_a","password":"dev"}' | python3 -c "import json,sys; print(json.load(sys.stdin)['access_token'])")
curl -s "localhost:8000/referrals/<demo-referral-id>/timeline" \
  -H "authorization: Bearer $TOKEN" | python3 -m json.tool
```

Result: 8 events, `advanced` flags `[true, true, false, false, true, true,
true, true]`, `current_state` and `replayed_state` both `CLOSED`.

```bash
docker compose run --rm \
  -e DATABASE_URL="postgresql+asyncpg://postgres:dev@db:5432/nirantharseva_test" \
  api sh -c "alembic upgrade head && python -m app.seed && ruff check . && pytest -q && python -m app.verify_replay"
```

Result: `ruff check .` clean, **180 passed**, verifier clean, `alembic heads`
still `0004`.

CI: green on all four jobs, run
[32240152464](https://github.com/pavan-pentyala/NirantharSeva/actions/runs/32240152464)
on commit `dc20b52`. Getting there took an extra fix: `e2e` hung three runs in
a row (20+ minutes each, no error) on `npx playwright install --with-deps
chromium` — apt-get blocking on an interactive `needrestart` prompt with no
TTY attached, a recent Ubuntu runner-image behaviour, unrelated to any Phase 3
code. Fixed in `dc20b52` by setting `DEBIAN_FRONTEND=noninteractive` and
`NEEDRESTART_MODE=a` on that step, plus `timeout-minutes: 15` on the job so a
future hang fails within minutes instead of running silently for hours. This
was flagged and confirmed with the user before touching `ci.yml`, since
editing the pipeline itself was outside what Phase 3's build order asked for.

## Settled decisions (carried forward)

- **Name:** NirantharSeva everywhere.
- **Python tooling:** `uv`. `uv.lock` committed.
- **UI design brief:** filled in and confirmed (`docs/UI_DESIGN_BRIEF.md`).
  The `.dc.html` design files it references have arrived and are tracked at
  `docs/design_handoff_ui_screens/` — open any of them directly in a browser.
- **Git hosting:** GitHub, private repo, GitHub Actions for CI.
- **`gh` CLI** at `C:\Program Files\GitHub CLI\gh.exe` (not on PATH).
- **`make` will not be installed** — use the `docker compose` equivalents.
- **Screenshots are not required** — do not raise this again.
- **GitHub Actions minutes are not a concern** — do not raise this again.
- **D9–D12 (Phase 3)** — settled and built. See `docs/PHASE3_PLAN.md`.
- **Phase 2 decisions D1–D8** — settled and all built. See `docs/PHASE2_PLAN.md`.
- **D13–D16 (Phase 4) and P4.2's own mid-session calls** — settled and
  built. See `docs/PHASE4_PLAN.md`, ADR-009, ADR-010, and
  `docs/PHASE2_OBSERVATIONS.md`'s Phase 4 section (observations 18–29) for
  everything decided during the build, not just at planning time.
- Review-I (per D9) is a literature review and survey, not a live demo. No
  rehearsal is budgeted or required.

## Next concrete step

**Wait for the user's explicit go-ahead before starting P4.3** (handoff R1).
P4.3 is: `vite-plugin-pwa` (`injectManifest` mode), migration `0006`
(drops `toy`/`toy_event`, removes `ToyPage.tsx` and the toy branches of
`push.py`/`pull.py`), porting `offline-sync.spec.ts` and
`client-kill-resume.spec.ts` off the toy harness onto the real referral
screens (root `/` currently still serves the toy harness precisely so this
port can happen deliberately, not by accident), and a real-phone recording.
Model for P4.3: Sonnet.

**`react-router-dom` / `dexie-react-hooks`, settled this session:**
`react-router-dom` approved and added; `dexie-react-hooks` declined —
`client/src/hooks/useLiveQuery.ts` is hand-rolled on Dexie core's own
`liveQuery()` instead (already part of the `dexie` dependency, no new
package). Do not raise either again unless P4.3 needs something the
hand-rolled hook can't do.

## Known problems and workarounds

- Host Python is 3.14.7; project pins 3.12 via `uv`. Container is
  `python:3.12-slim`. Do not build against 3.14.
- `uv` full path if a fresh shell cannot find it:
  `C:\Users\pavan\AppData\Local\Microsoft\WinGet\Links\uv.exe`.
- **Docker Desktop is at
  `C:\Users\pavan\AppData\Local\Programs\DockerDesktop\Docker Desktop.exe`**, not
  under `Program Files`. If `docker compose` reports it cannot reach the daemon,
  the daemon is not running — start it and wait about a minute.
- `run_id` shows as `""` rather than `null` in `/health` when `RUN_ID` is set to
  an empty string in `.env` — cosmetic.
- **Named Docker volumes (`server_venv`, `client_node_modules`) need `-V`** to
  refresh after a dependency change: `docker compose up -d --build -V <service>`.
- **A persistent test-database volume across many manual `pytest` runs
  eventually breaks `/sync/pull?limit=1000`-based tests** — not a code
  regression, just accumulated rows. Reset with `docker compose exec db psql
  -U postgres -c "DROP DATABASE nirantharseva_test;" -c "CREATE DATABASE
  nirantharseva_test;"` before trusting a red run that touches pull. Detail in
  `docs/PHASE2_OBSERVATIONS.md`'s Phase 3 section, observation 15.
- **Grep-based exit criteria (and CI gates) match your explanatory comments
  too, not just the code.** Two more instances this phase beyond the
  Phase 2 clock-discipline one. Detail in the same file, observation 13.
- **`test_concurrent_pushes_leave_no_gap_in_the_pull_cursor` fails on this
  Windows/Docker Desktop machine, on a fresh test database, on commits where
  GitHub Actions CI is recorded green** (Phase 4 section, observation 22).
  Toy-entity-only, unrelated to any referral/patient code. Not investigated
  further — out of scope for whatever phase is active unless a session is
  explicitly asked to look at `acquire_seq_lock`/`app/db.py`'s pooling.
- **The rest of the hard-won detail lives in `docs/PHASE2_OBSERVATIONS.md`** —
  read it, not this section, before touching `server/`. It now has a Phase 2
  section and a Phase 3 section; both are append-only and neither rewrites
  the other.
