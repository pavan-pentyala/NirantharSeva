# PROGRESS

> Claude Code reads this at the start of every session and rewrites it at the
> end. It is the only memory that survives between sessions. Keep it honest —
> an optimistic PROGRESS file is worse than no PROGRESS file, because the next
> session builds on top of something that does not exist.

**Last updated:** 2026-08-18
**Last session model:** Sonnet 5 — P2.2 built end to end.

---

## Current phase

**Phase 2 is now fully done — P2.1 and P2.2 both built, tested, and (pending
this session's push) CI-checked.** Auth runs against `app_user`, org scoping
is enforced on every read and on the referral branch of `/sync/pull`, the
write path is locked down both ways (I4 extended to org authority), and
`DEV_USERS` is gone entirely.

## P2.2 — what was built, in the order PROGRESS.md specified

1. **Migration `0004_org_integrity.py`** — `UNIQUE (app_user.name)`, index on
   `referral.origin_org_id`, the nine deferred FKs from P2.1 (referral↔org_unit
   ×2, patient↔org_unit, referral↔app_user, referral_event↔app_user,
   patient↔app_user, patient_alias↔app_user, escalation↔app_user,
   sync_conflict↔app_user, referral↔sla_profile), and
   `referral.origin_org_id SET NOT NULL`. Pre-checks for NULL `origin_org_id`
   and raises a `RuntimeError` naming `docker compose down -v` instead of
   letting Postgres emit a bare constraint violation — required a full
   `down -v` this session since every P2.1-era referral had a NULL origin.
2. **`server/app/seed.py`** — D4's completed fixture (PHC Ramnagar / Sub-centre
   Kotwali / Village A+B; asha_a, asha_b, anm1, mo1, supervisor1; 4 patients;
   2 referrals, one per village, both targeting PHC Ramnagar). Idempotent:
   every row keyed by a `uuid5` derived from a stable name, `org_unit`/`app_user`
   upserted (`ON CONFLICT ... DO UPDATE`), `patient`/`referral`/`referral_event`
   inserted once (`ON CONFLICT DO NOTHING`). Each seeded referral's `CREATED`
   event is appended in the same statement group as the referral row itself —
   I3 applies to seed data too, not just to API-driven writes. Uses the
   injected `Clock`, never `datetime.now()`. Invoked as `python -m app.seed`;
   `server/tests/conftest.py` calls the same function from a session-scoped
   autouse fixture, so demo data and test data cannot drift apart. Verified
   idempotent by running it twice in a row — second run changed nothing.
3. **Auth off `DEV_USERS`, onto `app_user`.** All 13 sites the phase plan
   listed, **plus a 14th it missed: `client/src/pages/ToyPage.tsx`**, which
   hardcoded `login("asha1", "dev")` for its dev auto-login — the actual login
   call the browser makes when a Playwright test loads the page. Left
   unfixed, both Playwright fault tests would have failed the moment
   `DEV_USERS` (and `asha1`) stopped existing, which is exactly what the user
   was told not to let happen. Fixed to `asha_a`; flagging it here since it
   wasn't in the original 13-file list.
   - `app/api/auth.py`: `login` and `get_current_user` are now async and
     DB-backed. **`get_current_user` uses its own short-lived session
     (`async_session_factory`), not the request-scoped `Depends(get_session)`**
     — an earlier version used the request-scoped session and it held a
     connection open for the whole request; a 20-way-concurrent test
     (`test_pull_cursor.py`) then exhausted the default connection pool
     (5 + 10 overflow). Fixed by making the auth lookup open, query, and
     close immediately. Worth knowing if E5's write-latency numbers move —
     ADR-006 flagged this exact cost as "unmeasured."
   - No `@lru_cache` anywhere in the auth path (per trap 11).
   - `CurrentUser` gained `id: UUID`; `org_unit_id` is now `UUID`, not the
     placeholder string `"1"`.
