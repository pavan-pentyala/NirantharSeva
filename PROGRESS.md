# PROGRESS

> Read at the start of every session, rewritten at the end. Its only job is
> to answer: where are we, what's next, what should I know before I start.
> The how/why already live elsewhere — ADRs for architecture decisions,
> `docs/PHASE*_PLAN.md` for what each phase built and why, git log for what
> changed and when, `docs/OBSERVATIONS.md` for hard-won lessons
> (append-only, one section per phase). Keep this file short: duplicating
> those here just gives a future session more text to read for the same
> information, at lower quality.

**Last updated:** 2026-08-24 (even later)
**Last session model:** Sonnet (pre-Phase-9 audit + fixes).

## Current phase

**Phase 7 is complete, including the cuttable P7.3 backlog.** P7.1, P7.2,
and P7.3 are all done and verified (see below).

**Phase 8 is complete — P8.1, P8.2, and P8.3 are all done and verified.**
The `experiments/` harness covers E1/E2/E3/E6, `experiments/analysis.py`
regenerates every table/figure/dashboard from `raw.csv` alone, E4's fault
matrix is filled from real recorded runs, and E5's k6 load test (a
genuinely new tool in this repo) produced real per-endpoint latency
numbers and an honest index finding. **Phase 9 (deployment, demo script,
the report) is next and needs its own go-ahead** — nothing in this repo
has started it.

**P8.2 found and fixed a real bug in already-committed P8.1 code** — a
shared RNG re-seeded per call in `experiments/resume.py`, not per cell,
silently corrupted every escalation-on/r>0 cell's closure numbers in the
*already-reported-as-done* E1 grid. Found only because E2 reused the
same function and produced impossible 100%-closure results. Fixed, and
**both E1's 45-cell grid and E2's 12-cell grid were re-run** with the fix
— `server/results/e1/` and `server/results/e2/` now hold the corrected
data, not the original P8.1 run. See observations 56–57
(`docs/OBSERVATIONS.md`) and this session's section in
`docs/Observations_for_report.md` before touching `experiments/resume.py`
or `experiments/cell.py`'s E2 loop again.

**A full pre-Phase-9 audit (2026-08-24, this session) found and fixed 15
real issues** across the whole codebase, none of them touching Phase 8's
own `server/results/` (confirmed with the user before starting — the
harness runs an entirely separate code path from the endpoints/UI the
audit fixed). Three background review agents each covered one subsystem
(server sync/domain core, server API/identity, client) in parallel, plus
a personal re-read of `experiments/`/`generator/`. Two findings were
confirmed by writing and running real pytest tests (in a since-deleted
scratch directory — never committed) before any fix was applied. Full
detail: migration `0009`, and the diff itself. Headline items:

- **`GET /referrals` crashed with a 500 on every second page** — the
  pagination cursor was a bare string bound against a `TIMESTAMPTZ`
  column; asyncpg requires a real `datetime`. Reproduced live (curl),
  confirmed by an automated test, fixed in `app/api/referrals.py`.
- **`GET /sync/pull?limit=0` could stall a client forever** — no lower
  bound on `limit`. Fixed with `Query(500, ge=1)` in `app/api/sync.py`.
  No current caller ever sent this; latent, not live.
- **Client-side lamport race**: `nextLamport()` was a non-atomic
  read-modify-write, and `CreateReferralPage`/`ReferralDetailPage` had no
  busy-state guard on their submit buttons (unlike `LoginPage`/
  `IdentityReviewPage`, which both already had one). Fixed: `nextLamport`
  now runs inside a Dexie transaction; both pages now disable their
  button while their own async call is in flight.
- **`pullAndApply()`** had no re-entrancy guard (unlike `flush()`'s own
  `flushing` flag), blindly overwrote the cursor instead of merging it,
  and had no try/catch (an unhandled promise rejection on any transient
  pull failure). All three fixed in `client/src/sync/engine.ts`.
  `applyResults()`'s per-op outbox write is now individually try/caught
  too, so one Dexie failure can't revert sibling ops flush() had already,
  correctly, marked "synced".
- **`experiments/cell.py` never checked `load()`'s own `non_accepted`
  count**, in any of the four cell functions (E1 included) — a silently
  smaller-than-generated cohort would have produced a clean exit and a
  wrong number. Now asserted after every load() call.
- **Two dead columns dropped** (`referral.sla_profile_id`,
  `escalation.escalated_to_user_id` — confirmed via grep, never read
  anywhere) **and a uniqueness constraint added**
  (`uq_sla_profile_active_state`) — migration `0009`, both confirmed with
  the user before writing it (schema changes are always ask-first).
- `app/domain/errors.py` (dead exception hierarchy, zero imports)
  deleted outright. `seed.py`'s `normalized_name` now calls the real
  `normalize()` instead of a second, weaker `.lower()`. `identity.py`'s
  merge now re-validates the candidate patient's own org scope
  (defense in depth — was safe by construction via ADR-014, now safe by
  assertion too). `make experiments EXP=<E1|E2|E3|E6>` actually runs the
  runner+analysis pair instead of printing a stale "not implemented"
  stub.
- **One thing the audit didn't find, that fixing it caused**: dropping
  the two dead columns changed physical table layout enough to flip an
  implicit, previously-undocumented tie-break in
  `app/api/dashboard.py`'s `_OVERDUE_QUERY` (two referrals escalated in
  the same sweep pass share an identical `triggered_at`, so the query's
  own `ORDER BY` was never actually deterministic — it just happened to
  return a stable order before). Fixed properly: `_BREACH_QUERY` now
  processes worst-first (`ORDER BY state_entered_at ASC`), and
  `_OVERDUE_QUERY` now breaks `triggered_at` ties via
  `referral_event.seq` — this project's own true commit-order marker
  (ADR-002) — instead of an accidental scan order. Verified deterministic
  across 5 repeated fresh-database runs before trusting it.

Verified: full server suite **269 passed**, `ruff check`/
`ruff format --check` clean, `python -m app.verify_replay` clean,
`alembic heads` is `0009` (upgrade and downgrade both checked). Client
`tsc --noEmit`, `npm run build`, and the full 11-spec Playwright suite
all green. `alembic downgrade -1` then `upgrade head` round-tripped
clean before trusting migration `0009`.

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
  `docs/OBSERVATIONS.md` Phase 5 section, observations 34–40.
- Phase 6 planning: D23–D27 decided with the user, ADR-013 (identity merge
  is REST, not a sync op) and ADR-014 (blocking with a missing phone)
  written. P6.1/P6.2 split approved.
