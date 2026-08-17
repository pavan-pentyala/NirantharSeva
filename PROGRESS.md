# PROGRESS

> Claude Code reads this at the start of every session and rewrites it at the
> end. It is the only memory that survives between sessions. Keep it honest —
> an optimistic PROGRESS file is worse than no PROGRESS file, because the next
> session builds on top of something that does not exist.

**Last updated:** 2026-08-17
**Last session model:** Opus 5 — P2.2 planning docs + ADR-005/006.
**Documentation only: no file under `server/`, `client/` or `.github/` changed,
and CI was not re-run.**

---

## Current phase

**Phase 1 is now unqualifiedly done.** GitHub Actions is green end-to-end,
confirmed by running it, not by inspection — see "GitHub Actions is now
confirmed green" below. The `gh` CLI is installed and authenticated in this
environment as of this session; future sessions can check CI runs directly
instead of asking the user to look.

**Phase 2, sub-phase P2.1, is done — all exit criteria met, confirmed both
locally and on GitHub Actions.** ADR-003 (conflict resolution) and ADR-004
(generic sync envelope) are written. Migration `0003` (referral domain
schema), `app/domain/states.py`, `app/sync/conflicts.py`, the referral
dispatch in `apply_operation`, the pull-envelope change (D3), and the
client update are all committed and pushed. CI run
[32019283579](https://github.com/pavan-pentyala/NirantharSeva/actions/runs/32019283579)
is green on commit `4dd737b` — all four jobs.

**P2.2 (auth on `app_user`, RBAC, org scoping) is planned and documented, but
NOT started — no code exists for it.** Its plan was rewritten on 2026-08-17
because, as previously written, **it could not be built as specified**: its exit
criterion referenced a referral API that does not exist, and its security filter
trusted a column the client controls. Four further decisions (**D5–D8**) were
settled with the user, and **ADR-005 and ADR-006 are written**. Per handoff R1,
P2.2 still needs the user's explicit go-ahead before any code.

## Done in this planning session (2026-08-17, docs only)

- Re-read the whole Phase 2 document set against the code that now exists, and
  found that **P2.2 as written could not be built**: its exit criterion named a
  referral API that does not exist, its scoping filter trusted a client-supplied
  column, `app_user` had no unique constraint for the login it specifies, and the
  `DEV_USERS` removal it describes in four files actually touches thirteen and
  breaks CI login unless seeding lands first.
- Settled **D5–D8** with the user (read API; write-path trust boundary; toy
  branch unscoped; migration `0004` integrity pass). Recorded in
  `docs/PHASE2_PLAN.md`.
- **Wrote ADR-005** (org-subtree visibility, read side) and **ADR-006**
  (server-derived org identity, write side). Two ADRs rather than the one the
  plan budgeted — reasoning in the Step 0 section of the phase plan.
- Rewrote the P2.2 section, the "Verify Phase 2 yourself" block (now includes a
  seed step and `make`-free commands) and "Traps" (six → eleven).
- **`docs/IMPLEMENTATION_PLAN.md` was not edited.** Every divergence is carried
  as an override in `docs/PHASE2_PLAN.md`, whose preamble was updated to say that
  is what it does. Exactly one true supersession exists in Phase 2: D7.

## Done in the previous session (P2.1 code + the CI fix)

- Read `docs/HANDOFF_CLAUDE_CODE.md`, `PROGRESS.md`, `docs/PHASE2_PLAN.md`,
  plan §6, in full, per the session's own instructions.
- **Found and fixed the reason CI had never gone green.** All three prior
  CI runs (`5038708`, `523bba3`, `1a62dac`) failed identically at the `npm
  ci` step of the `e2e` job with `EACCES` on `client/node_modules/@babel` —
  deterministic, not flaky. Root cause: `docker compose up --build` ran
  before `npm ci`; the client service's named volume
  (`client_node_modules`) mounts at a path inside a host bind mount
  (`./client:/app`), so Docker has to create `client/node_modules` on the
  actual host filesystem as the mount point when it's missing, and does so
  as root (the Docker daemon). On a clean GitHub runner nothing exists
  yet, so the directory was left root-owned before `npm ci` (running as
  the unprivileged `runner` user) tried to write into it. **Fix: run `npm
  ci` and the Playwright browser install before `docker compose up`** in
  `.github/workflows/ci.yml`'s `e2e` job. Commit `6f5b98c`.
- **GitHub Actions is now confirmed green.** Run
  [32016630078](https://github.com/pavan-pentyala/NirantharSeva/actions/runs/32016630078)
  — all four jobs (`clock-discipline`, `client`, `server`, `e2e`) passed,
  the first time `e2e` has ever gone green on GitHub's infrastructure.
  This means Phase 1's fault tests (= experiment E4's evidence) are now
  proven on a clean machine, not only on this laptop.
- ADR-003 (conflict resolution policy) and ADR-004 (generic sync envelope)
  written. Commit `d166ff3`.
- **P2.1 built**: schema migration `0003`, the pure state machine, the
  five-row conflict table, the referral dispatch in `apply_operation`, the
  D3 pull-envelope change with the client update in the same commit, and
  all P2.1 tests. Commit `4dd737b`, pushed. Detail below.

## Phase 2.1 — what was built

- **`server/alembic/versions/0003_referral_domain.py`** — `referral_state`
  (8 values) and `user_role` (5 values, D2) enums; `org_unit`, `app_user`,
  `patient`, `patient_alias`, `sla_profile`, `referral`, `referral_event`,
  `escalation`, `sync_conflict` tables; `uq_escalation_open` (I5),
  `idx_referral_open`, `idx_event_referral`, `idx_patient_norm`. No
  `DEFAULT now()` anywhere (ADR-001, same rule as `0002`). `0002` is
  untouched — this is a new revision.
- **The shared `event_seq` sequence (D3/ADR-004).** Both `toy_event.seq`
  and `referral_event.seq` now default to `nextval('event_seq')`, so one
  `/sync/pull` cursor can span both tables without gaps. Deliberately
  **not** `OWNED BY` either table/column — an owned sequence auto-drops
  with its column, and `toy_event` is dropped at Phase 4 (D1) while this
  sequence and `referral_event` must survive that drop.
- **A real migration bug caught by testing against a truly empty
  database, not a lightly-used one.** `setval('event_seq', COALESCE(MAX(seq),
  0))` works when `toy_event` already has rows (it did, from earlier
  manual testing on the dev DB) but fails outright on a genuinely fresh
  database: Postgres sequences have `MINVALUE 1`, and `setval(seq, 0)` is
  out of range. First cold-start (`docker compose down -v && up -d
  --build`) after writing the migration caught this immediately — fixed
  with `setval`'s third argument (`is_called`): value=`MAX(seq)` with
  `is_called=true` when rows exist, value=`1` with `is_called=false` when
  the table is empty, so neither case wastes a sequence value.
- **`server/app/domain/states.py`** — pure module, no DB/framework
  imports. `TRANSITIONS`, `GUARDS`, `is_legal`, `may` exactly per plan
  §6.2. Plus `replay_state`: reconstructs `(current_state, current_lamport,
  winning_op_id)` by replaying an ordered event list, advancing only when
  an event's `from_state` matches the state so far. This is the function
  I3 rests on — `apply_operation` calls it to find "the current lamport"
  (plan §6.1 deliberately has no lamport column on `referral`), and the
  new property test calls it independently of the cache to verify I3
  holds.
- **`server/app/sync/conflicts.py`** — the five-row decision table from
  ADR-003. Two things it does that the phase plan's own table left open,
  recorded in the ADR: equal incoming/current lamports resolve to
  `conflict` (not a `device_id` tiebreak, which the phase plan suggested —
  see ADR-003 for why this departs from it), and operations against a
  referral that doesn't exist yet are rejected (`unknown_referral`,
  `already_exists`) before the table is ever consulted.