4. **`app/domain/actor.py`** — `Actor(user_id, role, org_unit_id)`, a frozen
   dataclass. Lives in `app/domain/`, not `app/api/`, per the phase plan's
   own warning about entry #12: `app/sync/push.py` and
   `tests/property/test_referral_replay.py` (which calls `handle_push()`
   directly, no HTTP, no login) both needed this type, and putting it in
   `app/api/` would have made `app/sync/` import from `app/api/`.
5. **`app/api/scoping.py`** — one recursive CTE (`SUBTREE_CTE`) plus
   `subtree_params()`, returning a SQL fragment and params, never a
   materialised Python list of ids. Four call sites in the end, not three:
   `GET /referrals`, `GET /referrals/{id}`, the referral branch of
   `GET /sync/pull`, **and** the `outside_org_scope` pre-check in
   `_apply_referral_transition` (D6) — the phase plan's own D5 section only
   named the first three, but D6's write-side authority check needs the same
   subtree membership test, so `app/sync/push.py` also imports from
   `app/api/scoping.py`, matching the precedent `pull.py` already set.
6. **Read API** — `app/api/referrals.py` (+`app/schemas/referral.py`).
   `GET /referrals?state=&limit=&cursor=` (default 50, max 200, keyset
   pagination on `state_entered_at DESC, id DESC`, opaque base64 cursor) and
   `GET /referrals/{id}` (404, never 403, on an out-of-scope id — the scope
   predicate is part of the lookup query itself, not a check after it).
7. **Write-path lockdown (D6)** — `_apply_create_referral` no longer reads
   `origin_org_id`/`origin_user_id` from the payload; both come from `Actor`.
   A payload that names them anyway is logged at WARN with the `op_id` and
   ignored, never rejected. `_apply_referral_transition` gained the
   `outside_org_scope` pre-check, positioned before the from/to-state
   coherence checks and before `decide()` — writes no event, same as
   `unknown_referral`. `actor_user_id` is populated on every `referral_event`
   row now; it was `NULL` throughout P2.1.
8. **`/sync/pull` referral-branch scoping (D7)** — the referral branch joins
   `referral` and filters on `origin_org_id IN (subtree)`, inside the branch,
   before `LIMIT`. **The toy branch is untouched, deliberately** — pinned by
   a regression test (`test_toy_events_are_still_returned_unscoped_by_pull`)
   so a later session doesn't "fix" it.

## Tests added this session

- `tests/unit/test_scoping.py` — the CTE at all three tree levels (village /
  sub-centre / PHC).