- **P6.1** (`docs/PHASE6_PLAN.md` build order): `rapidfuzz` dependency;
  `IDENTITY_AUTO_ACCEPT`/`IDENTITY_REVIEW_FLOOR` config (D-shape of D17);
  `app/linkage/normalize.py` (NFKD + diacritic strip + whitespace
  collapse, no DB imports), `scoring.py` (`max(token_set_ratio, WRatio)`,
  no DB imports), `blocking.py` (ADR-014's predicate, with a marked seam
  for P6.2's `merged_into_id`), `pipeline.py`'s `resolve()` returning the
  four-field `Resolution` from "Contracts fixed now" (alias lookup
  compares `normalize()`d `raw_name` in Python, since
  `patient_alias.normalized_alias` doesn't exist until migration 0007);
  `generator/names.py` (15 hand-written Indian name-variant groups + 20
  filler names, no random noise) and `generator/gold_set.py` (seeded,
  reproducible — writes "existing" patient rows to `patient` and a
  separate, never-written `Query` per duplicate group, deliberately
  spanning all four blocking-relevant categories: same-village-same-phone,
  same-village-no-phone, cross-village, phone-changed); `docker-compose.yml`
  mounts `./generator:/app/generator` on `api`; `server/scripts/
  e3_draft_sweep.py` (blocks + scores each query once, classifies at six
  thresholds without re-querying, plus the naive-exact-match baseline and
  a normalize/blocking/scoring/threshold failure taxonomy). 30 new tests
  (`tests/unit/test_linkage_normalize.py`, `test_linkage_scoring.py`,
  `test_gold_set.py`; `tests/integration/test_linkage_blocking.py`,
  `test_linkage_pipeline.py`). Two real bugs found and fixed during
  verification, not just written and trusted — see observations 41–44 in
  `docs/OBSERVATIONS.md`'s new Phase 6 section.
- **P6.2** (`docs/PHASE6_PLAN.md` build order): migration `0007`
  (`patient.merged_into_id`, `patient_alias.normalized_alias` — no
  backfill needed, table was empty — the `identity_review` table +
  `uq_identity_review_open`, and a Python row-by-row `normalized_name`
  backfill for every pre-existing patient); `blocking.py` and
  `pipeline.py`'s exact/alias steps all gained `merged_into_id IS NULL`
  (the plan's exit-criteria table only named blocking explicitly — the
  exact/alias extension was my own call, flagged then, repeated here);
  `push.py::_resolve_patient` now calls `pipeline.resolve()` (ADR-009's
  one named call site) — `fuzzy_auto` writes a `patient_alias` row,
  `review_queue` creates a provisional patient AND queues an
  `identity_review` row (`_insert_identity_review`'s `ON CONFLICT ...
  WHERE status='pending' DO NOTHING` is the actual dedup gate, I5's
  sibling); `GET /identity/reviews` + `POST /identity/reviews/{id}/decide`
  (`app/api/identity.py`, ADR-013 — the conditional `UPDATE ... WHERE
  status='pending'` decide-once mechanism, 404-not-403 scoping, merge
  repoints referrals + writes an alias + sets `merged_into_id`);
  `scoping.py`'s call-site list updated (site 7). Client: Dexie v6
  (`identity_review_cache`), `client/src/sync/identityReviews.ts` (fetch +
  wholesale rewrite, no SSE — ADR-013 is plain REST), `IdentityReviewPage`
  (replaces the `PlaceholderPage`, now deleted) — offline shows an explicit
  "needs a connection" message and no queue at all, per ADR-013.
  15 new/changed server tests (`test_normalized_name_backfill.py`,
  `test_push_identity_resolution.py` — the three threshold bands through
  the real `/sync/push`, `test_identity_review_dedup.py`,
  `test_identity_api.py`) plus one new Playwright spec
  (`client/tests/identity-review.spec.ts`) verified against a real running
  browser twice — once by hand (screenshots), once as a committed,
  repeatable test. Wiring in the real fuzzy pipeline broke five
  *pre-existing* tests (two server, three client) whose "different
  person" fixtures turned out to be near-subset or near-duplicate names
  under `rapidfuzz` — all renamed, not worked around; see observations
  45–46.
- Phase 7 planning: D28–D33 decided (D28–D31 with the user, D32–D33 taken
  alone under handoff §2 and flagged in the plan for override), ADR-015
  (a cohort loads by replay through `/sync/push`) written. P7.1/P7.2
  split approved.
- **P7.1** (`docs/PHASE7_PLAN.md` build order): `pyyaml` promoted to a
  direct dependency; `configs/e1_dropout25.yaml` (the real config, §11.1's
  schema verbatim); `generator/names.py` gained `FIRST_NAMES`/
  `LAST_NAMES` (combinatorial pool for genuinely distinct people —
  `NAME_VARIANT_GROUPS`/`FILLER_NAMES` untouched, still P6.1's); `generator/
  cohort.py` (district — facilities/sub-centres/villages/ASHAs/ANMs/MOs,
  namespaced `cohort{seed}_...`/`Cohort{seed}...` so two loads never
  collide; patients — one `_Person` per distinct human, `duplicate_rate`
  giving a fraction a second record, `name_variant_rate` deciding whether
  that second record uses the group's alternate spelling or repeats the
  first exactly; a same-village name-collision guard using the real
  `app.linkage.scoring.score`, re-drawing on a hit and reporting the
  count; referrals — 1-5 per patient record, weighted, to reach D31's
  ~600 from ~200 patients); `generator/timeline.py` (the ordinary-path
  state walk with per-stage `dropout_rate`, asserted at import time to
  never touch ESCALATED, `push_delay_seconds` per D33's
  `connectivity_profile`); `generator/cli.py` (config resolution +
  defaults, writes all seven contract files, `config.resolved.yaml`
  echoes the seed actually used — I7); `server/scripts/load_cohort.py`
  (district by direct SQL exactly like `app/seed.py`'s pattern, referrals
  and events replayed through the real `/sync/push` with one login per
  generated user, `client`/`session_factory` both injectable so the same
  function serves the real CLI and `tests/integration/test_load_cohort.py`'s
  in-process ASGI client); `docker-compose.yml` mounts `./configs` and
  `./data` on `api`; CI's clock-discipline grep extended to `generator/`
  and `server/scripts`. 11 new tests (`tests/unit/test_cohort_generator.py`,
  `tests/integration/test_load_cohort.py`), suite now 256 (up from 245).
  Two pre-existing, environment-dependent gaps found and fixed while
  verifying, not just written and trusted — a `pytest`/`ruff` sys.path/
  import-sort divergence between Docker and bare `uv run` that had
  silently made every generator-importing test (including P6.1's own)
  never actually run in CI's `server` job, and a cross-file test-pollution
  bug in `GET /org_units`'s exact-set assertion — see observations 47-51
  in `docs/OBSERVATIONS.md`'s new Phase 7 section for both.
- **P7.2** (`docs/PHASE7_PLAN.md` build order): `tests/property/
  test_push_idempotency.py` (D32) — same fresh-engine-per-example pattern
  and walk strategy as `test_referral_replay.py`; Hypothesis additionally
  draws an arbitrary retry/duplication/re-interleaving pattern over the
  walk's ops (each op's first application stays in causal order, retries
  can land anywhere after), asserting the final `current_state`, replayed
  state, and — the part no single hand-picked retry can show — exactly one
  `referral_event` row per `op_id`, however many times it was resent.
  `client/tests/two-device-conflict.spec.ts` (§13.3's fifth E4 row) — two
  browser contexts as the same actor (asha_a), device 2 only ever pulling
  what device 1 created, both queuing the identical transition while
  offline; a `page.route` gate makes the server-side commit ORDER
  deterministic, and device 2's local lamport is forced (relative to
  device 1's own observed value, not a hardcoded constant) to guarantee
  ADR-003 row 5 ("conflict") rather than leaving it to chance — both fixes
  were needed only because the first draft's "natural tie" assumption
  broke under full-suite concurrent load; see observation 52.
  `tests/unit/test_fixture_name_collisions.py` — a maintained registry of
  village-scoped fixture patient names, scored pairwise with the real
  `app.linkage.scoring.score`; found and fixed two real, previously
  unnoticed collisions in the *existing* suite along the way
  (`test_pull_cursor.py`'s 20 `"Cursor Test Patient {i}"` names, several
  pairs scoring above `AUTO_ACCEPT`; `test_patient_resolution.py`'s "...
  Beta" scoring 87.8 against its own file's "... Alpha") — fixed by
  renaming, not by excluding them from the registry. The stale
  `test_permutation.py` docstring reference in `test_referral_replay.py`
  is gone. Suite now 259 (up from 256); client suite unaffected in count
  (existing specs untouched) plus the one new spec, all green across
  repeated full-suite runs. See observations 52-53 in
  `docs/OBSERVATIONS.md`'s Phase 7 section.

- **P7.3** (`docs/PHASE7_PLAN.md`'s review-hardening backlog, 2026-08-23
  session): all six A-items, all four B-items (all approved by the user —
  see "Settled decisions" below), and all six C-items.
  **A-items** (`client/src/`, no schema/contract change): A1 removed the
  four dead role chips from `LoginPage.tsx`; A2 added the resolved role +
  village to the header of Screens 1, 4, 5, 6 (Screen 1 already had it —
  the other three gained a `[session?.role, session?.username, org?.name]
  .filter(Boolean).join(" · ")` line); A3 (`CreateReferralPage.tsx`) sorts
  the facility list by name and defaults to the ASHA's nearest PHC ancestor
  via a parent-chain walk (`nearestPhcAncestor`), not `facilities[0]`; A4
  turned out to be **already built** — `SupervisorDashboardPage.tsx` already
  rendered `reason`/`asha_name` on overdue rows (P5.2's own work; the plan's
  line reference was stale) — flagged, not silently skipped; A5 moved the
  hardcoded 15000ms sync interval into `VITE_SYNC_INTERVAL_MS`
  (`client/src/sync/engine.ts`, `docker-compose.yml`, `.env.example`),
  matching `SLA_SCALE`/`SWEEP_INTERVAL_SECONDS`'s own precedent; A6 fixed
  the overdue banner's copy ("no update for X past deadline" →
  "flagged overdue X ago") rather than compute a real deadline-overshoot
  number the client has no data for.
  **B-items:** B2 seeded CHC Bishunpur and District Hospital Munger
  **above** the existing PHC Ramnagar only (`app/seed.py`) — deepens the
  ladder, no lateral choice, ADR-005 untouched, `test_org_units.py`'s exact
  name-set assertions updated for the 6-node tree. B1 added
  target_org_id validation to `_apply_create_referral`
  (`app/sync/push.py`) — a new `_target_org_is_ancestor_of_origin`
  recursive-CTE check, self-inclusive like `SUBTREE_CTE`; an invalid or
  non-ancestor target is rejected with `reason: invalid_target_org_id`
  before the patient-resolution side effects run; 3 new tests in
  `test_org_scoping.py`. B3 added migration `0008` (`app_user.phone`,
  nullable, same shape as `0005`'s `display_name`), seeded phone numbers
  for all 5 fixture users, and wired `asha_phone` through
  `dashboard.py`'s `_OVERDUE_QUERY` → `DashboardOverdueRow` →
  `dashboardStream.ts` → `DashboardOverdueCacheRow` →
  `SupervisorDashboardPage.tsx`'s overdue rows (shown under the ASHA's
  name, not a new grid column). B4 added `clearSession()`
  (`client/src/auth/session.ts`, clears the token only, never touches
  Dexie — deliberately) and a `LogoutButton` component wired into the
  header of Screens 1, 4, 5, 6.
  **C-items:** all six are now paragraphs in the new
  `docs/Observations_for_report.md` (not gitignored — committed); C5's
  three ranked offline-demo paths are also now printed by `make demo`
  itself (`Makefile`).
  Verified: `tsc --noEmit` and `npm run build` clean; full server suite
  **262 passed** (up from 259 — the 3 new B1 tests), `ruff check`/
  `ruff format --check` clean, `python -m app.verify_replay` clean;
  `alembic heads` is `0008` (B3 approved); full client Playwright suite
  (11 specs) green against the rebuilt app; `GET /org_units` checked by
  hand against a real running server — the 6-node tree resolves correctly
  end to end. Six screenshots added to `docs/screenshots/` (login with no
  chips, Screen 1/4 headers with role+village+logout, the facility
  default, the fixed banner copy).

- **Phase 8 planning** (2026-08-23, Opus, no code): `docs/PHASE8_PLAN.md`,
  **ADR-016** (one database and one OS process per experiment cell) and
  **ADR-017** (E1 reports measured detection and modelled recovery
  separately). D34–D37 answered by the user; D38 (child-process-per-cell
  mechanism) and D39 (`SLA_SCALE` pinned to 1.0 in experiments) taken alone
  and flagged for override; **D40 (the P8.1/P8.2/P8.3 split) and D41
  (deployment belongs to Phase 9, not Phase 8 — §14 governs, the phase
  map's P8 row is stale) both approved by the user.**
  Four findings the plan rests on, all verified against the repo rather
  than assumed: (1) **E1 as specified in §13.2 could not produce a non-null
  result** — escalation surfaces a stalled referral but never moves one, and
  nothing in the simulation responded to an alert, so escalation-on/off
  would have given identical closure rates by construction (ADR-017 is the
  fix); (2) **§12 and §13.1 contradict each other on cell isolation**, and
  `referral` has no `run_id` column by deliberate design (migration `0003`'s
  docstring), so §12's version cannot scope the sweep; (3) **`app/db.py`
  binds its engine at import time and `app/api/sync.py:32` passes the
  module-level `async_session_factory` straight into `handle_push`, not via
  `Depends`** — so `dependency_overrides` can redirect `/sync/pull` but not
  `/sync/push`, which is why a cell needs a process boundary rather than an
  override (ADR-016); (4) **E4 is already four-fifths built** across Phases
  1–7 — Phase 8's E4 work is evidence collection, not new tests.
  Also corrected: PROGRESS.md's old "54 loads (18 cells × 3 seeds)" budget
  did not match §13.2's specs. Real count is **63 cohort loads** (E1 45,
  E2 12, E3 3, E6 3), larger because ADR-017 grows E1 from 6 cells to 15.

- **P8.1** (`docs/PHASE8_PLAN.md` build order, 2026-08-23, Sonnet):
  `experiments/` — `grid.py` (E1's 15 cells: 3 escalation-off × dropout,
  12 escalation-on × dropout × response_rate, `IN_TRANSIT`'s dropout_rate
  is the swept stage per e1_dropout25.yaml's own precedent, everything
  else pinned; deliberately smaller cohort than P7.1's demo-scale default
  — n_patients≈22-25 per cell, flagged here since it's a wall-clock call,
  not a correctness one), `db_lifecycle.py` (raw asyncpg CREATE/DROP
  DATABASE against the maintenance connection — SQLAlchemy's own engine
  can't run either outside a transaction), `cell.py` (the child process:
  migrations via the real `alembic` CLI, `app.seed.seed()` for its
  `sla_profile` rows, the cohort generated in-process to a tempdir exactly
  like `tests/integration/test_load_cohort.py` already does, `get_clock()`
  called *after* `CLOCK_MODE=simulated`/`SIM_START` are set so the FastAPI
  app's own cached clock singleton is the one this loop steps — that
  sharing is what keeps push's `now` and the sweep's `now` on the same
  simulated timeline; ADR-016's whole reason a cell is one process), a
  stepped `load()`/`sweep()` loop with a horizon past the cohort's own
  last generated event, `resume.py` (ADR-017's `resume_escalated_referrals`
  — the probability-`r` recovery of a genuine drop-out — **plus**
  `reconcile_natural_continuations`, added after the identity check caught
  a real bug, see below), `runner.py` (parent: plans cells, spawns one
  child per (cell, seed) via `subprocess.run`, collects each child's one
  printed JSON line into `raw.csv`/`cells.resolved.yaml`/`manifest.json`,
  runs the r=0 identity check across every completed row). CI's
  clock-discipline grep, `server/pyproject.toml`'s isort first-party list,
  and `docker-compose.yml`'s `api` mount all extended to `experiments/`,
  the same treatment `generator/` got in P7.1.
  `tests/integration/test_load_cohort_upto_device_time.py` built first, as
  the plan required — six tests pinning `upto_device_time`'s exact
  boundary (`>` not `>=`) and the advancing-cutoff idempotent-resend
  pattern P8.1's own loop depends on.

  **Two real bugs found while getting E1's first real run to produce a
  trustworthy number, not just a clean exit** — see observations 54–55,
  `docs/OBSERVATIONS.md`, and the fuller report-facing writeup in
  `docs/Observations_for_report.md`'s 2026-08-23 (later still) section:
  (1) escalating a referral that was never actually going to drop out
  silently and permanently blocked its own next planned event (a stale
  `from_state` fixed at generation time no longer matched
  `current_state=ESCALATED`), which **halved every escalation-on cell's
  closure rate** until `reconcile_natural_continuations` was added — caught
  by ADR-017's own r=0 identity check on the *first* full 45-cell run, not
  by inspection; (2) PyJWT's `exp`/`iat` checks compare against the real
  system clock unconditionally, which silently breaks in both directions
  once `CLOCK_MODE=simulated` steps the same clock across real wall-clock
  "now" — fixed in `app/api/auth.py` by checking `exp` against the
  injected `Clock` by hand and disabling PyJWT's own real-time checks; two
  new unit tests in `test_auth.py` pin both directions with a real
  `SimulatedClock`. Neither is a Phase 8 API/contract change — both are
  latent defects in already-shipped code (the loader's replay shortcut,
  and `auth.py`'s clock-blind token check) that no earlier phase's tests
  exercised, flagged here per handoff §7 since they touch production code
  on my own initiative.

  **E1 ran to completion**: 45 rows in `server/results/e1/raw.csv`
  (committed — D36), `cells.resolved.yaml`, `manifest.json`. Total wall
  time **~64.5 minutes** (`manifest.json`'s `total_wall_seconds=3869.9`),
  ~75-115s/cell — comfortably faster than P7.1's own ~38s/load estimate
  would suggest for 45 loads run serially with a stepped clock on top,
  and the number P8.2/P8.3's own budget (18 more cells) should use. The
  r=0 identity check passed, both by the runner's own automated assertion
  and by an independent by-hand check of all nine dropout×seed pairs
  after the fact. A single cell (`off_d25`/seed=7) re-run separately
  reproduced its row byte-identical to the grid run's own, except
  `wall_seconds` (timing, not data).

  **Superseded by P8.2 — this run's own `resumed_and_closed`/`closure_rate`
  numbers for every escalation-on cell were wrong** (observation 56): a
  shared RNG in `experiments/resume.py`, re-seeded per call instead of per
  cell, meant most referrals in a cell got an identical fixed outcome
  instead of an independent per-referral draw. The r=0 identity check
  above is genuinely unaffected (r=0 never calls the buggy function) and
  still holds on the corrected data. `server/results/e1/raw.csv` now holds
  the re-run, not this original one — see the P8.2 entry below.

- **P8.2** (`docs/PHASE8_PLAN.md` build order, 2026-08-24, Sonnet):
  `experiments/grid.py` gained `e2_cells()`/`e3_cells()`/`e6_cells()` (D37's
  uniform `sla_profile.max_hours` override for E2, `FULL_COHORT_CONFIG`
  for E6 — both confirmed with the user, since cohort scale and E2's fixed
  `escalation_response_rate=0.5` are experiment parameters, not
  implementation details); `experiments/cell.py` gained `_run_e2_cell`,
  `_run_e3_cell`, `_run_e6_cell` (E1's own `_run_cell` untouched, kept as
  its own dispatch path in `main()` — this session's changes cannot alter
  E1's already-verified code path); `experiments/runner.py` generalized
  `RAW_COLUMNS` into `RAW_COLUMNS_BY_EXP` (one column set per experiment,
  matching PHASE8_PLAN.md's own table) and the r=0 identity check now
  gates on `args.exp == "E1"`. `experiments/analysis.py` (new): reads only
  `raw.csv`, writes `table_*.csv`, `figure_*.png` (matplotlib — new `dev`
  dependency, confirmed with the user, `server/pyproject.toml`/`uv.lock`),
  `summary.md`, and a self-contained `dashboard.html` per experiment.
  `matplotlib>=3.11.1` added via `uv add --group dev matplotlib` inside
  the `api` container (same install path as every other dependency here).

  **Two real, load-bearing bugs found and fixed before trusting any
  number from this sub-phase** — see observations 56–57,
  `docs/OBSERVATIONS.md`, and `docs/Observations_for_report.md`'s
  2026-08-24 section for the fuller report-facing writeup:
  (1) `experiments/resume.py`'s RNG bug (above) — found by E2's cells all
  reporting `closure_rate=1.0` regardless of SLA window, which is not
  what a real 50%-per-referral draw produces; confirmed against E1's own
  committed data (same fault, since P8.1). Fixed by keying each
  referral's draw off its own id, not a stream shared across referrals
  and calls. **Both E1 (45 cells) and E2 (12 cells) were re-run** after
  the fix — `server/results/e1/` and `server/results/e2/` hold the
  corrected data. (2) E2's SLA-window sweep was initially confounded by
  E1's own `LOAD_STEP_HOURS=168` (weekly push-batching lag exceeds every
  window E2 sweeps, {24,48,72,120}h) — found by running the 24h and 120h
  cells first and comparing their escalation rows directly: byte-identical.
  Fixed with a separate `E2_LOAD_STEP_HOURS=12` (confirmed with the user
  given the cost: ~90s/cell → ~18-20min/cell). Even after the fix,
  `escalations_raised`/`escalations_per_100_referrals` still barely move
  across the swept range — a real, structural property of this cohort's
  dwell-time distribution meeting the approved sweep range, not a bug;
  reported honestly rather than smoothed over.

  **Final results, all committed:**
  - **E1** (`server/results/e1/`, re-run): 45 rows, ~66 minutes,
    identity check passed. `figure_e1_closure.png` is the corrected
    headline figure — every dropout curve starts exactly on its own
    escalation-off baseline at r=0 and rises smoothly and monotonically
    through r=0.25/0.5/0.75.
  - **E2** (`server/results/e2/`): 12 rows (4 SLA windows × 3 seeds),
    ~3.7 hours (`E2_LOAD_STEP_HOURS=12`). `table_e2_frontier.csv`:
    closure_rate ~0.78-0.80 and escalations_per_100_referrals identical
    (~42.7) across all four windows — the flat-frontier finding above.
  - **E3** (`server/results/e3/`): 18 rows (1 cell × 3 seeds × 6
    thresholds), ~31 seconds total. `blocking_recall=1.0` on every seed —
    honest limitation: `generator/cohort.py`'s duplicate model (frozen
    P7.1 code) only produces same-village, same/near-spelling pairs, none
    of gold_set.py's harder cross-village/phone-changed categories, so
    this cohort-scale E3 mostly reconfirms the P6.1 draft rather than
    adding new signal — worth a sentence in Chapter 4, not a defect.
  - **E6** (`server/results/e6/`): 3 rows (1 cell × 3 seeds, full P7.1-scale
    cohort — confirmed with the user), ~56 minutes. `unresolvable_fraction`
    0.40-0.47 across three genuinely different cohorts (621/627/636
    referrals — confirms three different seeds, not one repeated),
    mean ≈0.445. `lost` is 0 in every seed — nothing in this codebase ever
    writes the `LOST` state, noted in `experiments/cell.py`'s own comment,
    not something P8.2 needed to fix.

  Verified: full server suite **269 passed** (unchanged count — no new
  server tests, this sub-phase is harness/tooling only), `ruff check`/
  `ruff format --check` clean, `python -m app.verify_replay` clean.
  `alembic heads` still `0008` (P8.2 adds no migration). No leftover
  `ns_exp_*` databases or orphaned containers after the session (checked
  by hand, `docker ps -a` and a `pg_database` query).

- **P8.3** (`docs/PHASE8_PLAN.md` build order, 2026-08-24 later, Sonnet):
  **E4** — no new tests (confirmed by Phase 8 planning: all five §13.3
  rows already had one). Ran all five against a freshly reset, migrated,
  reseeded stack and recorded what actually happened:
  `server/tests/fault/kill_api.sh` (20-op batch, API killed 50ms in,
  restarted, retried — 20 `referral_event` rows, not 40),
  `client/tests/offline-sync.spec.ts`, `client-kill-resume.spec.ts`,
  `two-device-conflict.spec.ts` (Playwright, all three), and
  `tests/integration/test_push_idempotent.py` +
  `tests/property/test_push_idempotency.py` (5 tests, the latter a
  Hypothesis-generated arbitrary retry pattern, not just a fixed ×5). All
  five passed; `server/results/e4/matrix.md` has the five-row table plus
  raw captured output (`kill_api_output.txt`, `idempotency_output.txt`,
  `playwright_output.txt`).

  **E5** — k6 added fresh: `docker-compose.yml`'s new `k6` service, gated
  behind the `--profile load` flag so it never starts with a plain
  `docker compose up` (`docker-compose.yml`'s own comment explains why);
  `experiments/k6/load.js` (login once in `setup()`, then per-iteration
  `GET /dashboard` + `GET /referrals` + `GET /sync/pull` as a
  broad-subtree MO, one `POST /sync/push create_referral` as an ASHA — the
  mix confirmed with the user). Run against a fresh dev database loaded
  with a real P7.1-scale cohort (seed 42: 220 patients, 621 referrals),
  10 VUs, 40s, twice — once with `idx_referral_open` (migration 0003,
  already shipped — not a new index) dropped, once with it restored.
  Per-endpoint p50/p95 come from `request_timing` (queried directly, per
  the plan's own design in §12 — "E5 is then a query, not a re-run"), not
  from k6's own summary, which is kept only as a cross-check
  (`k6_before_summary.json`/`k6_after_summary.json`).

  **The honest finding: the index makes no measurable difference at this
  data scale.** `EXPLAIN ANALYZE` produces the *identical* query plan
  (`Seq Scan on referral`) with the index dropped or present — Postgres's
  planner correctly prefers a sequential scan over an index lookup on a
  ~600-row table. Latency moved a few milliseconds in both directions
  across the five endpoints tested, consistent with sampling noise, not a
  causal effect. Reported as-is (`server/results/e5/summary.md`,
  `explain_open_loops_{before,after}.txt`, `table_e5_latency.csv`) — the
  same discipline P8.2's flat E2 frontier was reported with, not smoothed
  into a more flattering number. See observation 58, `docs/OBSERVATIONS.md`.

  Verified: full server suite **269 passed** (unchanged — no new server
  tests), `ruff check`/`ruff format --check` clean, `python -m
  app.verify_replay` clean, `alembic heads` still `0008` (P8.3 adds no
  migration). Client `tsc --noEmit` and `npm run build` clean. Stack fully
  reset (`docker compose down -v`) between E5 and E4 (so the k6-loaded
  cohort didn't interfere with E4's own assertions) and again at the end.

## Not done / in progress

- **Phase 9 (deployment, demo script, report) is not started.** Needs its
  own go-ahead — nothing about it was decided or built this session.
- **The real-phone airplane-mode recording is not done.** User has said
  keep it — do not drop it, do not re-propose dropping it.
- **A pre-existing, unrelated flake was observed, not fixed:**
  `client/tests/identity-review.spec.ts` (untouched this session)
  intermittently hits Playwright's 5s default timeout under a full-suite
  run with 7 parallel workers on this machine — not something P7.2 asked
  for or something these changes caused; see observation 53.

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

P6.1: every criterion in `docs/PHASE6_PLAN.md` checked against real
commands — `alembic heads` is still `0006`; `grep -rnE
'^from app\.db|^from sqlalchemy|import sqlalchemy'
app/linkage/normalize.py app/linkage/scoring.py` is empty; the same seed
(42) produces a byte-identical `ground_truth_identity.json` and identical
`e3_draft_sweep.json`, run twice in a row, diffed, not just reasoned about
— and a different seed (7) produces different patient ids, ruling out a
generator that ignores its seed; the gold set's `cross_village` (4 pairs)
and `phone_changed` (3 pairs) categories are non-empty and asserted so in
`tests/unit/test_gold_set.py`, giving `blocking_recall=0.533` on the P6.1
run — a real number below 100%, not a tautology; the sweep table over
{80,85,88,90,92,95} plus the naive exact-match baseline
(precision=recall=f1=0.000 — expected, since every query is a genuine
spelling variant of its match by construction) both write to
`results/e3_draft/` (gitignored, generated); the failure taxonomy
attributes all 7 misses to `blocking` and none to `scoring`/`threshold` on
this draft cohort, honestly — see observation 43's note on why
`normalize` stays empty too; `datetime.now()`/`time.time()` grep clean
outside `app/clock.py`, checked across `app/`, `generator/`, and
`scripts/`; `ruff check`, `ruff format --check`, full suite (235 passed,
up from 205) all green; `python -m app.verify_replay` clean after. Two
real bugs found and fixed while verifying, not just written and trusted —
`app/linkage/blocking.py`'s `:phone IS NULL` needed the same `CAST` shape
as observation 37's `SLA_SCALE` (observation 42), and `--out`/`--gold`
path arguments need `MSYS_NO_PATHCONV=1` on this Windows/Git-Bash setup or
the path silently mangles and a `--rm` container erases the evidence
(observation 41).

P6.2: every criterion in `docs/PHASE6_PLAN.md` checked against real
commands — `alembic heads` prints `0007`, `0006` unmodified; a
pre-existing (simulated pre-migration) patient row is matched by the new
exact step only after the backfill runs, not before
(`test_normalized_name_backfill.py`); the three threshold bands
(`fuzzy_auto` reuses + writes an alias, `review_queue` creates a
provisional patient + queues exactly one review + `push` still returns
`accepted`, below-floor creates a provisional patient with no review) all
verified through the real `/sync/push`, at the real
`IDENTITY_AUTO_ACCEPT=92.0`/`IDENTITY_REVIEW_FLOOR=80.0` defaults, not an
adjusted `Settings` object; two calls to `_insert_identity_review` with
the same pair produce one row, and the test asserts this against the bare
SQL mechanism directly (push.py's own call site can never trigger the
collision naturally — see that function's docstring); `decide` merge
repoints referrals, writes an alias, sets `merged_into_id`, and a second
identical POST returns the same outcome with no second alias or repoint;
`decide` keep-separate repoints nothing, and a `kept_separate` pair is not
re-queued by a later identical push (it resolves via `exact` against its
own already-created provisional patient); a merged-away patient is
provably absent from `block()`'s own candidate list afterward; an ANM
sees only her own sub-centre's pairs, a two-branch test using PHC
Ramnagar (her org's *parent*) as the "outside" branch rather than a new
fixture org, since `test_org_units.py`/`test_scoping.py` both assert the
seeded org tree's *exact* name set; `tsc --noEmit`, `npm run build`, both
suites (server 245, client 10) green; `python -m app.verify_replay` clean
on both the isolated test DB and the dev DB. Screen 6 checked against a
real running browser via a manual Playwright script (screenshots) *and*
a committed, repeatable spec — both independently confirmed the pair
renders, only disagreeing fields box, and both buttons work end to end.
No banned word (brief §6: sync, pending ops, conflict, operation, queue,
offline mode, retry, payload) in Screen 6's own copy — read by hand, and
"review queue" specifically avoided in the page title/heading for
exactly this reason.

Wiring the real fuzzy pipeline into `create_referral` broke five
pre-existing tests whose "make it a different patient" fixtures assumed
exact-match-only resolution — two server-side (`test_pull_referral_
payload.py`, `test_push_idempotent.py`, a subset-name collision scoring
literally 100.0) and three client-side Playwright specs using `` `<fixed
prefix> ${Date.now()}` `` names, which collide with their own previous run
at ~93 once two runs happen against the same persistent dev database. All
renamed, not worked around — see observations 45–46 for the mechanism and
why "unique-looking" wasn't unique enough twice over (once for the exact
name pattern, again for the boilerplate words shared across files).

P7.1: every criterion in `docs/PHASE7_PLAN.md` checked against real
commands — `python -m generator.cli --seed 42 --config
configs/e1_dropout25.yaml --out data/run_001/` emits all seven files
(patients=220, referrals=621, events=2039 on the default config); run
twice with the same seed and `diff -r` the two output directories —
byte-identical; seed 7 against the same config produces different output
(`diff -rq` shows every file differs); `config.resolved.yaml` carries
`seed: 42` and every default filled in; a full cohort loaded into a
freshly migrated, freshly seeded database through `/sync/push`
(`python scripts/load_cohort.py --cohort data/run_001/`) reports
`non_accepted=0`, and every loaded referral's `origin_org_id` equals its
own generated ASHA's `org_unit_id` (checked by query, all rows); `python
-m app.verify_replay` clean afterward (623 referrals, 2662 events
checked, including the two seeded ones); `SELECT count(*) FROM
referral_event WHERE to_state='ESCALATED'` is 0 on a freshly loaded
database; `grep -rnE 'datetime\.(now|utcnow)\(|time\.time\('
generator server/scripts` finds nothing but its own explanatory
comments (read by hand, not just counted — PROGRESS.md's own warning
about grep-based criteria), and CI's clock-discipline job now covers
both directories; `alembic heads` is still `0007`; `ruff check`, `ruff
format --check`, and the full server suite (256 passed, up from 245) are
all green, in Docker **and** on the bare host (observations 47-48 are why
both were checked, not just one).

**The measured wall-clock cohort-load time is ~38 seconds** for the
default ~620-referral, ~2660-op cohort (D31's own estimate was "~200
patients / ~600 referrals" for exactly this reason — the number Phase 8's
E1 budget is built on, per ADR-015). 54 loads (18 cells × 3 seeds) ≈ 34
minutes total — comfortably inside a working session; no need to fall
back to ADR-015's in-process or snapshot/restore alternatives.

Two things decided alone under handoff §2, flagged here so they can be
overruled:

- **`ground_truth_identity.json`'s shape adapts P6.1's `gold_set.py`
  pattern (`{seed, patients, queries}`) rather than copying it exactly.**
  `patients` lists the first occurrence of each duplicated person's
  record; `queries` lists each later occurrence, with `expected_record_id`
  pointing back — record ids, not DB patient ids, since (per ADR-015) the
  generator never writes to the database itself, so no DB patient id
  exists yet when this file is written.
- **`events.csv` has no `lamport` column** (the plan's contract table
  doesn't list one); the loader derives it as `step + 1` (create is
  lamport 1) rather than the generator inventing a second counter.

P7.2's own three items (`tests/property/test_push_idempotency.py`, the
two-device-conflict Playwright spec, the fixture-collision guard test)
are unaffected by any of the above and remain exactly as scoped in
`docs/PHASE7_PLAN.md`.

P7.2: every criterion in `docs/PHASE7_PLAN.md` checked against real
commands — `pytest tests/property/test_push_idempotency.py -v` passes (20
Hypothesis examples, each a random legal walk with a random
retry/duplication pattern layered over it); `pytest tests/unit/
test_fixture_name_collisions.py -v` passes both tests, including the one
that deliberately feeds the checker a colliding pair and asserts it
fails; `git grep -n test_permutation -- server/` is clean;
`npx playwright test two-device-conflict.spec.ts` passes reliably (run
standalone 4+ times and as part of the full 11-spec suite twice, after
fixing the ordering and lamport races — see observation 52); `alembic
heads` still `0007` (no migration); full server suite 259 passed (up from
256), `ruff check`/`ruff format --check` clean; client `tsc --noEmit` and
`npm run build` clean.

P7.3: every criterion in `docs/PHASE7_PLAN.md`'s "P7.3 exit criteria" met.

- Every A-item built (or, for A4, found already built and said so) and
  every existing suite still green — server 262/262, client 11/11
  Playwright specs, `tsc --noEmit` clean, `npm run build` clean.
- Every B-item was explicitly approved by the user before any code was
  touched (see "Settled decisions" below for the four answers) and all
  four are built: B2 (org-tree depth), B1 (target_org_id validation, 3 new
  tests), B3 (`app_user.phone`, migration `0008`), B4 (logout, token-only).
  None declined.
- Every C-item is a real paragraph in `docs/Observations_for_report.md`
  (new, not gitignored), not a TODO; C5's ranked list is also printed by
  `make demo` itself.
- `alembic heads` prints `0008` — B3 was approved, so this is the expected
  value per the plan's own exit criterion ("0007, unless B3 was approved —
  then 0008").

P8.1: every criterion in `docs/PHASE8_PLAN.md` checked against real
commands — `MSYS_NO_PATHCONV=1 docker compose run --rm api python -m
experiments.runner --exp E1 --out /app/results/e1/` writes all **45 rows**
to `raw.csv`; re-running one cell (`off_d25`/seed=7) with `--cell --seeds`
reproduces every substantive column byte-identical to the grid run's own
row (only `wall_seconds` differs, which is timing, not data); the r=0
identity check — escalation-on with `response_rate=0` must equal
escalation-off's `closure_rate` at the same dropout level and seed — holds
across all nine (dropout, seed) pairs, checked twice: once by the runner's
own automated assertion (printed `Identity check passed`), once
independently by reading the nine row-pairs out of `raw.csv` by eye after
the run. `alembic heads` is `0008` (unchanged from P7.3 — P8.1 adds no
migration). `tests/integration/test_load_cohort_upto_device_time.py`'s six
boundary tests pass. Full server suite **269 passed** (up from 262),
`ruff check`/`ruff format --check` clean, `python -m app.verify_replay`
clean. **git_sha is "unknown" in every row** — `.git` isn't mounted into
the `api` container (only `server/`, `generator/`, `experiments/`,
`configs/`, `data/` are), so `git rev-parse HEAD` fails inside it; a
known, accepted gap (`_git_sha()`'s own docstring), not something P8.2/P8.3
need to fix unless a report figure actually needs real provenance.

**P8.1's original numbers above are superseded** — see the P8.2 entry in
"Done" and observation 56: the r=0 identity check itself still holds
(unaffected by the bug), but the response-rate-swept closure numbers it
sat next to were wrong until this session's fix and re-run.

P8.2: every criterion in `docs/PHASE8_PLAN.md`'s D40 table checked against
real commands — `server/results/{e2,e3,e6}/raw.csv` exist with the exact
row counts D40/PHASE8_PLAN.md's "Cell counts" table specifies (E2: 12,
E3: 18, E6: 3); `MSYS_NO_PATHCONV=1 docker compose run --rm api python -m
experiments.analysis --exp E2 --in /app/results/e2/ --out
/app/results/e2/` (and the same for E1/E3/E6) regenerates
`table_*.csv`/`figure_*.png`/`summary.md`/`dashboard.html` reading
**only** `raw.csv` — checked by running it after the source databases
were already dropped (ADR-016's per-cell lifecycle drops each database
before the next cell starts; nothing in `analysis.py` imports `app.*` or
opens a database connection at all, checked by reading the file, not just
by it happening to work). `alembic heads` is `0008` (P8.2 adds no
migration). Full server suite **269 passed** (unchanged — no new server
tests; P8.2 is a harness/tooling sub-phase), `ruff check`/
`ruff format --check` clean across `experiments/` and the whole server
tree, `python -m app.verify_replay` clean. No `ns_exp_*` database or
orphaned `docker ps -a` entry survived the session.

P8.3: every criterion in `docs/PHASE8_PLAN.md`'s D40 table checked against
real commands — `server/results/e4/matrix.md` has all five §13.3 rows,
each citing a real, dated run (not "should pass"); raw output for each is
committed alongside (`kill_api_output.txt`, `idempotency_output.txt`,
`playwright_output.txt`). `server/results/e5/table_e5_latency.csv` has
p50/p95 per endpoint in both index states, sourced from `request_timing`
directly; `explain_open_loops_before.txt`/`_after.txt` hold the real
`EXPLAIN ANALYZE` output for both states (byte-for-byte identical query
plan — the honest finding, not a shortfall in what was measured).
`alembic heads` is `0008` (P8.3 adds no migration — `idx_referral_open`
was dropped/recreated by hand on the running dev database for the
measurement, never via a migration). Full server suite **269 passed**
(unchanged), `ruff check`/`ruff format --check` clean, `python -m
app.verify_replay` clean, client `tsc --noEmit`/`npm run build` clean. No
leftover `ns_exp_*` database, no orphaned container, `docker compose down
-v` run clean at the end (checked by hand).

## Open item for the user

**The real-phone clip** (plan §8.5, the Review-III fallback) is still
owed, and is being kept. Needs a physical Android phone: open the app, add
to home screen, airplane mode, create a referral, restore signal, record it
syncing. Ten minutes; nothing in this repo can do it. Note where the file
lands here once recorded — it is deliberately not committed (large binary).

## Next concrete step

**Phase 8 is done — P8.1, P8.2, P8.3 all complete.** Next is **Phase 9**
(deployment, demo script, the report itself — docs/IMPLEMENTATION_PLAN.md
§14). Wait for the user's go-ahead before starting it; nothing about it
has been decided yet, including whether Opus should lead the report
chapters (design/writing work, not code — handoff R2 would say Opus, not
Sonnet).

To verify P8.3 yourself:

```bash
docker compose down -v && docker compose up -d --build
docker compose run --rm api sh -c "alembic upgrade head && python -m app.seed"
bash server/tests/fault/kill_api.sh
```
Expect `PASS: 20 ops landed exactly once...` at the end. This kills the
real `api` container and restarts it — expected, that is the test.

```bash
docker compose exec db psql -U postgres -c "DROP DATABASE IF EXISTS nirantharseva_test;" -c "CREATE DATABASE nirantharseva_test;"
docker compose run --rm -e DATABASE_URL="postgresql+asyncpg://postgres:dev@db:5432/nirantharseva_test" \
  api sh -c "alembic upgrade head && python -m app.seed && pytest -v tests/integration/test_push_idempotent.py tests/property/test_push_idempotency.py"
```
Expect 5 passed.

E5 is not worth re-running casually — it needs a full cohort load, two
API container restarts, and two 40s k6 runs (~10 minutes total, plus the
`idx_referral_open` drop/recreate). If you do, `docker-compose.yml`'s own
comment on the `k6` service has the exact invocation
(`docker compose --profile load run --rm k6 run /scripts/load.js
--summary-export=/results/...`) — `MSYS_NO_PATHCONV=1` is required, same
as every other `docker compose run` passing a container path. `docker
compose down -v` afterward; this loads real referrals into the dev
database and drops a real index, temporarily, on it.

To verify P8.2 yourself:

```bash
docker compose up -d --build
MSYS_NO_PATHCONV=1 docker compose run --rm api python -m experiments.runner --exp E3 --out /app/results/e3_check/
MSYS_NO_PATHCONV=1 docker compose run --rm api python -m experiments.analysis --exp E3 --in /app/results/e3_check/ --out /app/results/e3_check/
```
Expect: 3 cells x 6 rows = 18 rows in `raw.csv` (~30s total — E3 is the
cheap one, a single load pass per seed, no clock stepping), then
`table_e3_thresholds.csv`, `table_e3_summary.csv`, `figure_e3_prf.png`,
`summary.md`, `dashboard.html` all appear in the same directory. Compare
against the committed `server/results/e3/` — every column but
`wall_seconds`/`git_sha` should match. Delete `server/results/e3_check/`
afterward.

**E2 and E6 are not worth re-verifying casually — they now take ~3.7
hours and ~56 minutes respectively** (E2_LOAD_STEP_HOURS=12 for E2;
E6's full P7.1-scale cohort for E6). If you do:
```bash
MSYS_NO_PATHCONV=1 docker compose run --rm api python -m experiments.runner --exp E2 --out /app/results/e2_check/ --cell sla24 --seeds 42
```
One cell only, ~18-20 minutes, is enough to sanity-check the harness
still works without re-running the whole grid.

**Before touching `experiments/resume.py` again:** read observation 56
(`docs/OBSERVATIONS.md`) first. The bug was a shared RNG re-seeded per
call instead of per cell — any change to how `resume_escalated_referrals`
or `reconcile_natural_continuations` constructs its `Random` needs to
preserve "one independent stream per referral," not just "looks seeded."

To verify P8.1 yourself:

```bash
docker compose up -d --build
docker compose exec db psql -U postgres -c "DROP DATABASE IF EXISTS nirantharseva_test;" -c "CREATE DATABASE nirantharseva_test;"
docker compose run --rm -e DATABASE_URL="postgresql+asyncpg://postgres:dev@db:5432/nirantharseva_test" \
  api sh -c "alembic upgrade head && python -m app.seed && pytest -q tests/integration/test_load_cohort_upto_device_time.py"
# expect 6 passed

MSYS_NO_PATHCONV=1 docker compose run --rm api python -m experiments.runner --exp E1 --out /app/results/e1_check/
```
Expect: 45 lines logged (one per cell, each ~75-115s), `Identity check
passed` printed near the end, `45 rows written to
/app/results/e1_check/raw.csv`. **This takes about an hour** — each cell
is its own fresh database and its own child process (ADR-016), and there
is no way to shrink that without shrinking the grid itself. Compare
`server/results/e1_check/raw.csv` against the committed
`server/results/e1/raw.csv` — every column but `wall_seconds` should
match row for row. Delete `server/results/e1_check/` afterward (scratch,
not the committed run). `docker compose down -v` when done — each cell
creates and drops its own `ns_exp_e1_*` database, but check `docker ps -a`
first if the run was interrupted (same orphan-container risk noted below
for the scheduler).

To verify P7.3 yourself:

```bash
docker compose up -d --build
docker compose run --rm api sh -c "alembic upgrade head && python -m app.seed"
docker compose run --rm api alembic heads                     # expect 0008 (head)
docker compose exec client npx tsc --noEmit && docker compose exec client npm run build

docker compose exec db psql -U postgres -c "DROP DATABASE IF EXISTS nirantharseva_test;" -c "CREATE DATABASE nirantharseva_test;"
docker compose run --rm -e DATABASE_URL="postgresql+asyncpg://postgres:dev@db:5432/nirantharseva_test" \
  api sh -c "alembic upgrade head && python -m app.seed && ruff check . && ruff format --check . && pytest -q && python -m app.verify_replay"
# expect 262 passed, clean

TOKEN=$(curl -s -X POST http://localhost:8000/auth/login -H "content-type: application/json" \
  -d '{"username":"asha_a","password":"dev"}' | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
curl -s http://localhost:8000/org_units -H "authorization: Bearer $TOKEN" | python -m json.tool
# expect 6 org units: District Hospital Munger -> CHC Bishunpur -> PHC Ramnagar
#   -> Sub-centre Kotwali -> Village A / Village B
```
Then log in as `asha_a`/`dev` at `http://localhost:5173/login` by hand —
no role chips on the login screen, the header shows `ASHA` and a
`Log out` link, and `/referrals/new`'s "Sending to" defaults to
"PHC Ramnagar". `docker compose down -v` afterward.

To verify P7.1 yourself:

```bash
docker compose up -d --build
docker compose run --rm api sh -c "alembic upgrade head && python -m app.seed"
MSYS_NO_PATHCONV=1 docker compose run --rm api \
  python -m generator.cli --seed 42 --config configs/e1_dropout25.yaml --out /app/data/run_001/
MSYS_NO_PATHCONV=1 docker compose run --rm api \
  python -m generator.cli --seed 42 --config configs/e1_dropout25.yaml --out /app/data/run_002/
diff -r data/run_001 data/run_002                    # must be empty — I7
MSYS_NO_PATHCONV=1 docker compose run --rm api python scripts/load_cohort.py --cohort /app/data/run_001/
docker compose run --rm api python -m app.verify_replay
docker compose exec -T db psql -U postgres -d nirantharseva \
  -c "SELECT count(*) FROM referral_event WHERE to_state='ESCALATED';"   # must be 0
docker compose down -v   # this loaded real rows into the dev db — clean up after
```
Expect: both CLI runs report identical counts, `diff` empty, the load
reports `non_accepted=0`, `verify_replay` clean, escalated count 0.

To verify P7.2 yourself:

```bash
docker compose exec db psql -U postgres -c "DROP DATABASE IF EXISTS nirantharseva_test;" -c "CREATE DATABASE nirantharseva_test;"
docker compose run --rm -e DATABASE_URL="postgresql+asyncpg://postgres:dev@db:5432/nirantharseva_test" \
  api sh -c "alembic upgrade head && python -m app.seed && pytest -v tests/property/test_push_idempotency.py tests/unit/test_fixture_name_collisions.py"
git grep -n test_permutation -- server/   # must be empty

docker compose up -d --build
docker compose run --rm api sh -c "alembic upgrade head && python -m app.seed"
cd client && npx playwright test two-device-conflict.spec.ts
```
Expect 3 server tests passed, the grep empty, and the Playwright spec
green. **Run the full client suite (`npx playwright test`, no filter) at
least twice** if you want confidence this specific spec holds under
concurrent load, not just in isolation — see observation 52 for why that
distinction mattered here. `docker compose down -v` afterward; the server
run above wrote to the isolated test DB (safe to just drop it again), but
the Playwright runs write real rows to the dev DB.

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
cd client && npx playwright test                     # expect 11 passed, ~2 min (see below)
```

Two of those 11 tests need a demo-scale scheduler running first, or they'll
sit at their real-SLA pace instead of failing fast — start one before the
`npx playwright test` above:

```bash
docker compose run --rm -d --name demo-scheduler -e SLA_SCALE=0.0004 -e SWEEP_INTERVAL_SECONDS=5 scheduler
# ... run the tests ...
docker stop demo-scheduler   # started with --rm, so this also removes it
```

If the SSE-dependent dashboard test times out waiting for a live breach
despite the scheduler logging that it escalated something, the API
container's dedicated `LISTEN` connection is probably stale from an
earlier `docker compose down -v`/`up` cycle in the same long session —
`docker compose restart api` fixed this instantly and reliably when it
happened this session. `identity-review.spec.ts` has also been seen to
time out intermittently (Playwright's 5s default) under a full-suite run
with many parallel workers on this machine, unrelated to the above and
not chased further — see observation 53.

Server (`alembic heads` should print `0008`):

```bash
docker compose exec db psql -U postgres -c "DROP DATABASE IF EXISTS nirantharseva_test;" -c "CREATE DATABASE nirantharseva_test;"
docker compose run --rm -e DATABASE_URL="postgresql+asyncpg://postgres:dev@db:5432/nirantharseva_test" \
  api sh -c "alembic upgrade head && python -m app.seed && ruff check . && ruff format --check . && pytest -q && python -m app.verify_replay"
```
Expect `262 passed`, clean.

Identity resolution draft sweep (Phase 6's headline number), against the
same isolated test DB set up above — **on Windows/Git-Bash,
`MSYS_NO_PATHCONV=1` is required on both commands below or the `--out`/
`--gold` path silently mangles (observation 41)**:

```bash
MSYS_NO_PATHCONV=1 docker compose run --rm -e DATABASE_URL="postgresql+asyncpg://postgres:dev@db:5432/nirantharseva_test" \
  api python -m generator.gold_set --seed 42 --out /app/results/e3_draft/
MSYS_NO_PATHCONV=1 docker compose run --rm -e DATABASE_URL="postgresql+asyncpg://postgres:dev@db:5432/nirantharseva_test" \
  api python scripts/e3_draft_sweep.py --gold /app/results/e3_draft/
```
Expect `blocking_recall=0.533`, a naive-baseline precision/recall/f1 of
`0.000` (every gold-set query is a genuine spelling variant, so exact
match should find nothing), and a threshold-sweep table with precision
reaching `1.000` by threshold 85. Run both commands twice with the same
`--seed` and diff `server/results/e3_draft/*.json` — byte-identical, or
the numbers are not reproducible (P6.1 exit criterion). Writes to
`server/results/e3_draft/` via the bind mount — gitignored, safe to
delete and regenerate.

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
`docs/OBSERVATIONS.md` are two separate incidents this session of a
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
`asha_a`/`dev`, `mo1`/`dev` for Screen 5, `supervisor1`/`dev` for Screen 4
(`/supervisor`), or `anm1`/`dev` for Screen 6 (`/identity-review`) — every
screen is real now; no placeholders remain.

Screen 6 needs a pending pair to show anything. To make one by hand:
push a `create_referral` as `asha_a` naming a close misspelling of an
existing Village A patient — `"Lakshmy Devi"` against the seeded
`"Lakshmi Devi"` scores 91.67, just inside the review band under the
default 92/80 thresholds:

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login -H "content-type: application/json" \
  -d '{"username":"asha_a","password":"dev"}' | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
curl -s -X POST http://localhost:8000/sync/push -H "content-type: application/json" \
  -H "authorization: Bearer $TOKEN" -d "{\"device_id\":\"demo\",\"ops\":[{\"op_id\":\"$(python -c 'import uuid;print(uuid.uuid4())')\",\"entity\":\"referral\",\"entity_id\":\"$(python -c 'import uuid;print(uuid.uuid4())')\",\"operation\":\"create_referral\",\"payload\":{\"patient_name\":\"Lakshmy Devi\",\"reason\":\"demo\",\"priority\":\"routine\"},\"lamport\":1,\"device_time\":\"2026-08-21T09:00:00Z\"}]}"
```
Then log in as `anm1`/`dev`. **This writes real rows to the dev
database** — the patient, its referral, and the `identity_review` pair
survive until deleted, and `client/tests/identity-review.spec.ts` decides
every pending pair it finds as a precondition, so leaving one lying
around changes what that spec exercises. Clean up by deleting from
`identity_review`, `patient_alias`, `referral_event`, `referral`, then
`patient`, in that order (FK dependencies), and re-run
`docker compose exec api python -m app.verify_replay` afterward.

## Settled decisions (do not re-ask)

- Name: NirantharSeva everywhere.
- Python: `uv`, lockfile committed. Node: `npm`, lockfile committed.
- Git hosting: GitHub, private repo, GitHub Actions CI.
- `make` is not installed — use the `docker compose` equivalents (Makefile
  documents the mapping).
- `react-router-dom`: yes. `dexie-react-hooks`: no. `vite-plugin-pwa`: yes.
- GitHub Actions minutes: not a concern.
- Screenshots: either way is fine (user's answer) — `docs/screenshots/`
  currently holds one per screen (all six real now) plus the PWA
  offline-reload proof.
- Review-I is a literature review/survey, not a live demo — no rehearsal
  needed.
- The real-phone offline clip stays on the list. Do not propose dropping
  it again.
- All decisions D1–D33: settled — see the relevant `PHASE*_PLAN.md` / ADR.
  Phase 5's four (SSE query-token auth, LISTEN/NOTIFY, `SLA_SCALE`,
  P5.1/P5.2 split) and Phase 6's five (gold set sliced forward from the
  Phase 7 generator, P6.1/P6.2 split, identity merge over REST rather than
  the outbox, no "not sure" third button on Screen 6, blocking with a
  missing phone) were answered 2026-08-20; do not re-ask them.
- Phase 7's four (D28 cohort loads by replay through `/sync/push` —
  ADR-015; D29 the generator builds its own district; D30 P7.1/P7.2
  split; D31 default cohort ~200 patients / ~600 referrals) were answered
  2026-08-21. D32 (the property layer proves idempotency-under-retry, not
  permutation invariance — the latter is false by design under ADR-003)
  and D33 (`connectivity_profile` = device→server delay distribution)
  were taken alone under handoff §2 and are flagged in
  `docs/PHASE7_PLAN.md` for override.
- P7.3's four B-items were all answered 2026-08-23, all approved, none
  declined: **B2** — seed CHC Bishunpur + District Hospital Munger *above*
  PHC Ramnagar only (the plan's own recommendation; no second PHC, no
  lateral referral, ADR-005 untouched). **B1** — build target_org_id
  validation, ancestor-of-origin shape (follows from B2). **B3** — add
  `app_user.phone`, migration `0008`. **B4** — add logout, token-only,
  Dexie untouched. Do not re-ask any of these.
- Phase 8's four (D34 E1 splits into measured detection + modelled recovery
  swept over `escalation_response_rate` — ADR-017; D35 one database and one
  OS process per cell — ADR-016; D36 `results/` is committed minus bulk
  per-request dumps; D37 E2's SLA sweep sets every `sla_profile.max_hours`
  uniformly to the cell value) were answered 2026-08-23. D38 (a cell runs in
  a child process) and D39 (`SLA_SCALE` pinned to `1.0` in every experiment
  process) were taken alone under handoff §2 and are flagged in
  `docs/PHASE8_PLAN.md` for override. **D40** (split into P8.1/P8.2/P8.3)
  and **D41** (deployment stays in Phase 9 — §14 governs, the phase map's
  P8 row is stale; Phase 8 ships no deployment) were also answered
  2026-08-23. No Phase 8 decision is open.
- **New standing instruction (2026-08-23, applies going forward):**
  `docs/Observations_for_report.md` (new file, not gitignored) collects
  results/framing/discussion material for the final written report, one
  dated section per session. Update it at the end of every session
  alongside `PROGRESS.md`, whenever the session produced anything
  report-worthy — this is now in `CLAUDE.md`'s "End of every session"
  section too.
- **P8.2's three decisions, all answered 2026-08-24, do not re-ask:**
  E2's fixed `escalation_response_rate=0.5` (grid.py's `E2_RESPONSE_RATE`
  — the median of E1's own swept {0,0.25,0.5,0.75}, chosen for direct
  comparability with E1's r=0.5 cells); E6 uses the full P7.1-scale
  cohort (`FULL_COHORT_CONFIG`, ~200 patients/~620 referrals), not E1/E2's
  smaller grid-scale one, despite the wall-clock cost (~56 min for 3
  seeds) — "full-cohort run" (§13.2) was read literally; `matplotlib`
  added as a new `dev`-group dependency for `experiments/analysis.py`'s
  figures, confirmed before it was added. Also answered: `E2_LOAD_STEP_HOURS
  =12` for E2 specifically (not the shared `LOAD_STEP_HOURS=168`), after
  the confound in observation 57 was found and measured — the ~18-20min/
  cell cost was shown before, not after, committing to the full grid.
- **P8.3's two decisions, both answered 2026-08-24 (later), do not
  re-ask:** E5's before/after index comparison drops/recreates
  `idx_referral_open` by hand on a scratch-loaded dev database (never a
  migration, never a permanent schema change) rather than inventing a
  second index to compare; the k6 load mix is `GET /dashboard` + `GET
  /referrals` + `GET /sync/pull` (broad-subtree MO login) + `POST
  /sync/push create_referral` (ASHA login), 10 VUs, 40s per run — a
  representative slice, not a stress test, chosen over a sync-path-only
  script because the dashboard/referrals reads are what the index
  question is actually about.
- **Pre-Phase-9 audit's two schema decisions, both answered 2026-08-24
  (even later), do not re-ask:** drop `referral.sla_profile_id` and
  `escalation.escalated_to_user_id` (both confirmed dead by grep) via a
  new migration rather than leaving them in the schema; add
  `uq_sla_profile_active_state` (a partial unique index on
  `sla_profile(state) WHERE active`) as a safety net in the same
  migration, even though nothing currently violates it. Both landed as
  migration `0009`.

## Known problems and workarounds

- **A `Random(seed_string)` built fresh inside a function that gets
  called many times per cell gives every call the same first draw, not
  an independent one per referral.** `experiments/resume.py`'s
  `resume_escalated_referrals` did exactly this — silently corrupted
  every escalation-on/r>0 cell in P8.1's *committed* E1 run, invisible to
  the r=0 identity check (which never calls this function at all). Fixed
  by keying the RNG off the referral's own id, constructed inside the
  per-referral loop, not once per call. Before changing anything in this
  file that constructs a `Random`, check: does this seed string vary per
  independent decision, or could two different draws share it? See
  observation 56, `docs/OBSERVATIONS.md`.
- **A harness setting tuned for one experiment's wall-clock budget can
  silently neutralize a different experiment's swept parameter.**
  `LOAD_STEP_HOURS=168` (P8.1, tuned for E1) is wider than every SLA
  window E2 sweeps ({24,48,72,120}h) — push-batching lag alone breached
  every window regardless of its value, until `E2_LOAD_STEP_HOURS=12`
  fixed it (at a real cost: ~90s/cell → ~18-20min/cell). Before adding a
  new sweep to any future experiment, ask whether any existing constant
  in `experiments/grid.py` sits inside — not below — the new sweep's own
  range. See observation 57, `docs/OBSERVATIONS.md`.
- **`experiments.runner`'s `--out` needs `MSYS_NO_PATHCONV=1` too** — same
  Git-Bash path-mangling as `--out`/`--gold` elsewhere (observation 41),
  and it bit this exact command this session: a run without the prefix
  exits 0, prints real-looking progress, and silently writes `raw.csv`
  outside the repo entirely (`C:\Program Files\Git\app\results\...` on
  this machine) instead of `server/results/e1/`. Always check the row
  count lands in `server/results/<exp>/raw.csv` after a run, not just that
  the command exited cleanly.
- **Escalating a referral does not stop it from progressing on its own —
  a loader that mechanically replays a fixed `from_state` will silently
  and permanently block any referral that gets escalated without actually
  dropping out.** Cost P8.1's first full E1 run a wrong headline number
  (every escalation-on cell closing roughly half of what escalation-off
  closed) before ADR-017's r=0 identity check caught it. See observation
  54, `docs/OBSERVATIONS.md`, before touching `experiments/resume.py` or
  `experiments/cell.py`'s sweep loop again.
- **PyJWT's `exp`/`iat` checks compare against the real system clock,
  unconditionally — under `CLOCK_MODE=simulated`, a token looks expired
  before the simulated clock reaches real "now," and looks issued in the
  future after it passes real "now."** `app/api/auth.py` now checks `exp`
  against the injected `Clock` by hand instead. See observation 55,
  `docs/OBSERVATIONS.md`, before touching token validation again — this
  only shows up under a simulated clock that runs long enough to cross
  real wall-clock time, which no phase before P8.1 ever did.
- **`server/pyproject.toml` needs `pythonpath = [".."]` (pytest ini) and
  `[tool.ruff.lint.isort] known-first-party = ["app", "generator"]`, or
  `generator`-importing code behaves differently inside Docker vs. on the
  bare host** — Docker's `./generator:/app/generator` bind mount makes
  `generator/` a real child of `server/`'s own root; on the bare host
  (CI's `server` job, or any local `uv run pytest`/`uv run ruff` from
  `server/`) it is a sibling directory instead, and both `pytest`'s
  import resolution and `ruff`'s isort category detection default to
  different answers for the two layouts. Found while adding P7.1's own
  generator-importing tests — every prior generator-importing test
  (including P6.1's `test_gold_set.py`) had apparently only ever been run
  through `docker compose run`, never through CI's bare job or a bare
  local run. See observations 47-48, `docs/OBSERVATIONS.md`.
- **`server_lamport` (`app/sync/push.py`) is a GLOBAL max over the entire
  `referral_event` table, not scoped to a referral or an org — any test
  or script that assumes two devices' local lamport counters will
  naturally agree (or naturally differ in a predictable way) is trusting
  something that only holds in isolation, and on a persistent dev
  database it decays further with every earlier run of the same test.**
  `client/tests/two-device-conflict.spec.ts` hit this twice — once
  needing a request-ordering fix (a `page.route` gate), once needing the
  forced lamport to be computed relative to a live observed value instead
  of a hardcoded constant. See observation 52.
- **`GET /org_units` returns the exact global org_unit table, unscoped by
  design (P4.2) — any test that creates a real org_unit row and does not
  delete it afterward breaks `tests/integration/test_org_units.py`'s
  exact-set assertion, even if its org names never collide with the
  seeded ones.** `tests/integration/test_load_cohort.py` hit this and now
  cleans up every row it creates (org_unit, app_user, patient, referral,
  referral_event, etc., in FK-respecting order) in a `finally` block —
  copy that pattern for any future test that loads a real cohort or
  otherwise creates org units. See observation 49.
- **Any test that creates a patient needs a name sharing NO words with
  any other test's patient name, in any file, server or client — and a
  random differentiator, never `Date.now()`.** Since P6.2,
  `create_referral` resolves patients through the real fuzzy pipeline, so
  `rapidfuzz` decides whether two fixtures are "the same person":
  `token_set_ratio` scores a subset name against its superset as exactly
  100 (`"X Patient"` vs `"X Patient Two"`), two millisecond timestamps
  inside an otherwise identical name score ~93, and two words of shared
  boilerplate ("Test Patient") score 75–89 — the last one is below
  `AUTO_ACCEPT` so it doesn't corrupt identity, but it queues a junk
  `identity_review` pair that clutters a live demo of Screen 6. Use
  `crypto.randomUUID().slice(0, 8)` (client) or a distinct phrase
  (server), and scan any new name against the existing ones with
  `app.linkage.scoring.score` before committing it. Observations 44–46;
  this cost five broken pre-existing tests in P6.2, in two separate
  rounds.
- **Git Bash on Windows rewrites `/app/...`-style path arguments before
  `docker compose run`/`exec` ever sees them** — a `--out`/`--gold` value
  meant for the container's own filesystem gets reinterpreted as a host
  path, the command still exits 0, and a `--rm` container erases the only
  copy of whatever it wrote to the wrong place (observation 41). Prefix
  any such command with `MSYS_NO_PATHCONV=1`.
  **Hit again with k6 (P8.3)** — `docker compose --profile load run --rm
  k6 run /scripts/load.js` without the prefix rewrote `/scripts/load.js`
  to a literal `C:/Program Files/Git/scripts/load.js` and failed with "the
  moduleSpecifier ... couldn't be found on local disk," not a silent
  wrong-location write this time, but the same root cause.
- **`asyncpg.exceptions.AmbiguousParameterError` on a bind parameter whose
  first use in a query is `:param IS NULL`** — asyncpg's prepared-statement
  protocol has no type to infer from a NULL comparison. Same root cause as
  the `SLA_SCALE` entry below (observation 37), but this one raises
  instead of silently corrupting; fix is the same shape, `CAST(:param AS
  <type>)` on first use. Hit in `app/linkage/blocking.py`'s phone
  predicate (observation 42) — worth checking for in any future query with
  a nullable bind parameter.
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
  `docs/OBSERVATIONS.md`. Check with `docker ps -a` (not `docker
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
- **The rest of the hard-won detail lives in `docs/OBSERVATIONS.md`**
  — read it before touching `server/` or `client/src/sync/`. Append-only,
  one section per phase, never rewritten.