- **`server/app/sync/push.py`** — `apply_operation` dispatches on
  `op.entity`: `toy`/`set_value` is byte-for-byte unchanged (D1);
  `referral`/`create_referral` and `referral`/`transition` are new. The
  role that guards a transition (I4) comes from the authenticated JWT
  claim, threaded through from `api/sync.py`, **never from the op
  payload** — a device cannot be trusted to name its own role.
- **`server/app/sync/pull.py` + `server/app/schemas/sync.py`** — `EventOut`
  is now the generic envelope (D3): `seq`, `entity_type`, `entity_id`,
  `op_id`, `device_id`, `lamport`, `device_time`, `server_time` stay flat;
  everything entity-specific is in `payload`. `handle_pull` is a
  `UNION ALL` across `toy_event` and `referral_event`, ordered by the
  shared `seq`.
- **Client, same commit (D3 requires this):**
  `client/src/api/client.ts`'s `EventOut` matches the new envelope;
  `client/src/sync/engine.ts`'s `applyPulledEvents` reads
  `payload.new_value` for toy events and skips `entity_type !== "toy"`
  (referral events flow through pull already, but land in no client cache
  until Phase 4 per D1).
- **`server/tests/fault/kill_api.sh` ported from toy to referral (D1)** —
  it needs no UI, so unlike the two Playwright fault tests it doesn't wait
  for Phase 4. Seeds one `patient` row via direct `psql`, then a batch of
  20 `create_referral` ops (distinct `entity_id` each, same patient),
  `docker kill`s the API mid-batch, retries, confirms exactly 20
  `referral_event` rows via the patient join.
