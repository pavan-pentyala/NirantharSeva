# PROGRESS

> Read at the start of every session, rewritten at the end. Its only job is
> to answer: where are we, what's next, what should I know before I start.
> The how/why already live elsewhere — ADRs for architecture decisions,
> `docs/PHASE*_PLAN.md` for what each phase built and why, git log for what
> changed and when, `docs/PHASE2_OBSERVATIONS.md` for hard-won lessons
> (append-only, one section per phase). Keep this file short: duplicating
> those here just gives a future session more text to read for the same
> information, at lower quality.

**Last updated:** 2026-08-21
**Last session model:** Opus 5 (Phase 7 planning). Implementation is Sonnet.

## Current phase

**Phase 6 is complete and verified — both P6.1 and P6.2.** Identity
resolution is wired into the real referral-creation path, the review
queue is a real screen, and Screen 6 works end to end in a live browser
(screenshot in `docs/screenshots/screen6-identity-review.png`).

**Phase 7 is planned, not started** — `docs/PHASE7_PLAN.md`, D28–D33,
ADR-015. Waiting for a go-ahead to start P7.1. A ready-to-use starting
prompt is in `temp.txt` (gitignored scratch file).

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
  `docs/PHASE2_OBSERVATIONS.md` Phase 5 section, observations 34–40.
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
  `docs/PHASE2_OBSERVATIONS.md`'s new Phase 6 section.
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

## Not done / in progress

- P7.1: not started, needs the user's go-ahead (handoff R1). Starting
  prompt ready in `temp.txt`.
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

## Open item for the user

**The real-phone clip** (plan §8.5, the Review-III fallback) is still
owed, and is being kept. Needs a physical Android phone: open the app, add
to home screen, airplane mode, create a referral, restore signal, record it
syncing. Ten minutes; nothing in this repo can do it. Note where the file
lands here once recorded — it is deliberately not committed (large binary).

## Next concrete step

**Start P7.1** on the user's go-ahead, in a new session, using the prompt
in `temp.txt`. P7.1 is the cohort generator + the configs + the loader:
`generator/cohort.py`, `timeline.py`, `cli.py` (building on P6.1's
`names.py`/`gold_set.py`, not replacing them), `configs/`, and
`server/scripts/load_cohort.py`. No migration (`alembic heads` stays
`0007`), no new screen, no test-layer work — that is P7.2. Model: Sonnet.

**P7.1 owes one number back:** the measured wall-clock time of a single
cohort load. Phase 8's E1 budget is fifty-four of them (ADR-015).

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
cd client && npx playwright test                     # expect 10 passed, ~2 min (see below)
```

Two of those 10 tests need a demo-scale scheduler running first, or they'll
sit at their real-SLA pace instead of failing fast — start one before the
`npx playwright test` above:

```bash
docker compose run --rm -d --name demo-scheduler -e SLA_SCALE=0.0004 -e SWEEP_INTERVAL_SECONDS=5 scheduler
# ... run the tests ...
docker stop demo-scheduler   # started with --rm, so this also removes it
```

Server (`alembic heads` should print `0007`):

```bash
docker compose exec db psql -U postgres -c "DROP DATABASE IF EXISTS nirantharseva_test;" -c "CREATE DATABASE nirantharseva_test;"
docker compose run --rm -e DATABASE_URL="postgresql+asyncpg://postgres:dev@db:5432/nirantharseva_test" \
  api sh -c "alembic upgrade head && python -m app.seed && ruff check . && ruff format --check . && pytest -q && python -m app.verify_replay"
```
Expect `245 passed`, clean.

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

## Known problems and workarounds

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