- `tests/integration/test_org_scoping.py` — 404 on an out-of-scope id, the
  id absent from the list, **the data-leak test with both directions
  asserted in one test** (asha_a sees Village A, does not see Village B, via
  `/sync/pull`), ANM/MO seeing everything below them, a payload-claimed
  foreign org still landing in the actor's own org, `outside_org_scope`
  writing zero events, the toy-branch-stays-unscoped regression, and a
  fixture check that every seeded `target_org_id` is an ancestor of its
  `origin_org_id` (scoped to the two seeded referral ids specifically — an
  earlier version scanned the whole `referral` table and false-failed on
  other tests' rows that never set a `target_org_id`).
- `tests/unit/test_auth.py` — full rewrite, DB-backed. Login success/failure,
  token claims matching the real `app_user` row, a tampered token rejected,
  and a validly-signed token for a since-removed user rejected. **The tamper
  test does not flip the token's last character** — base64url's terminal
  character of a segment can carry unused padding bits, and the first version
  of this test flipped exactly such a bit and the "tampered" token still
  verified. Fixed by decoding the payload, mutating a claim, and
  reassembling with the original signature instead.
- `tests/property/test_referral_replay.py` — updated, not added: now builds
  a real `Actor` by looking up the seeded `asha_a`/`mo1` rows by name.

## Decisions taken by Claude Code this session, without asking

_(one line each, so the user can overrule)_

- **`handle_push`'s and `apply_operation`'s `actor` parameter is
  `Actor | None = None`, not required.** Toy-only pushes (D1, frozen) never
  read it — `tests/property/test_permutation.py` and
  `tests/integration/test_pull_cursor.py` call `handle_push` directly with no
  actor at all, exactly as they did in P2.1, and forcing them to fabricate
  one would have been unnecessary churn on frozen test code.
- **`get_current_user` opens its own short-lived session instead of using
  the request-scoped `Depends(get_session)`** — see item 3 above. This is a
  connection-pool sizing fix, not a design change; `login()` still uses the
  request-scoped session since nothing exercises it at concurrency.
- **Cursor pagination for `GET /referrals`** implemented as an opaque
  base64-encoded `(state_entered_at, id)` pair with a plain `OR`-chained
  keyset predicate (not a Postgres row-constructor comparison) — simpler to
  reason about and avoids relying on Postgres's parameter-type inference
  across a row constructor, which is less common than the direct-comparison
  form already used everywhere else in this codebase (`WHERE seq > :since`,
  etc.).
- **`org_unit.type` values are free text** (`"PHC"`, `"SUB_CENTRE"`,
  `"VILLAGE"`) — the column has no CHECK constraint (plan §6.1 doesn't add
  one), so this is seed-data convention, not schema.
- **Patient names in the seed are plausible Indian names** (Lakshmi Devi,
  Ramesh Kumar, Fatima Begum, Suresh Yadav) per `DOMAIN_PRIMER.md`'s
  instruction, not literal names from any document — none were specified.
- **Fixed the 14th `DEV_USERS`/`asha1` site the phase plan's enumeration
  missed** (`client/src/pages/ToyPage.tsx`) — see item 3 above. Flagging
  because the plan explicitly said "exactly three files" for the
  `asha1`→`asha_a` change and this is a fourth.

## Verified, by running it, not by inspection

- **Full cold start from a wiped volume** (`docker compose down -v` then
  `up -d --build`) — migration `0004` applied cleanly to a genuinely empty
  database (no pre-existing NULL `origin_org_id` rows to trip the guard).
- `docker compose run --rm api python -m app.seed` — run **twice in a row**;
  second run left row counts unchanged (org_unit=4, app_user=5, patient=4,
  referral=2, referral_event=2).
- Server suite: **168/168 green** (up from 155 at end of P2.1), against
  `nirantharseva_test`, via the exact containerized command the phase plan's
  "Verify Phase 2 yourself" block specifies. `ruff check` and
  `ruff format --check` both clean.
- Client `npm run typecheck` and `npm run build`: clean.
- **Both Playwright fault tests pass** against the freshly seeded dev stack.
- **`kill_api.sh` passes** — 20/20 `referral_event` rows survived the kill
  and retry, logged in as `asha_a`.
- **The data-leak check, by hand**, exactly as the phase plan's verification
  block describes: `asha_a` sees 21 referrals (her own village's fault-test
  batch of 20 plus her one seeded referral), **all with her own
  `origin_org_id`**; `mo1` sees 22 (the same 21 plus Village B's seeded
  referral). The difference of exactly one row is Village B's referral,
  invisible to `asha_a`, visible to `mo1`.
- `\d app_user` / `\d referral` on the dev database confirm
  `uq_app_user_name`, `idx_referral_origin_org`, and `origin_org_id NOT
  NULL` are actually present, not just asserted by the migration file.

## NOT verified

- **CI has not been checked yet as of this write-up** — commit not yet
  pushed. Next action after this file is saved: commit, push, `gh run
  watch`/`gh run view` on the resulting run, and report the result honestly
  (this note should not still be here if the session report claims CI is
  green).

## Settled decisions (carried forward)

- **Name:** NirantharSeva everywhere.
- **Python tooling:** `uv`. `uv.lock` committed.
- **UI design brief:** filled in for Phase 4 (previous session,
  `docs/UI_DESIGN_BRIEF.md`) — not used this session, P2.2 was API-only.
- **Git hosting:** GitHub, private repo, GitHub Actions for CI.
- **`gh` CLI** at `C:\Program Files\GitHub CLI\gh.exe` (not on PATH).
- **`make` will not be installed** — use the equivalent `docker compose`
  command from the Makefile directly.
- **Screenshots are not required.**
- **GitHub Actions private-repo minutes are not a real concern.**

### Phase 2 decisions (D1–D8) — settled, do not re-litigate

Full reasoning in `docs/PHASE2_PLAN.md`. All eight are now **built**, not
just decided:

- **D1 — toy model frozen through P2/P3.** Untouched this session except for
  `ToyPage.tsx`'s dev-login username (see above) — that is a login credential,
  not toy business logic, and D1 does not freeze it.
- **D2 — five-value `user_role` enum.** Built in P2.1, unaffected this session.
- **D3 — generic pull envelope.** Built in P2.1; the referral branch gained a
  join and a scope filter this session but kept its envelope shape.
- **D4 — seed fixture.** **Built** (`server/app/seed.py`), see above.
- **D5 — scoped referral read API.** **Built** (`app/api/referrals.py`).
- **D6 — write path locked down both ways.** **Built.**
- **D7 — toy branch of `/sync/pull` stays unscoped.** **Built as unscoped**,
  and pinned by a regression test.
- **D8 — migration `0004` full integrity pass.** **Built.**

## Exit criteria status — Phase 2.2 (`docs/PHASE2_PLAN.md`)

- [x] An ASHA in village A cannot see a referral from village B, via
      `GET /referrals`, `GET /referrals/{id}`, or `/sync/pull`
- [x] Scoping tests pass at all three tree levels
- [x] `origin_org_id`/`origin_user_id` come from the session; a payload
      claiming otherwise is ignored, with a test proving it
- [x] A transition against an out-of-scope referral is
      `rejected`/`outside_org_scope` and writes zero events
- [x] Auth works against `app_user`; `DEV_USERS` is gone from all 13 sites
      (plus the 14th this session found)
- [x] `0004` applies to a cold database; `origin_org_id` is NOT NULL and
      indexed; `app_user.name` is unique
- [x] The seed runs in dev (verified) and CI's `server`/`e2e` jobs (steps
      added — **not yet confirmed green on GitHub Actions**, see "NOT
      verified" above)
- [x] `docker compose run --rm api python -m app.seed` seeds a working
      district
- [x] Both Playwright fault tests and `kill_api.sh` still green
- [x] ADR-005 and ADR-006 written
- [ ] **CI green — not yet checked, see "NOT verified"**

## Exit criteria status — Phase 2.1, Phase 1, Phase 0

All met and previously confirmed on GitHub Actions. Unchanged this session.

## Next concrete step

**Immediate:** commit this session's work, push, and check the resulting CI
run with `gh run watch` / `gh run view`. Report the result honestly — do not
mark P2.2 "done" in conversation until that run is actually green.

**After that:** Phase 2 is complete. Per handoff R1, **wait for the user's
explicit go-ahead before starting Phase 3.**

## Known problems and workarounds

- Host Python is 3.14.7; project pins 3.12 via `uv`. Container is
  `python:3.12-slim`. Do not build against 3.14.
- `uv` is installed via winget; if a fresh shell can not find it, use the
  full path `C:\Users\pavan\AppData\Local\Microsoft\WinGet\Links\uv.exe`.
- `run_id` shows as `""` rather than `null` in `/health` when `RUN_ID` is
  set to an empty string in `.env` — cosmetic.
- **Named Docker volumes (`server_venv`, `client_node_modules`) need `-V`
  to refresh after a dependency change**, e.g.
  `docker compose up -d --build -V <service>`.
- **`setval('seq', 0)` fails on Postgres** — see migration `0003`'s comment.
- **`app_user.name` is doing double duty** as login handle and display name,
  and `asha_a` is not a name a panel wants on a demo screen. Nothing
  displays a user's name until P4 — decide there (a `display_name` column,
  or renamed seed rows). Do not add a column for a screen that does not
  exist.
- **`docker compose down -v` was required this session** for migration
  `0004` (every P2.1-era referral had `origin_org_id IS NULL`). Already
  done; a fresh session starting from this repo state does not need to
  repeat it unless the dev database is reset again.