- **Tests added:** `tests/unit/test_states.py` (is_legal/may across all 8
  states × 5 roles, terminal-state check, ESCALATED-resumes check,
  `replay_state` unit tests), `tests/unit/test_conflicts.py` (one test per
  conflict-table row, plus the equal-lamport case), one
  `tests/integration/test_referral_transitions.py` covering the full
  CREATED→CLOSED traversal with correct roles, both guard-violation shapes
  (role and transition-legality) asserting zero new events by row count,
  the conflict case asserting both rows written and `current_state`
  untouched, and the `unknown_referral`/`unknown_patient`/`already_exists`
  edge cases from ADR-003's "Gap 2". `tests/property/test_referral_replay.py`
  is the I3 property test: Hypothesis generates a random legal walk
  through the state machine (excluding ESCALATED — no human role can
  submit it), pushes it, and asserts the replayed log state equals the
  cached `current_state`.
- **`server/tests/conftest.py`** gained `anm_auth_headers` and
  `mo_auth_headers` fixtures alongside the existing `auth_headers`
  (`asha1`), needed for role-based traversal tests.
- **`.github/workflows/ci.yml`**'s `server` job env gained `anm1`/`mo1` to
  its `DEV_USERS` (the `e2e` job already had them via `.env.example`).

## Decisions taken by Claude Code this session, without asking

_(one line each, so the user can overrule)_

- **Foreign keys declared only where the plan explicitly names them, or
  share that exact single-parent shape.** `patient_id → patient.id`,
  `referral_id → referral.id` (on both `referral_event` and `escalation`),
  `patient_alias.patient_id → patient.id`, `app_user.org_unit_id →
  org_unit.id` are real FKs. The org/user cross-reference columns
  (`origin_user_id`, `origin_org_id`, `target_org_id`, `actor_user_id`,
  `escalated_to_user_id`, `created_by`, `confirmed_by`, `resolved_by`,
  `sla_profile_id`) are bare `UUID`, unconstrained — Phase 2.2's real auth
  and seed data are what give these something real to reference; forcing
  FK integrity now would need seed data that doesn't exist yet.
  > **Resolved in plan on 2026-08-17 — NOT in code.** D8 / migration `0004`:
  > the FKs land alongside the seed script, with `UNIQUE (app_user.name)`, an
  > index on `origin_org_id`, and `origin_org_id SET NOT NULL`. **Requires
  > `docker compose down -v`** — every existing referral has a NULL origin.
  > `0004` does not exist yet.
- **`actor_user_id` and `referral.origin_user_id` are left `NULL` in
  P2.1.** `app_user` has no rows until Phase 2.2's real auth lands against
  it. `actor_role` is always populated (D2's requirement) from the
  authenticated JWT claim; the *user* identity behind that role isn't
  linkable to a real row yet.
  > **Resolved in plan on 2026-08-17 — NOT in code.** D6 / ADR-006: both are
  > resolved from the authenticated session once `app_user` has rows. **Still
  > NULL in the code today.**
- **`origin_org_id`/`target_org_id` come from the client's `create_referral`
  payload, not from the authenticated identity.** `DEV_USERS`' `org_unit_id`
  is a placeholder string (`"1"`), not a real `org_unit` UUID, so there is
  nothing trustworthy to derive it from yet. This is fine only because
  P2.1 does not enforce org-scoping — **P2.2 must revisit this** when
  scoping enforcement makes `origin_org_id` a security-relevant field, not
  just a data field.
  > **Resolved in plan on 2026-08-17 — NOT in code.** D6 / ADR-006:
  > `origin_org_id` and `origin_user_id` become server-derived and the payload
  > value is ignored; `target_org_id` stays a payload field because it is not a
  > visibility input. **Nothing under `server/` has changed.**
- **`referral_event` and `sync_conflict` both gained a `run_id` column**
  beyond what plan §6.1's raw SQL lists, matching `toy_event`'s. Handoff
  §R8 requires instrumentation on anything that handles a request or an
  op; these are exactly that. Cache/lookup tables (`referral`, `patient`,
  `escalation` as given) did not get one.
- **`create_referral` validates `patient_id` exists before inserting**,
  returning `rejected`/`unknown_patient` rather than letting the FK
  constraint raise. An unhandled `IntegrityError` would roll back the
  whole per-op transaction including the receipt claim (I1), which is
  correct for a genuinely bad op but must not propagate as an unhandled
  exception out of `handle_push` and break the rest of the batch.
- **`sync_conflict.field` is always written as the literal string
  `"current_state"`** for referral conflicts — the whole cached state is
  what's in dispute, not a narrower field, but the column exists and
  leaving it `NULL` seemed less informative than naming what it actually
  is.

## Verified, by running it, not by inspection

- **Full cold start from a wiped volume state** (`docker compose down -v`
  then `up -d --build`) — the exact sequence that caught the `setval` bug
  above. All four services healthy; all three migrations (`0001`, `0002`,
  `0003`) apply cleanly to a genuinely empty database.
- Server suite: **155/155 green** (up from 25 at end of Phase 1) via the
  exact containerized command CI uses, against `nirantharseva_test`.
  `ruff check` and `ruff format --check` both clean.
- Client `npm run typecheck` and `npm run build`: clean.
- **Both Playwright fault tests pass through the new pull envelope** — the
  regression check ADR-004 calls for, proving the toy path still works
  after the breaking contract change.
- `kill_api.sh` (referral-ported): green across two repeated runs.
- All of the above run in sequence against the same cold-started stack.

## NOT verified

Nothing outstanding for P2.1 — see "Exit criteria status" below, all six
boxes checked including CI.

## Settled decisions (carried forward)

- **Name:** NirantharSeva everywhere.
- **Python tooling:** `uv`. `uv.lock` committed.
- **UI design brief:** not ready, not needed until Phase 4.
- **Git hosting:** GitHub, private repo, GitHub Actions for CI.
- **`gh` CLI is now installed and authenticated** in this environment —
  future sessions should use it directly to check CI rather than asking
  the user to check the Actions tab by hand. Binary is at
  `C:\Program Files\GitHub CLI\gh.exe` (not on the session's default
  PATH — call by full path).
- **Schedule:** plan §4 dates are tentative; phase order is what matters.
- **`make` will not be installed** — use the equivalent `docker compose`
  command from the Makefile directly.
- **Screenshots are not required** — do not raise this again.
- **Playwright installed now, not deferred to Phase 4.**
- **GitHub Actions private-repo minutes are not a real concern** — 30 of
  3,000 monthly minutes used as of this session. Do not raise this again
  unless usage actually climbs.

### Phase 2 decisions (D1–D8) — settled, do not re-litigate

Full reasoning in `docs/PHASE2_PLAN.md`. D1–D4 were settled before P2.1;
D5–D8 before P2.2, on 2026-08-17. All eight were the user's decisions, taken
with options and a recommendation — none were unilateral.

- **D1 — the toy model survives until Phase 4.** Toy tables and `ToyPage`
  stay frozen through P2 and P3. `kill_api.sh` ported to referrals in
  P2.1 (**done this session**). The two Playwright tests port at P4, and
  the toy is dropped then, in its own migration.
- **D2 — `user_role` has five values**, including `SYSTEM` (**done —
  migration `0003`**). `actor_role` is never null; `actor_user_id` is
  null for system events. `app_user.role` is never `SYSTEM`, by
  convention not constraint.
- **D3 — `/sync/pull` is a generic envelope with a typed `payload`**
  (**done this session** — see "Phase 2.1 — what was built" above).
- **D4 — seed data is a small hand-written fixture.** **Not built.** P2.2
  work. Its org assignments and `target_org_id` values were pinned during
  P2.2 planning — a completion of D4, not a change to it.
- **D5 — P2.2 ships a minimal scoped referral read API.** **Not built.**
  `GET /referrals` and `GET /referrals/{id}`, 404 (not 403) outside the
  subtree. Plan §6.5's fourth exit criterion is untestable without it, and
  plan §2.2's layout already lists `api/referrals.py`. An API, not a screen.
- **D6 — the write path is locked down both ways.** **Not built.**
  `origin_org_id`/`origin_user_id` server-derived, payload ignored;
  out-of-subtree transitions `rejected` as `outside_org_scope`. ADR-006.
- **D7 — the toy branch of `/sync/pull` stays unscoped until P4.** **Not
  built.** **The one place Phase 2 supersedes plan §6.4.** An application of
  D1, not an exception to it. ADR-005 records why this is not the failure
  ADR-004 warns about.
- **D8 — migration `0004` is a full integrity pass.** **Not built.** Unique
  `app_user.name`, index on `origin_org_id`, the deferred FKs, and
  `origin_org_id SET NOT NULL` — which is what stops the data-leak test
  passing vacuously. **Requires `docker compose down -v`.**

## Exit criteria status — Phase 2.1 (plan §6.5 items 1-3, `docs/PHASE2_PLAN.md`)

- [x] A referral traverses CREATED → … → CLOSED through the API
- [x] Every guard violation returns `rejected` and writes no event
- [x] All five conflict-table rows have a passing test
- [x] I3 property test passes (replayed state == cached state)
- [x] Both Playwright fault tests still green through the new envelope
- [x] ADR-003 and ADR-004 written
- [x] CI green — run `32019283579` on commit `4dd737b`

**All six met. P2.1 is done.**

## Exit criteria status — Phase 1 (plan §5.6), Phase 0, and 1.1

All met and now **confirmed on GitHub Actions**, not just locally — see
"Done this session" above. Not repeating the full checklists here; see
commit messages on `3e73369`, `982f203`, `5038708` if detail is needed.

## Next concrete step

P2.1 is done and reported. P2.2 is planned in full and **ADR-005 / ADR-006 are
already written**, so Step 0 is complete. Per handoff R1, **wait for the user's
explicit go-ahead before starting P2.2.**

When told to start **P2.2**, build in this order (`docs/PHASE2_PLAN.md` has the
detail for each; **switch to Sonnet — all of it is code**):

1. **Migration `0004`** — unique `app_user.name`, index on `origin_org_id`, the
   deferred FKs, `origin_org_id SET NOT NULL`. Needs `docker compose down -v`.
2. **`server/app/seed.py`** — D4's fixture, idempotent, using the injected
   `Clock`. Everything after this depends on it, including every auth fixture
   and `kill_api.sh`.
3. **Auth off `DEV_USERS` onto `app_user`** — all 13 sites listed in the phase
   plan, including the two CI seed steps that removal *creates*, and
   `test_referral_replay.py`, which calls `handle_push()` directly and does not
   look like auth code.
4. **`app/api/scoping.py`** — the recursive-CTE helper, returning a SQL fragment
   rather than a list of ids.
5. **The read API** (`app/api/referrals.py`) — 404, never 403.
6. **The write-path lockdown** — server-derived origin; `outside_org_scope`.
7. **Scope the referral branch of `/sync/pull`** — inside the branch, before
   `LIMIT`. Leave the toy branch alone (D7).

ADR-005 (org-subtree visibility) and ADR-006 (server-derived org identity) are
written and should be read before step 1, not after.

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
- **`setval('seq', 0)` fails on Postgres** — sequences have `MINVALUE 1`
  by default. Use the three-argument form (`value`, `is_called`) when the
  target might legitimately be zero/empty; see migration `0003`'s comment
  for the pattern.
- **Migration `0004` will require `docker compose down -v`.** Every referral
  written during P2.1 has `origin_org_id IS NULL`, and `0004` sets that column
  `NOT NULL`. CI is unaffected — it always starts from a clean database.
- **Once `DEV_USERS` is removed, an unseeded database fails at login with a
  bare 401**, not with a clear error. If auth suddenly breaks in P2.2, check
  whether the seed ran before assuming the auth code is wrong.
- **`.env.example` currently ships `admin1:dev:ADMIN:1`, and `ADMIN` is not one
  of the five `user_role` values.** That user can log in and obtain a valid
  token, and then every push it sends is rejected as `unknown_role`. It is a
  live bug today, closed by the `DEV_USERS` removal in P2.2. Do not try to
  migrate `admin1` into `app_user` — it has no home in the enum.
- **`app_user.name` will be doing double duty** as login handle and display
  name, and `asha_a` is not a name a panel wants on a demo screen. Nothing
  displays a user's name until P4, so the decision belongs there (a
  `display_name` column, or renamed seed rows). Do not add a column in `0004`
  for a screen that does not exist.
