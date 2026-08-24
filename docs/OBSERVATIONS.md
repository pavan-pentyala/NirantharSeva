# Implementation observations

**What this file is for:** engineering memory. Things learned by building
each phase that are not derivable from the code, the ADRs, or the git
history. Started at Phase 2 (hence the file's git history and its own
early section headers); nothing below the Phase 2 section is Phase-2-
specific.
**Who it is for:** the next session. Read it before touching `server/`.

**This file is append-only per phase.** Each new phase adds its own section
at the bottom; it never rewrites an earlier phase's. `PROGRESS.md` is
overwritten every session and cannot hold any of this.

**Where this sits relative to the other documents.** `docs/PHASE2_PLAN.md`'s
"Traps specific to this phase" was written *before* the code, from reasoning —
and ADR-005 and ADR-006 cite it by number, so it stays as it is. This file is
what the build actually taught, written *after*. Where they disagree, this file
is the newer fact and the trap list is the older prediction.

---

## Migrations and schema

**1. `setval('seq', 0)` fails on Postgres.** Sequences default to `MINVALUE 1`,
so `setval(seq, COALESCE(MAX(seq), 0))` blows up on an empty table. Use the
three-argument form — `value` plus `is_called` — whenever the target could be
zero or the table could be empty. The working pattern is commented in
`server/alembic/versions/0003_referral_domain.py`.

**2. Cold-start every new migration before believing it.** Observation 1 passed
against the dev database, which had rows from earlier manual testing, and failed
only on the first `docker compose down -v && up -d --build`. A lightly-used
database is not an empty one, and migrations are written for empty ones. Wipe and
re-apply before claiming a migration works.

**3. `event_seq` is deliberately not `OWNED BY` either table.** An owned sequence
is dropped automatically with its owning column. `toy_event` is dropped at Phase 4
(D1), while `event_seq` and `referral_event` must survive that drop. This looks
like an oversight and is not. Do not "tidy" it. See ADR-004.

**4. A nullable security column makes its own test pass vacuously.** Every
referral written during P2.1 had `origin_org_id IS NULL`, and `NULL IN (subtree)`
is never true — so the org data-leak test went green because *nothing was visible
to anyone*, including the person who created it. Migration `0004`'s `NOT NULL` is
what gives that test meaning; integrity was the secondary reason, not the primary
one.

> **The general rule, and it is the most transferable thing in this file:** a test
> that asserts something is *absent* must assert the matching *positive* case in
> the same test. Otherwise it cannot distinguish "correctly scoped" from
> "completely broken", and it reports success while proving nothing.

**5. A migration that tightens a previously-nullable column needs
`docker compose down -v`.** Pre-check for the offending rows and raise with a
message that names the wipe. A bare `NotNullViolation` from Postgres tells the
next person nothing about what to do. `0004` does this; copy the shape.

---

## Tests that passed for the wrong reason

Both of these were written during P2.2, both went green on the first run, and
both proved nothing until they were fixed. They are recorded together because the
failure mode is the same: **a test that cannot fail is worse than no test**, since
it also buys false confidence.

**6. Flipping a token's last character is not a tamper test.** base64url encodes
in 6-bit groups, so the final character of a segment can carry unused padding
bits. A flip that lands only on those bits leaves the *decoded bytes* unchanged —
and therefore the signature still verifies. The first version of
`test_tampered_token_is_rejected` did exactly this and asserted a 401 that never
came. Tamper properly: decode the payload, mutate a claim, re-encode, and
reassemble with the **original** signature.

**7. A whole-table assertion picks up other tests' rows.** The
"every seeded `target_org_id` is an ancestor of its `origin_org_id`" check scanned
all of `referral`, and false-failed the moment another test in the same session
created a referral with no `target_org_id`. Scope a fixture assertion to the
fixture's own ids — import them from `app.seed` rather than re-deriving or
scanning.

---

## Auth and connections

**8. Never hold the request-scoped session inside an auth dependency.**
`get_current_user` runs on *every* authenticated request. Written with
`Depends(get_session)`, it held a pooled connection open for the entire request
lifetime, and `test_pull_cursor.py`'s 20-way concurrent push exhausted the pool
(SQLAlchemy defaults: size 5, overflow 10) and timed out after 30s. It now opens
its own short-lived session, queries, and closes.

This is ADR-006's "third cost", which that ADR called unmeasured. It is measured
now: it bites at 20-way concurrency with default pool settings. **Look here first
if E5's write-latency numbers move.**

**9. No `lru_cache` over the user lookup, ever.** After ADR-005, org membership is
a confidentiality boundary. A cached `app_user` row means a moved or disabled user
keeps their old visibility until the process restarts. The Phase 0 auth stub had
an `@lru_cache` and it was deliberately not reinstated.

---

## Plan-vs-reality drift

> **The general rule:** an exhaustive file list written during planning is a
> *hypothesis*. Verify the count with grep before trusting it. Both items below
> are cases where a carefully-written plan document undercounted, and both would
> have caused silent breakage.

**10. The `DEV_USERS` blast radius was 14 sites, not the 13 the phase plan
enumerated.** The missed one was `client/src/pages/ToyPage.tsx`, which hardcoded
`login("asha1", "dev")` — the dev auto-login the browser actually performs when a
Playwright test loads the page. It is not obviously auth code and does not appear
in any server-side search. Left unfixed, both Playwright fault tests would have
broken the moment `asha1` stopped existing, and those tests are experiment E4's
evidence.

**11. `SUBTREE_CTE` has four production call sites, not the three that ADR-005
and `scoping.py`'s own docstring claim.** The fourth is
`push.py::_actor_can_see_referral_origin`, added by D6 *after* ADR-005 was
written. A consequence worth knowing: **`app/sync/` now imports from
`app/api/scoping.py`** — the write path needs the same subtree test the read path
uses. Phase 3's timeline endpoint makes it five.

ADR-005 is Accepted and must not be rewritten (`ADR-TEMPLATE.md` forbids it). The
correction is recorded here and in ADR-008's Context.

---

## CI

**12. The ADR-001 clock grep is a substring match, and it matches comments.** The
`clock-discipline` job greps `server/app/` for the literal `datetime.now(` and
excludes only `app/clock.py`. It has no idea what a docstring is. A docstring
reading "uses the injected Clock, never `datetime.now()`" — a sentence written to
*document compliance* — fails the build. This cost one red run: `5802b13` failed,
`03fdbcf` fixed it by rewording.

Write **"uses the injected Clock — see `docs/decisions/ADR-001.md`"**. Never write
the banned literal, not even to say you are not using it.

Do not try to make the grep comment-aware. A fragile parser guarding a rule is
worse than a blunt matcher plus this note.

---

## Two standing items, recorded so they are visible

- **`docs/mom/` contains only `.gitkeep`.** Plan §16 requires a minutes-of-meeting
  file per week, written the same day, with a monthly bundle. None exist. This is
  project discipline rather than engineering, but it is a graded obligation and
  nothing else in the repo tracks it.
- **`README.md` documents `make up` and `make test`**, but `make` is not installed
  on this machine and will not be (settled decision). Either fix the README or
  accept that its first instruction does not run.

---

## Related decisions, for cross-reference

| Observation | Decision it restates or corrects |
|---|---|
| 3 | ADR-004 — one shared `event_seq` behind both event tables |
| 4, 11 | ADR-005 — org-subtree visibility; its "three call sites" is now four |
| 8, 9 | ADR-006 — server-derived org identity; its "third cost", now measured |
| 6, 7 | No ADR — test-design lessons, recorded only here |
| 12 | ADR-001 — the injected clock; this is about its CI enforcement, not the rule |

---

# Phase 3 — implementation observations

**Status:** Phase 3 complete (`110d2b2` through `2ff889a`), CI green. Built on
Sonnet in one session, in the order `docs/PHASE3_PLAN.md` gives.

**What this section is for:** the same as the Phase 2 section above — things
learned building Phase 3 that are not derivable from the code, the ADRs, or the
git history. This file is append-only per phase; this section never rewrites
the Phase 2 content above it.

---

## Grep-based exit criteria are adversarial to the same file's own prose

**13. A grep-based exit criterion counts your explanatory comments as matches
of the thing they're explaining.** Two separate instances this phase, same
root cause as observation 12's clock-discipline trap, worth generalising
explicitly now that it has bitten twice more:

- The exit criterion `grep -rn "frm == state" server/app/` returning exactly
  one line broke the first time it was written, because
  `app/domain/states.py`'s own docstring *quoted* the rule it was documenting
  — `replay_steps`'s docstring said the timeline and the verifier don't have
  to "re-derive `frm == state` on their own," which is itself a second textual
  match. Fixed by describing the rule instead of quoting its exact source
  text: "the advancement rule appears exactly once."
- The exit criterion `grep -rn "assert " server/app/sync/push.py` returning
  nothing broke the same way: the comment explaining *why* the bare `assert`
  was removed said "python -O deletes a bare assert outright" — an ordinary
  English sentence that happens to contain the literal substring `assert `
  (the word followed by a space). Fixed by putting a backtick immediately
  after the word (`` `assert` outright``) so the character after `t` is a
  backtick, not a space, and by preferring "assertion" / "AssertionError"
  elsewhere, since `assert` immediately followed by a letter never matches
  `"assert "`.

**The general rule:** before writing a comment or docstring near code a CI
grep inspects, check whether the sentence you are about to write contains the
literal pattern the grep is hunting for. A substring grep cannot tell
"the code does X" from "this comment explains that the code does X" — both
are text in the same file. This is exactly observation 12's clock-discipline
lesson, generalised: it is not specific to `datetime.now(`, it is a property
of every substring-match CI gate in this repository.

---

## The timeline's "zero events is 404, indistinguishable from out-of-scope" property is a query-shape decision, not a behaviour you can bolt on after

**14. A two-query implementation of the timeline endpoint — a separate
visibility check, then a separate events fetch — cannot produce the
"zero-events looks like out-of-scope" property ADR-008 asks for.** The first
draft of `GET /referrals/{id}/timeline` ran `SELECT current_state FROM
referral WHERE id = :id AND origin_org_id IN subtree` to decide 404-or-not,
then a second query for the events. That visibility query succeeds for a
referral that exists, is in scope, and has zero events — it never joins
`referral_event` at all — so a zero-event referral would return `200` with an
empty `events` list, not the `404` ADR-008 specifies. The property only
falls out of a **single** query: an `INNER JOIN` of `referral` to
`referral_event`, filtered by the subtree predicate and `id`, in one round
trip. Zero rows come back for three different reasons — doesn't exist, out of
scope, or exists-but-zero-events — and all three are genuinely
indistinguishable to the caller, by construction, because there is only one
query and it only produces rows when both a referral row and at least one
event row exist together.

This was caught before it shipped (no test had to fail to find it — reading
ADR-008's own alternatives table against the draft query was enough), but it
is worth recording because the ADR describes the *outcome* precisely without
spelling out that the outcome constrains the query to exactly one shape. A
future reader implementing something similar from the ADR's prose alone could
write the same two-query version and have every test pass except the one
nobody thought to write: a referral that exists, is visible, and has zero
events.

---

## Environment

**15. A persistent Docker volume across many manual `pytest` runs in one
session eventually breaks tests that assume a page holds everything.**
Observation 2 (Phase 2) already established "cold-start every migration
before believing it" for schema changes; this generalises it to test *data*.
`tests/integration/test_org_scoping.py` has two tests that push one event and
then assert it appears in `GET /sync/pull?since=0&limit=1000` — correct
against a fixture-sized database, but this session ran the full suite
manually against the same `nirantharseva_test` database close to a dozen
times while iterating on Phase 3 (no `down -v` between runs, since that would
have thrown away the running dev stack too), and `toy_event` alone
accumulated past 1200 rows. Both tests then false-failed: not because
anything in Phase 3 broke pull scoping, but because their own event fell
outside the first 1000 rows of an already-1200-row table. `docker compose
exec db psql -U postgres -c "DROP DATABASE nirantharseva_test;" -c "CREATE
DATABASE nirantharseva_test;"` resets just the test database — cheap, and
does not disturb the running dev stack the way `docker compose down -v`
would. Do this before trusting any red run that touches `/sync/pull`'s
`limit`, if the same test database has been reused across more than a
handful of manual suite runs.

---

## A judgement call on an ambiguous instruction, recorded so it can be checked

**16. Build-order step 3 ("replace the bare `assert` in `push.py` with a
structured ERROR log") is listed among "steps 1–4 change no externally
visible behaviour," but the exit criteria for that same step require a new
test proving the corrupted-cache request now succeeds instead of 500ing —
which is itself the externally visible behaviour change the step exists to
make.** Read literally, "no test edits other than rewiring
`test_referral_replay.py`" would forbid the very test the exit criteria
demand. Resolved by reading "no test edits" as protecting the 168 pre-Phase-3
tests from being altered to paper over a regression, not as forbidding a
new, purpose-built test for a newly introduced code path — no existing test
was touched, one new test was added
(`test_i3_divergence_is_logged_not_asserted_and_the_request_still_succeeds`
in `tests/integration/test_referral_transitions.py`), and the full
pre-existing 168 stayed green throughout. Flagged to the user at the time
this call was made, not decided silently.

---

## CI infrastructure — a hang unrelated to any Phase 3 code

**17. `npx playwright install --with-deps chromium` can hang forever on a
GitHub-hosted Ubuntu runner, with no error, because `--with-deps` runs
`apt-get install` under the hood and a recent runner image ships
`needrestart`, which can pop an interactive "which services should be
restarted?" prompt during that install.** With no TTY attached, `apt-get`
just blocks waiting for a keypress that will never arrive — the step shows
"in progress" indefinitely rather than failing. This hit three consecutive
`e2e` runs in this session, each for 20+ minutes before being cancelled by
hand, on a workflow step neither Phase 3 nor any recent session touched — the
`e2e` job's Playwright step has existed since Phase 0/1. Nothing about this
is specific to this repository; it is a property of the current GitHub
Actions Ubuntu image plus this particular install command.

Fixed by setting `DEBIAN_FRONTEND=noninteractive` and `NEEDRESTART_MODE=a` as
env vars on that one step (`.github/workflows/ci.yml`, commit `dc20b52`),
which forces non-interactive `apt-get` and removes the prompt entirely — the
next run finished the same step in under two minutes. A `timeout-minutes: 15`
was also added at the job level, not as the fix, but so that *any* future
hang (this cause or another) fails within fifteen minutes with a clear
timeout error instead of silently consuming CI minutes for hours and leaving
whoever is watching to notice by hand, the way this one was noticed.

**The general rule:** a CI step that shows "in progress" for far longer than
its historical duration, with zero new log output, is not "slow" — it is
hung, and retrying without a `timeout-minutes` guard just repeats the same
silent multi-hour wait. Add the timeout first, so the *next* hang (from
whatever cause) announces itself.

---

# Phase 4 — implementation observations

**Status:** Phase 4 complete — P4.1, P4.2 and P4.3 all done. Built on
Sonnet, in the build order `docs/PHASE4_PLAN.md`'s three tables give.

**What this section is for:** the same as the Phase 2 and Phase 3 sections
above — things learned building Phase 4 that are not derivable from the
code, the ADRs, or the git history. Append-only; this section never
rewrites the Phase 2 or Phase 3 content above it.

---

## ADR-009's "gains" was read as additive, not a replacement — and that reading was load-bearing

**18. `create_referral`'s payload could have been read two ways: `patient_id`
replaced by `patient_name`, or `patient_name` added alongside it.** ADR-009
says the payload "gains" `patient_name`/`age`/`sex`/`phone`, which is
ambiguous on its own. Reading it as a replacement would have broken
`patient_id`-based `create_referral` calls in five existing test files
(`test_org_scoping.py`, `test_referral_timeline.py`,
`test_replay_verifier.py`, `test_referral_replay.py`,
`test_referral_transitions.py`) plus `scripts/demo_walk.py` itself — the
exact script `docs/PHASE4_PLAN.md`'s P4.3 section calls "not disposable
scaffolding" because it is E4's evidence. The ADR's own "Alternatives
considered" table settled it: "`create_referral` already has to name a
patient; giving it the data to make one itself removes an entire failure
mode" — "already has to" names the existing `patient_id` path, "giving it
the data to make one itself" names the new one, additively.
`_resolve_patient` in `app/sync/push.py` tries `patient_id` first, falls
back to `patient_name`, and every pre-Phase-4 caller kept working
unmodified — confirmed by running the full suite and the demo walk against
the exact commit before this session, then again after (observation 19).

**19. Where `village_org_id` comes from for the new-patient match was not
written anywhere — resolved from the design file, not the plan.** ADR-009
says "exact match on `(normalized_name, village_org_id)`" but never says
where `village_org_id` comes from for a *new* patient. `docs/UI_DESIGN_BRIEF.md`
doesn't say either; `docs/design_handoff_ui_screens/Screen 2 - ASHA Create
Referral.dc.html` does — its Village field renders read-only with a "yours"
tag, never a picker. Read as: the actor's own `org_unit_id`, no new payload
field. This works cleanly for ASHA (whose `org_unit_id` *is* a village) and
is untested for ANM (whose `org_unit_id` is a sub-centre) — GUARDS[CREATED]
permits ANM to create referrals in principle, but no screen exercises that
path yet (P4.2 builds ASHA's Screen 2 only), so this is not yet a real gap,
just an unverified one worth remembering before P4.2 or Phase 6 touch this
call site.

---

## `docs/PHASE4_PLAN.md` names a `patient_cache` Dexie table the wire protocol gives no key to populate it with

**20. Declared, deliberately left empty this sub-phase — flagged rather than
guessed at.** The P4.1 build-order table says "Dexie `version(2)`:
`referral_cache`, `patient_cache` added," but ADR-010's payload — the only
new data P4.1 puts on the wire — is `patient_name`, `age`, `sex`, `reason`,
`priority`, `target_org_name`; no `patient_id`. There is no key a
`patient_cache` row could be written under from anything `/sync/pull`
sends. Two readings were possible: the plan meant something (e.g. an
optimistic write from the ASHA's own `createReferral()` call, keyed by a
client-generated id) that never got written down, or the table is scaffolding
for a later phase and simply has nothing to populate it yet. Took the second
reading — `client/src/db/schema.ts` declares `PatientCacheRow` and the
table, with a docstring stating plainly that nothing writes to it yet and
why. If the intent was the first reading, that's a P4.2 conversation, not
a silent gap.

---

## A Playwright mock that assumes call order without accounting for a lazily-initialized ID is a trap worth naming

**21. `getDeviceId()` calls `crypto.randomUUID()` itself, the first time it
runs against a fresh IndexedDB — and a Playwright test overriding
`crypto.randomUUID` to intercept a specific call by *position* will silently
intercept the wrong one if it doesn't account for that.** The first attempt
at `client/tests/referral-cache-atomicity.spec.ts` assumed
`createReferral()`'s own `op_id` generation would be the first
`crypto.randomUUID()` call after the override was installed; it wasn't —
`getDeviceId()`'s own lazy-init call went first, silently consuming the
intercepted id as a *device id* instead of the *op id* the test meant to
collide, and the test passed for the wrong reason (no exception was thrown,
`threw` was `false`, and the assertion on it caught that — but a less
careful assertion could have missed it entirely). Fixed by pre-seeding
`sync_meta`'s `device_id` row before installing the override, so
`getDeviceId()` reads a cached value instead of minting one. Same shape as
observation 6 (Phase 2) and observation 13 (Phase 3): a thing outside the
code path under test can still consume the exact resource the test is
trying to control.

---

## The full-suite pytest run has one pre-existing failure, unrelated to this session, present on the last committed Phase 3 commit too

**22. `test_concurrent_pushes_leave_no_gap_in_the_pull_cursor`
(`tests/integration/test_pull_cursor.py`) failed on a fresh
`nirantharseva_test` database this session — and reproduces identically on
commit `a4c27aa` (the last commit before any P4.1 change), confirmed by
stashing every P4.1 edit and re-running it in isolation.** Not a regression
from this session's `push.py`/`pull.py` changes (the failing test only
exercises the toy entity, untouched by ADR-009/ADR-010). `PROGRESS.md`
records CI green on this exact commit on GitHub's Ubuntu runner
(run `32240152464`), so this looks environment-specific to this Windows
Docker Desktop setup rather than a real gap in `acquire_seq_lock`'s
guarantee — plausibly connection-pool or scheduling timing under 20
concurrent `asyncio.gather`ed pushes, different between this host and the
Linux CI runner. Left unfixed and unmodified: out of P4.1's scope, and
touching `app/db.py`'s pooling or `test_pull_cursor.py`'s concurrency
mechanics without being asked risks the exact sequencing invariant (I2-
adjacent, ADR-002) this phase has no reason to be near. Every other test in
the suite — 186 of 187, plus all of P4.1's own new tests — passed clean on
this same run.

---

## An optimistic write can poison the pull-side fold it's supposed to anticipate — the most important thing found this session

**23. `applyPulledEvents`' referral branch (built and tested in P4.1) folded
`state so far` from `referral_cache`, and that was wrong the moment P4.2
gave `createReferral`/`transitionReferral` something real to write against.**
Both functions write their target state into `referral_cache` optimistically,
before any round trip (plan §8.3, by design). P4.1's own test for the fold
(`apply-pulled-referral-events.spec.ts`) never caught this, because it built
a synthetic event fixture with no matching optimistic write ever having
touched `referral_cache` first — a case that cannot occur through P4.1's own
code, since P4.1 shipped no screen that could call `createReferral`. The
first time a real screen created a referral and then waited for its own
confirming pull, the bug was immediate and total: the confirming
`create_referral` event's `from_state` is `null`, but `referral_cache`
already read `"CREATED"` (the optimistic write's own doing) by the time the
pull processed it — `null !== "CREATED"`, so the fold's `advanced` check
returned `false`, and the event that should have confirmed the referral's
own creation was silently dropped instead. Every *subsequent* optimistic
transition on that device has the identical shape: the confirming pull for
your own accepted transition never advances, because your own optimistic
write already moved `referral_cache` past what the confirming event's
`from_state` expects.

Caught by hand, not by a test that predicted it: the P4.2 exit-criterion
walkthrough (create a referral offline, reconnect, open its detail page)
showed an empty "What happened" timeline where a "Referral created" entry
should have been. Traced with `window.__db`/`window.__engine` (the same
Playwright test hooks `main.tsx` already exposes) by manually diffing what
`GET /sync/pull` actually returned against what `referral_event_cache` held
after the client processed it — the server had the event at the right seq,
the client's cursor had advanced past it, and the client had simply never
written it anywhere.

**Fix:** fold `state so far` from `referral_event_cache` (only ever written
by an *advancing* pull — nothing else touches it) instead of from
`referral_cache` (which optimistic writes can move ahead of the fold at any
time). This is more than a bug fix — it is the correct general design: two
different jobs were sharing one table, and only one of them should have been
folding against it. `referral_cache` stays the UI's read model (optimistic,
can be ahead of the confirmed log); `referral_event_cache` is now the only
thing the fold itself ever reads or writes. `apply-pulled-referral-events.spec.ts`
still passes unmodified after the fix (its fixture never had a prior
optimistic write to begin with, so the two implementations agree on that
case) — a second Playwright test
(`p42-screens.spec.ts`'s end-to-end walkthrough) is what actually exercises
the case that broke, and would catch a regression here.

**The general lesson:** a fold's "state so far" must come from a table only
the fold itself writes. Any other writer of that table — including an
optimistic UI update the fold's own author added, in the same file, one
phase later — can invalidate the fold's core assumption without touching
the fold's code at all.

---

## Windows Docker Desktop's bind mount does not reliably notify a long-running `vite dev` process of file changes

**24. Several rounds of edits to `App.tsx`, `engine.ts`, and new page files
were invisible to the already-running `client` container until it was
explicitly `docker compose restart client`'d.** The container was started
hours earlier, at the start of this session; `vite dev`'s file watcher uses
native filesystem events by default, and those don't reliably cross a
Windows-host-to-Linux-container bind mount without polling enabled
(`server.watch.usePolling` in `vite.config.ts`, not currently set). The
symptom was confusing rather than a clean failure: `npx tsc --noEmit` and
`npm run build` (both one-shot commands that read the current file state
directly) showed no problem at all, while a *running* Playwright test hit
`/login` and got the stale pre-router `App.tsx` content — because the
long-lived dev server process genuinely hadn't reloaded. Restarting the
container (not rebuilding the image — the source is bind-mounted, so a
restart alone re-reads it) fixed it every time this happened. Not
configured to poll, on purpose: it would cost dev-server responsiveness for
every session to fix a problem that a `docker compose restart client` after
a batch of edits solves in two seconds. Worth remembering before spending
time debugging a test failure that looks like an app bug but is actually a
stale dev server.

---

## Screen 3's action buttons didn't match the ASHA's actual permissions — confirmed with the user rather than guessed

**25. The design mockup gives the ASHA "Mark as arrived" (`→ ARRIVED`) and,
on the escalated variant, "mark as lost" (`→ LOST`) — but `GUARDS`
(`app/domain/states.py`, Phase 2, frozen) reserves `ARRIVED` for `MO` and
`LOST` for `SYSTEM` alone; no human role can write `LOST` at all.** Building
either button as shown would ship a control that always comes back
`rejected: role_not_permitted` if pressed — not a styling problem,
a design assuming looser permissions than the already-reviewed RBAC model
grants. Flagged per handoff §8 rather than built around silently; the user
picked "build only her real actions" over showing the mockup's buttons
disabled-with-an-explanation or loosening `GUARDS` to match the design.
Implemented in `client/src/domain/referralActions.ts`: `ashaActionFor`
returns a real action only at `CREATED` (`→ IN_TRANSIT`, "Mark as sent") and
`BACK_REFERRED` (`→ CLOSED`, "Mark as care finished") — both already
`GUARDS`-permitted and both already implied by the rest of the design (the
create flow, Screen 1's "Care finished" pill). Every other state shows a
plain waiting line instead of a button, reusing the design's own
"Waiting for: ..." pattern rather than inventing new copy.

---

## Two data gaps P4.1 didn't anticipate, both resolved without a server contract change

**26. Screen 3's timeline needs per-event history, and P4.1's Dexie schema
only ever gave the client a folded snapshot (`referral_cache`), not a log.**
`docs/PHASE4_PLAN.md`'s P4.1 build-order table named `referral_cache` and
`patient_cache` as the only new Dexie tables; nothing in P4.1's scope
anticipated a screen needing individual event history rendered offline.
Added `referral_event_cache` (Dexie `version(3)`, `client/src/db/schema.ts`)
— one row per *advancing* pulled event, written alongside the
`referral_cache` update in the same `applyPulledReferralEvent` (the same
function observation 23 above fixed). A client-only Dexie table addition
doesn't touch the wire protocol or any server schema, so this was decided
without asking — flagged here rather than left implicit, per the same
"small technical choices, but tell him" rule P4.1's `patient_cache` call
used.

**27. Screen 2 needs org names (the ASHA's own village, a facility to send
to) and nothing had ever exposed org data to the client — the JWT carries
only a bare `org_unit_id` UUID.** Unlike observation 26, this genuinely
needed a new server endpoint (`GET /org_units`,
`server/app/api/org_units.py`) — a new API surface, not a client-only
addition — so it was asked before building, not decided alone. Deliberately
unscoped (unlike `GET /referrals`): org names and the tree shape aren't
patient data, so every authenticated role sees the whole tree, not just its
own subtree — verified by a test asserting `asha_b` (Village B) still sees
`PHC Ramnagar` and `Village A` in the response. Cached client-side into a
new `org_cache` Dexie table (`version(3)`, same bump as observation 26),
refreshed once after login rather than re-fetched per screen.

---

## No display name is available client-side for any actor but (arguably) the one logged in — the timeline is attributed by role, not name

**28. The design's timeline says "by you, Sunita Kumari"; nothing on the
wire gives the client a name to say that with.** `app_user.display_name`
(added in migration `0005`, P4.1) has never been sent to the client anywhere
— not in the JWT (`sub`/`role`/`org_unit_id`/`iat`/`exp` only, unchanged
since Phase 0), not in the widened pull payload (ADR-010 lists
`actor_role`/`actor_user_id`, not a name). Even the *current* user's own
display name isn't available client-side: the JWT's `sub` claim is the
login username, not `display_name`, and there's no endpoint that returns
the latter. `client/src/domain/timeline.ts`'s `timelineAttribution`
attributes every event by role instead — "by the ASHA", "by the MO", "by
the system" — real data instead of a fabricated name, at the cost of the
mockup's personalization. Not asked about separately: this is a copy
simplification with no contract change, the same category of call as
observation 25's waiting-line copy, and is named here so it's not mistaken
for an oversight later.

---

## Verifying "no banned word" against the built JS bundle produces the same false-positive trap Phase 2/3 already documented for grep-based exit criteria

**29. A blind `grep -i` for the banned words (sync, pending ops, conflict,
operation, queue, offline mode, retry, payload) across
`client/dist/assets/*.js` returns dozens of hits — none of them UI copy.**
React's own internal fiber scheduler uses "queue" constantly; this project's
own function/variable names (`syncNow`, `sync_meta`, `Op.payload`,
`useSyncStatus`) are exactly the vocabulary the banned list forbids in
*rendered copy*, and a production build keeps every one of them as a
readable string or property name even after minification. Verified instead
by grepping the **source** `.tsx`/`.module.css` files and checking every
match by hand: every hit was an import, a function name, a CSS class, or a
comment — never a JSX text node or string literal actually rendered to a
screen. Same shape as observation 13 (Phase 3): a grep-based check is
adversarial to your own identifiers, not just your prose, and "grep the
built output" needs a human read of what each match actually is, not a
pass/fail on hit count.

---

## P4.3's own `grep -rn toy_ client/src` exit criterion cannot reach zero — and that is correct, not a failure

**30. Two references to the dropped scaffold table's name must survive in
`client/src/db/schema.ts` forever, because Dexie's schema history works the
same way Alembic's does.** `docs/PHASE4_PLAN.md` writes P4.3's criterion as
"`grep -rn toy_ server/app client/src` returns nothing." `server/app`
reaches zero cleanly. `client/src` cannot, for two independent reasons:

1. **`version(1).stores({ toy_cache: "id", ... })` is shipped history.**
   Dexie replays every declared version in order to upgrade an existing
   browser's IndexedDB. Editing v1 retroactively is the same mistake as
   editing a shipped Alembic migration — a rule this project states in
   `CLAUDE.md` and enforces server-side.
2. **`version(4).stores({ toy_cache: null })` *is* the drop.** Dexie's
   "remove this table" syntax is naming it with a `null` schema. Omitting
   the table — the way v2 and v3 omit tables they don't change — leaves it
   in place, so the only way to actually delete it is to write its name one
   final time.

The plan's own trap list anticipated the *shape* of this ("P4.3's
`grep -rn toy_` criterion will catch a comment that mentions toy_ in
passing") and prescribed rewording prose. Every prose hit was reworded
accordingly — `server/app/sync/pull.py`'s docstring now says "the toy
model's own event table" rather than naming it. But the two lines above are
code, not prose, and no rewording removes them. Read the criterion as "no
leftover toy *implementation*," which is objectively true: no toy table
server-side, no cache reads or writes anywhere, no `ToyPage`, no toy branch
in `push.py`/`pull.py`/`applyPulledEvents`. A block comment above
`version(4)` states this in the file itself, so a future session running
the grep doesn't mistake the two survivors for work left undone.

**The general rule, third instance now:** a grep-based exit criterion
counts your comments (obs. 13), your own identifiers (obs. 29), and now
your framework's required syntax. It is a starting point for a human read,
never a pass/fail gate on its own.

---

## The Cache API's default `Vary` handling silently defeats a hand-rolled precache

**31. `cache.match(request)` respects the `Vary` header by default, and
`vite preview` (like most static hosts) sends `Vary: Accept-Encoding` — so
a precached asset misses on lookup even though it is definitely in the
cache.** The install handler's `cache.addAll()` issues its own fetches, and
the browser's later `<script>`/`<link>` requests for the same URLs don't
send byte-identical `Accept-Encoding` headers. `Vary: Accept-Encoding` tells
`match()` to compare that header between the stored request and the current
one; they differ; the lookup returns `undefined`.

The failure is maximally confusing, because everything *looks* right:
`navigator.serviceWorker.getRegistration()` reports `activated`,
`navigator.serviceWorker.controller` is non-null, and dumping
`caches.open(...).keys()` shows all seven expected entries with the exact
URLs being requested. Only instrumenting the SW's own `fetch` handler with
a `console.log` of `!!cached` (visible via Playwright's
`context.on("serviceworker")` then `worker.on("console")`) showed
`cached=false` for assets that were plainly present. Fixed by passing
`{ ignoreVary: true }` to both `match()` calls in `client/src/sw.ts`. That
is safe *here* specifically because every cached entry is this app's own
build output, content-hashed per filename, never served with different
content for the same URL — it would not be safe for a general-purpose
runtime cache.

Worth knowing before hand-rolling a service worker: Workbox sets
`ignoreVary` for precached entries as a matter of course, which is part of
why this class of bug is rarely seen by people who use it. This project
deliberately uses `injectManifest` with a plain Cache Storage
implementation (no Workbox runtime — plan §8.4's "precache the app shell"
is only seven files), so the default had to be overridden by hand.

---

## Porting the fault tests off the toy harness exposed a real bug the toy harness structurally could not

**32. `startAutoFlush()` was only ever called from `LoginPage`'s submit
handler, so a device that reopened the app with an already-valid session
never started flushing its outbox.** The Phase 1 toy harness called
`startAutoFlush()` from its own page's mount effect, and that page was
mounted at `/` unconditionally with no auth gate — so in the toy world,
every page load started the sync engine, and the gap did not exist to be
found. P4.2's real screens moved that call to the login moment, which is
correct for a fresh login and silently wrong for every *subsequent* app
boot: reopened tab, reload, PWA relaunch from the home screen.

`client-kill-resume.spec.ts`'s port is what surfaced it — its whole premise
is "kill the tab mid-push, reopen, confirm the retry lands," and the reopen
step goes straight to `/referrals` with a valid token in localStorage,
never through `/login`. The op sat at `inflight` forever and the test timed
out. Fixed by also calling `startAutoFlush()` (idempotent by its own
internal guard) from `RequireAuth`'s mount effect, which every authenticated
route passes through regardless of how it was reached.

This is the second time in Phase 4 that porting a test onto real
infrastructure found a real defect rather than just needing new selectors
(obs. 23 was the first, in P4.2). Both were invisible to the tests that
existed at the time, and both were in the "works on the happy path, fails
on resume" category the fault tests exist specifically to catch — which is
the argument for `docs/PHASE4_PLAN.md`'s insistence that these two specs
"must stay green through the port — they are E4's evidence, not disposable
scaffolding."

---

## `vite dev` and `vite preview` are not interchangeable for anything PWA

**33. `vite-plugin-pwa`'s `injectManifest` strategy injects an *empty*
precache manifest in dev mode, so a reload-while-offline test passes
vacuously or fails confusingly against `vite dev`, and only means anything
against a real build.** `devOptions.enabled: true` registers a service
worker in dev, which makes it look like the PWA is working, but
`self.__WB_MANIFEST` is `[]` — nothing is precached, so an offline reload
has no app shell to serve and the page comes back blank. The first attempt
at `offline-sync.spec.ts` ran against `:5173` for exactly this reason and
failed in a way that looked like a service-worker bug rather than a
wrong-server bug.

Resolved by: dropping `devOptions` entirely (a dev-mode SW that cannot
serve offline is worse than none — it invites this confusion), adding a
`preview` block to `vite.config.ts` with the same `/api` proxy the dev
server has, publishing `4173` in `docker-compose.yml`, and pinning that one
spec to `test.use({ baseURL: "http://localhost:4173" })`. The other four
specs stay on the dev server, where hot reload is worth having and no
precache is needed. CI builds and starts `vite preview` before running
Playwright, in its own step with its own readiness poll.

**Corollary for anyone running the suite by hand:** `npx playwright test`
now needs *both* servers up. `docker compose up -d` gives you `:5173`;
`:4173` needs `docker compose exec client npm run build` followed by
`docker compose exec -d client npm run preview`. A `docker compose restart
client` kills the preview process (it isn't the container's main command)
and it must be restarted by hand — which cost two confusing red runs this
session before the pattern was obvious.

---

# Phase 5 — implementation observations

## `docs/PHASE5_PLAN.md`'s own op_id formula collides on a legitimate re-breach — the trap it documents needed a further correction

**34. Deriving the swept `ESCALATED` event's `op_id` from `uuid5(referral_id,
breached_state)` alone, exactly as the plan's Traps section describes it,
breaks D22's own re-breach case.** `referral_event.op_id` is `NOT NULL
UNIQUE`. A referral can legitimately breach the *same* `breached_state`
twice — resolve out of `ESCALATED` back into, say, `IN_TRANSIT`, then stall
in `IN_TRANSIT` again — and `uq_escalation_open`'s partial index correctly
allows a second `escalation` row once the first is resolved. But a second
event with the identical `uuid5(referral, breached_state)` op_id collides
with the first one's, and since the insert in `app/domain/escalation.py`
has no `ON CONFLICT` clause, this would raise an `IntegrityError` and roll
back the whole transaction — no second row either, contradicting the exit
criterion that says re-breach must produce one.

Resolved by folding `triggered_at` (the sweep's own `clock.now()`) into the
op_id: `uuid5(referral_id, breached_state, triggered_at.isoformat())`. Two
sweeps over the *same still-open* breach still collapse to the same input
whenever `now` hasn't moved, which is exactly the case
`uq_escalation_open`'s own idempotency test needs — but a genuine re-breach,
which structurally cannot happen without the SLA window elapsing again, always
has a different `triggered_at` and gets a distinct op_id.
`test_resolution_on_exit_and_rebreach_creates_a_second_row` in
`test_escalation_sweep.py` pins this: it asserts two `ESCALATED` events
exist after the second breach, not just two `escalation` rows, which is
the assertion the naive formula would have failed on silently rather than
by crashing (the crash would at least have been loud; a formula using
`ON CONFLICT DO NOTHING` instead of raising would have passed the row count
and failed the event count only).

## A `docker compose run --rm` process killed by `timeout` can outlive the tool call, survive `down -v`, and keep writing to the "clean" database that follows

**35. `timeout 8 docker compose run --rm ...` returning control after 8
seconds does not mean the container is gone.** Used to smoke-test the sweep
live, with `SLA_SCALE=0.0001` and a 2-second interval, against the
then-current dev database. The `timeout` wrapper reliably kills the
foreground `docker compose run` CLI process, but that is not the same
thing as the daemon stopping the container it started — this one kept
running detached, invisible to `docker compose ps` (which only lists
service containers), visible only in `docker ps -a`. `docker compose down
-v` immediately after reported `Volume ... Resource is still in use` and
`Network ... Resource is still in use` — the orphan holding both — and
proceeded anyway, silently reusing the *existing* network for the fresh
`up` rather than recreating it. The orphan, still attached to that reused
network with Docker's embedded DNS re-resolving `db` to the new container,
spent the next several minutes sweeping the newly-seeded, otherwise-clean
database every 2 seconds at a 24-hour SLA window scaled to under 9 seconds
— escalating both seed referrals within 16 seconds of being seeded, before
any real verification had a chance to run against a genuinely clean state.

**Caught by:** re-querying the "clean" database once more before trusting
it and finding two `escalation` rows that a fresh reseed should not have
produced. Diagnosed with `docker ps -a` (not `docker compose ps`) plus
`docker inspect <container> --format '{{.State.StartedAt}}'` to see the
orphan was older than the "fresh" service containers around it.

**Resolved by:** `docker rm -f` on the orphan by name, then re-running
`down -v` (this time reporting a clean removal of the network and volume,
no "still in use" warnings) before `up` and reseeding. **For next time:** a
one-off `docker compose run` container that will outlive the tool call
should be started detached (`-d`) or with an explicit `docker stop`/`docker
rm` afterward that is verified to have worked — a `timeout`-wrapped
foreground run is not a reliable way to guarantee cleanup, and `down -v`'s
own "still in use" warnings are worth reading, not scrolling past.

## D22's resolution UPDATE does not need to match `breached_state` — the state machine already guarantees at most one open escalation per referral

**36. `_apply_referral_transition`'s resolution `UPDATE escalation SET
resolved_at=:now WHERE referral_id=:id AND resolved_at IS NULL` (D22, no
`breached_state` predicate) is correct, not just simpler, because
`app/domain/escalation.py`'s sweep only ever escalates a referral whose
`current_state` is one of the five states with an `sla_profile` row —
`ESCALATED` itself is always excluded.** So a referral already in
`ESCALATED` can never be escalated again for a *different* breached state
while still `ESCALATED` — there is structurally at most one unresolved
`escalation` row per referral at any time, and this transition only ever
resolves the transition it is literally applied to. Worth recording because
it is the kind of thing a later change could break invisibly: if the sweep
were ever changed to escalate a referral out of a state other than the
current one (it should not be), this UPDATE's lack of a `breached_state`
predicate would silently resolve the wrong row.

## `SLA_SCALE` was silently truncated to zero for every demo-scale value — production config hid it completely

**37. asyncpg's prepared-statement type inference resolves `:sla_scale` as
`integer`, not `double precision`, when its first appearance in the query
is `s.max_hours * :sla_scale` and `s.max_hours` is an integer column —
truncating any `SLA_SCALE` strictly between 0 and 1 to exactly 0.** With
the window at zero, `state_entered_at + 0 < now` is true for a referral
that is a single millisecond old, so P5.2's demo-scale testing (`SLA_SCALE`
values like `0.001`) escalated every referral **instantly**, not after the
intended scaled window. `SLA_SCALE=1.0` — the production default, and the
only value P5.1's own test suite exercised through a real query — hides
this completely: `round(1.0)` is `1`, so the bug produces the *correct*
answer whenever the scale is exactly 1. It surfaces only at demo scale,
which is the one time a human is actually watching the clock.

**Caught by:** a live Playwright test (`client/tests/dashboard.spec.ts`)
passing in ~3 seconds when the arithmetic said it needed to wait ~86.
Diagnosed by inserting a referral with a hand-set `state_entered_at =
now()` directly via `psql` and watching `SELECT ... current_state` show
`ESCALATED` within one sweep tick, then isolating it further with a
throwaway script (`server/_probe2.py`, deleted after use — not committed)
that ran the exact breach query with an added `is_breached`/`window_interval`
diagnostic column: `make_interval(secs => s.max_hours * :sla_scale * 3600)`
evaluated to `timedelta(0)` for `sla_scale=0.001`, and a bare
`SELECT make_interval(secs => 24 * :sla_scale * 3600)` reproduced it
outside the app entirely, isolating it to the bind parameter's inferred
type rather than anything else in the query or the sweep's own logic.

**Resolved by:** `CAST(:sla_scale AS double precision)` in
`app/domain/escalation.py`'s `_BREACH_QUERY` — forces the parameter's type
before Postgres has a chance to infer it from context. **A second, real
gap this exposed:** `test_sla_scale_shrinks_the_window` (P5.1) used
`sla_scale=0.0001` and asserted only that a 1-second-old referral
escalated — which the truncation bug would *also* make pass, since with
the window at zero *anything* escalates instantly. A test that can't fail
when the exact bug it's supposed to catch is present is not proving what
its name says. Rewritten to use `sla_scale=0.5` with two referrals, one
11h old and one 13h old against a 24h SLA (scaled to 12h) — a within-window
case and a past-window case in the same test, which only passes if the
scale genuinely divides the window in half rather than zeroing it.

## Screen 5's action button silently no-opped for an escalated referral — D20 applied "symmetrically" was not applied correctly everywhere

**38. `IncomingReferralsPage.tsx`'s `handleAdvance` re-derived
`moActionFor(currentState)` *inside* the click handler, using the
referral's real `current_state` ("ESCALATED" while overdue) rather than
the display state the render already used to decide whether to show the
button at all.** `MO_ACTIONS` has no entry for `"ESCALATED"`, so
`moActionFor("ESCALATED")` returns `null` and the handler returned
immediately — the button was visibly rendered (the *render* correctly used
`moActionFor(displayState)`), looked clickable, and did nothing when
clicked. `ReferralDetailPage.tsx`'s equivalent handler was correct, but by
accident rather than design: it happened to close over the already-computed
outer-scope `action` variable instead of recomputing anything, so the same
mistake was structurally impossible there even before anyone thought about
it. Resolved by having the render pass the already-computed `action.toState`
into `handleAdvance` explicitly, rather than letting the handler recompute
it from a different state.

**Caught by:** a dedicated live Playwright test that creates a referral,
advances it to `IN_TRANSIT`, lets a demo-scale sweep escalate it, and then
actually clicks MO's "Arrived" button and asserts the card disappears from
the tab — not by code review, and not by the same pattern already having
been verified correct on Screens 1 and 3. Applying the same rule
("`ashaActionFor`/`moActionFor` read the display state") in three places
does not guarantee the *effect* of that rule is wired identically in all
three; only exercising the actual click on each screen found the one place
it wasn't. Worth remembering the next time "the same fix, applied
symmetrically" feels like it should be enough on its own.

## `docker compose run --rm -d` containers need to be tracked across a whole session, not just around the command that started them

**39. The same class of leak documented in observation 35 recurred twice
more in P5.2, despite already knowing about it** — a `--name
demo-scheduler` container from an earlier round of manual verification was
still running, 27 minutes later, holding stale pre-fix code in its already-
imported Python process, when a later `docker compose down -v` reported
"volume ... still in use" and only *then* revealed it. The `--rm` flag
means the container removes itself once stopped, which is necessary but
not sufficient — nothing stops a session from simply forgetting a
still-running background container exists between one verification step
and the next, especially when several verification passes happen across
a long session with edits in between. **The fix that actually holds:**
treat "confirm `docker ps -a` shows only the real services" as a
mandatory step before *every* `down -v`, not just the first one after a
known incident, and name one-off containers distinctly enough
(`demo-scheduler`, `sweep-demo`) that a stray one is recognizable at a
glance rather than blending into the regular service list.

## httpx's `ASGITransport` cannot drive a `StreamingResponse` with a real gap between chunks — not a `BaseHTTPMiddleware` problem, a transport one

**40. `client.stream(...)` against an app mounted on `ASGITransport` hangs
before even returning a status code once the response generator's second
chunk is more than an instant away — reproduced against a two-route
FastAPI app with zero middleware, ruling out `BaseHTTPMiddleware` (the
first suspect, given its well-known history with `StreamingResponse`) as
the cause.** A finite one-chunk-and-done generator returns instantly; a
generator that yields once and then `await`s anything before its next
yield hangs the test, seemingly regardless of middleware. `GET
/dashboard/stream`'s handler is exactly this shape (one snapshot on
connect, then a wait for the next notification or heartbeat), so no
integration test in `test_dashboard.py` opens the live route and reads
from it — `app/api/dashboard.py`'s `stream_events()` is deliberately a
standalone async generator, callable and `anext()`-able directly in a test
without going through HTTP at all, and the actual wire-level behaviour
(headers, reconnection, an open connection staying open) is proven instead
by `client/tests/dashboard.spec.ts`'s Playwright tests against a real
uvicorn server. The general lesson: when an integration test against an
in-process ASGI transport hangs on something that works fine in the real
running container, suspect the transport before suspecting the code, and
confirm with the smallest possible repro before restructuring anything
around a guess.

# Phase 6 — implementation observations

## Git Bash on Windows silently rewrote a container path argument, and `--rm` erased the evidence

**41. `docker compose run --rm api python -m generator.gold_set --seed 42
--out /app/results/e3_draft/` printed a success message naming the file it
wrote — but the path in that message was
`C:/Program Files/Git/app/results/e3_draft/ground_truth_identity.json`,
not `/app/results/e3_draft/ground_truth_identity.json`.** MSYS2's Git Bash
rewrites any argument that *looks* like an absolute POSIX path before
handing it to a Windows executable (`docker.exe` here), including
arguments meant for a process running *inside* a Linux container, which
has no relationship to the host's filesystem at all. `Path("/app/...")`
inside the container had genuinely been constructed from the mangled
string, so the file was written somewhere real but useless, inside a
container that was about to remove itself (`--rm`) the moment the command
returned — by the time the mistake was visible, the only copy was already
gone. Nothing crashed; the exit code was 0.

**Caught by:** checking for the file at its expected bind-mounted host
location (`server/results/e3_draft/`) after the run, instead of trusting
the tool's own printed confirmation — the same "don't trust the hit count,
read the match" discipline observations 13/29/30 already established for
grep now applies to a program's own stdout too.

**Resolved by:** prefixing the command with `MSYS_NO_PATHCONV=1`, which
disables MSYS2's path rewriting for that invocation. Needed on **every**
`docker compose run` (or `exec`) call in this environment that passes a
path argument meant for the container, not the host — `--out`, `--gold`,
bind-mount-relative paths typed by hand, anything starting with `/`. A
path argument that happens to also exist on the host (or partially
resolves, as `/app/...` did here by picking up the *nearest* Windows
`app/` directory it could find) is the dangerous case, because the command
still "succeeds."

## `:param IS NULL` gives asyncpg nothing to infer a type from — the loud cousin of observation 37

**42. `app/linkage/blocking.py`'s first draft of the phone predicate —
`(:phone IS NULL OR phone IS NULL OR left(phone, 4) = left(:phone, 4))` —
raised `asyncpg.exceptions.AmbiguousParameterError: could not determine
data type of parameter $2` the first time it actually ran with
`phone=None`,** which is the common case per ADR-014, not the rare one.
asyncpg's prepared-statement protocol infers a bind parameter's type from
its first usage in the query; `:phone IS NULL` is a comparison against
NULL, which carries no type information at all. Observation 37
(`SLA_SCALE` inside `make_interval`) is the same root cause — a bind
parameter's type inferred from an ambiguous first use — but that one
failed *silently*, resolving to a wrong-but-valid type (integer) and
corrupting results without an error. This one simply refuses to run,
which is the easier failure to have, but the fix is identical: `CAST(:phone
AS text)` on the parameter's first appearance, load-bearing, not
decoration, exactly per the plan's own warning in "Traps" not to let a
threshold — or, it turns out, any bind parameter compared against NULL —
reach SQL uncast.

## A synthetic gold set that inserts both spellings of a duplicate pair lets a query find itself

**43. The first draft of `generator/gold_set.py` inserted BOTH records of
each duplicate pair into `patient` before scoring — the existing record
and the record meant to be the "incoming query."** That would have let
`app/linkage/blocking.py`'s candidate scan return the query's own row
alongside the real match, and since a string always scores 100 against
itself, every duplicate pair would report a perfect match for a reason
that has nothing to do with the fuzzy matcher actually working — not a
crash, not a wrong number, a number that looks *better* than the truth.
Caught before it was ever run, by noticing that `app/sync/push.py`'s real
call site (ADR-009) never resolves a patient against itself — a referral
always names an incoming person against rows that already exist. Resolved
by splitting `generate()`'s output into `GeneratedPatient` rows (written to
the database) and separate `Query` records (name/phone/village only, never
written) — the same asymmetry the real pipeline has. Worth remembering
when Phase 7's full cohort generator extends this module: any new record
type it adds needs the same "who gets written, who only gets queried"
question asked explicitly, not inherited by copying the pattern without
re-deriving why it's shaped that way.

## Fuzzy-matching integration tests sharing one un-rolled-back database need names with no shared words, not just unique full strings

**44. A draft `test_new_patient_when_no_candidate_exists_at_all` failed
intermittently-looking but actually deterministically: the query
`"Test Pipeline Nobody Like This Exists Yet"` matched a candidate at
`review_queue`, not `new_patient`, because five other tests in the same
file had already inserted patients named `"Test Pipeline Auto ..."`,
`"Test Pipeline Review ..."`, etc.** — into the same live database, with
no per-test transaction rollback (the established pattern in this test
suite, e.g. `tests/integration/test_patient_resolution.py`). Uniquely-named
test fixtures are not enough once `rapidfuzz.fuzz.token_set_ratio` is in
the loop: it scores on the *set of shared words*, so a common English
prefix used purely for human readability ("Test Pipeline …") is itself
enough signal to cross a review-floor threshold, regardless of how
different the "real" name content is. Resolved by giving every fixture
name in `tests/integration/test_linkage_pipeline.py` zero word overlap
with every other name in that file *and* with `app.seed`'s fixture
patients ("Lakshmi Devi", "Ramesh Kumar" — both in Village A). Worth
remembering for P6.2's identity-review tests and Phase 7's integration
tests generally: a scoring-based matcher makes "give it a unique string"
a weaker isolation guarantee than it is everywhere else in this codebase.

## `token_set_ratio` scores a name against "that name plus one more word" as a perfect 100 — not just "high"

**45. Two pre-existing server tests broke the moment `push.py` started
resolving patients through the real pipeline (P6.2): `"Test Pull Payload
Patient"` and `"Test Pull Payload Patient Two"` were written to be two
different patients (Phase 2/4, exact-match-only era), and under the new
pipeline the second one silently reused the first one's identity —
`score(normalize("Test Pull Payload Patient"), normalize("Test Pull
Payload Patient Two"))` is exactly **100.0**, not merely high.** The
mechanism: `token_set_ratio` computes similarity from the intersection of
each string's token *set*; when one name's words are a strict subset of
the other's, the shorter one matches "perfectly" against the longer one by
that metric's own definition, regardless of how many extra words the
longer one carries. This is a sharper trap than ordinary spelling-variant
overlap (observation 44) — it doesn't taper off with length the way a
typo's effect does, and "append a distinguishing word" is exactly the
naming habit this codebase already used for "make two fixtures different."
`tests/integration/test_push_idempotent.py` had the identical shape
("Idempotent Test Patient" / "...Two"). **Resolved** by renaming the
second fixture in each pair to share zero words with the first, rather
than extending it. Worth remembering the next time a fixture needs a
sibling: appending, not substituting, is the dangerous move.

## A timestamp-suffixed "unique" name collides with its own earlier run once fuzzy matching is live

**46. `client-kill-resume.spec.ts` and three other Playwright specs
generated their patient's name as `` `<fixed prefix> ${Date.now()}` ``,
and a second run of the same spec against the same persistent dev
database silently reused the first run's patient:
`score("P5.2 MO Overlay Test Patient 1787293488925", "P5.2 MO Overlay
Test Patient 1787294374245")` is **92.86** — comfortably above
`AUTO_ACCEPT` (92.0) — even though every digit of the millisecond
timestamp differs.** Five of six words are identical; the timestamp is
just one more word to `token_set_ratio`; a suffix's *sole job* being
uniqueness doesn't make the matcher treat it any differently from a real
word. This produced a real, non-obvious test failure: `dashboard.spec.ts`
timed out clicking a referral row that didn't exist, because the
`create_referral` push had silently attached to a *previous run's*
patient instead of creating a new one — a wrong-identity bug wearing a
timeout's clothes. **Resolved** by generating the differentiator as
`crypto.randomUUID().slice(0, 8)` instead of `Date.now()` — a random
value has no systematic reason to overlap with a previous run's, where a
millisecond clock reading from a suite run minutes later still shares a
long digit prefix, compounding the problem even before the "one word
different" issue above. **A second pass was still needed after that fix**:
four fixture names across four different spec files shared the two words
"Test Patient" as boilerplate, and that alone scored 75–89 against each
other — not enough to reuse an identity (below `AUTO_ACCEPT`), but enough
to land in the review band and queue a spurious `identity_review` pair
per test run, which would clutter Screen 6 in a live demo with pairs no
human ever created. Every Playwright fixture patient name in this
codebase now shares zero words with every other one, the same discipline
observation 44 established server-side. The general lesson, stated once
for both: **once a "different name" fixture is scored by a real matcher
instead of compared for exact equality, "looks different to a human" and
"scores as different" are no longer the same claim, at any distance —
even two names differing in every digit of a random-looking suffix — and
every place that manufactures a "this is a different person" fixture
needs to be re-audited when fuzzy matching goes live, not just the ones
touched by the current diff.**

---

# Phase 7 — implementation observations

**Status:** P7.1 complete (cohort generator, configs, loader). CI green.

## `import generator` outside Docker's bind mount was silently resolving to nothing, in every session since P6.1

**47. `docs/PHASE6_PLAN.md`'s own build order says `generator/` "is otherwise
invisible inside the container" without the `./generator:/app/generator`
bind mount — but nothing checked whether it was equally invisible OUTSIDE
Docker, in CI's bare `server` job (`uv sync && uv run pytest`, no Docker
involved) and in any local `uv run pytest` from `server/`.** It was: `server/`
was the only directory ever added to `sys.path` (via the editable install of
`nirantharseva-server`), and `generator/` sits one level up, a sibling, not a
child. On a machine that happens to have a stray empty `server/generator/`
directory (this one did — an untracked leftover from an earlier `docker
compose up` that, for reasons unrelated to this bug, materialized a mount
point there), `import generator` **succeeds** as an empty PEP 420 namespace
package with no error, and `from generator.gold_set import generate` then
fails with `ModuleNotFoundError('generator.gold_set')` — a submodule error
that reads like a typo, not the real problem. On a fresh checkout with no
such stray directory, the same test fails with the more honest
`ModuleNotFoundError('generator')`. Either way, every generator-importing
test — P6.1's own `tests/unit/test_gold_set.py` included — has apparently
never actually run in CI's `server` job or in a bare local `uv run pytest`;
every green run on record was a `docker compose run` run, where the bind
mount papers over it. Found only because P7.1 added more generator-importing
tests and one was run locally without Docker first, as a fast pre-Docker
lint/import sanity check. **Fixed** by adding `pythonpath = [".."]` to
`[tool.pytest.ini_options]` in `server/pyproject.toml` — pytest's own
`pythonpath` ini option, no extra dependency. Verified by re-running the
exact `uv run python -c "from generator.gold_set import generate"` repro
from before the fix (fails) against after (succeeds), and by confirming
`uv run pytest tests/unit/test_gold_set.py` gets past collection/import (it
then fails on an unrelated, expected DB-connectivity error, since there is
no Postgres reachable outside Docker on this machine — the point was
collection, not a full green run). Worth checking whenever a future phase
adds a new repo-root, non-`server/` Python directory that tests need to
import: bind-mount visibility and `sys.path` visibility are two different
things, and only one of them was ever actually wired up.

## `ruff`'s import-sort category for a cross-boundary package depends on whether it happens to be nested under the project root at scan time

**48. The same `generator` import that observation 47 fixes for pytest also
sorted differently depending on environment, even after the fix: inside
Docker (`generator/` bind-mounted at `/app/generator`, a real child of the
project root `/app`), `ruff`'s isort auto-detected it as first-party
alongside `app`, sorted alphabetically after it; on the bare host (`server/`
as the project root, `generator/` a sibling, not a child), `ruff` sorted it
as some other category, before `app`.** Both `ruff check .` and `ruff
format --check .` are part of the same `docker compose run ... pytest`
one-liner this project's own verify instructions use, and CI's `server` job
runs the identical commands bare — so the two environments disagreed about
the "correct" sorted order of the exact same import block in the exact same
file, and satisfying one would fail the other. Not a hypothetical: writing
`server/tests/unit/test_cohort_generator.py` on the bare host, letting
`ruff check --fix` sort it, then running the identical `ruff check .` inside
Docker immediately re-flagged it (and vice versa) — an oscillation, not a
one-time fix. **Fixed** by adding an explicit `[tool.ruff.lint.isort]
known-first-party = ["app", "generator"]` to `server/pyproject.toml`, so the
category is a stated fact instead of a directory-nesting inference. Verified
by running `ruff check` and `ruff format --check` in both environments back
to back against the same commit and getting "all checks passed" from both.
Same root cause as observation 47 (Docker's bind mount changes what
`generator/` looks like from inside `/app/server`'s own directory listing),
different tool, different symptom — worth remembering as one class of bug,
not two, the next time something behaves differently `docker compose run`
vs. bare.

## `GET /org_units` is unscoped by design (P4.2) — which makes it an exact-set assertion any org-creating test can break, not just the ones that collide by name

**49. `tests/integration/test_org_units.py` asserts the database's org_unit
table contains *exactly* `{"PHC Ramnagar", "Sub-centre Kotwali", "Village
A", "Village B"}` — not a subset check.** `docs/PHASE7_PLAN.md`'s own
"Traps" section already named the collision half of this risk ("never let
the generator's org names collide with the seeded ones — P6.2 already hit
this once"), and `generator/cohort.py`'s names (`"Cohort{seed} PHC 1"` etc.)
never do collide. That was not sufficient: `server/tests/integration/
test_load_cohort.py`'s first draft created a real, non-colliding cohort
district via `server/scripts/load_cohort.py` and left it in the database
after the test function returned, and *any* additional row in `org_unit` —
colliding name or not — breaks an exact-set assertion the same way. Two
tests in a completely different file (`test_org_units.py`) started failing
depending on test execution order, the same cross-file-pollution shape as
observations 44-46, just via `org_unit` instead of `patient`. **Fixed** by
giving `test_load_cohort.py` its own `finally`-blocked cleanup that deletes
every row it created (`identity_review`, `patient_alias`, `referral_event`,
`sync_conflict`, `escalation`, `referral`, `patient`, `app_user`,
`org_unit`, in FK-respecting order) before the test function returns — not
by weakening the collision-avoidance already in place, and not by loosening
`test_org_units.py`'s assertion, since the exact-set check is the entire
point of that test (P4.2: `GET /org_units` is deliberately unscoped, org
names are not patient data, and that unscoped-ness is worth pinning
precisely). **A second bug hid inside the first fix's own cleanup query**:
the patient-selecting subquery joined through `referral` (`SELECT
r.patient_id FROM referral r JOIN app_user u ON ... WHERE u.name LIKE
:prefix`), but by the time the cleanup statement that deletes `patient` rows
ran, the *previous* cleanup statement had already deleted every matching
`referral` row — so the subquery silently returned zero rows, the `patient`
delete deleted nothing, and the very next statement (`DELETE FROM app_user
...`) failed on `fk_patient_created_by`, a foreign-key violation that only
appears once the *second* test in the file runs (the first test's cleanup
order happened to not expose it in every ordering). Re-deriving the
patient-id subquery from `patient.village_org_id IN (SELECT id FROM
org_unit WHERE name LIKE :org_prefix)` instead — independent of whether
`referral` rows still exist — fixed it for good. Worth remembering
generally: a multi-statement cleanup's later subqueries can silently see
the *effects* of its own earlier statements, and a subquery that "obviously"
finds the right rows needs to be checked against the state it will actually
run in, not the state at the top of the function.

## A `(index * K) % N` combinatorial name generator can accidentally re-introduce the periodicity it was built to avoid, depending on the caller's own stride

**50. `generator/cohort.py`'s `_combinatorial_name(index)` originally paired
`FIRST_NAMES[index % 30]` with `LAST_NAMES[(index // 30) % 30]` — correct in
isolation, but `_assign_people` calls it with a *global* person index while
assigning villages round-robin (`village_index = i % n_villages`), so within
one village (`n_villages=8`), consecutive calls land 8 apart, not 1 apart.
`gcd(8, 30) = 2`, so a single village's ~25-27 people only ever draw from 15
of the 30 possible first names, each one repeated roughly twice per
village — real-looking names individually, but visibly repetitive side by
side in one village's patient list, and (worse) enough shared-token overlap
between same-first-name pairs to trigger the collision-guard's re-draw path
far more than necessary (19 re-draws became 104 on the default config when a
first attempted fix — striding the last-name index by a small odd constant —
traded one periodicity artifact for a different one, still keyed off the
same underlying `index`). **Fixed** by scrambling `index` through a fixed
multiplicative hash (`(index * 2654435761) % 2**32`, Knuth's constant) before
splitting the result across the two name pools, which decorrelates the name
assignment from whatever stride the caller happens to use — deterministic
(no RNG, so reproducibility is untouched) and independent of `n_villages`.
Re-draw count on the default config dropped to 9. Verified by re-running the
byte-identical-twice check after the change (still identical) and by reading
`patients.csv`'s first several rows by eye. Worth remembering: a "index // N,
index % N" split is only collision-free against *sequential* callers; a
caller that steps by anything other than 1 needs the split to be scrambled,
not just correct in isolation.

## `duplicate_rate`'s and `dropout_rate`'s literal config values, checked against a real load, not just reasoned about

**51. The default `configs/e1_dropout25.yaml` (200 patients, 10% duplicate
rate, 8 villages, 2 facilities) produced 220 patient records, 621 referrals,
2039 transition events on seed 42 — close to D31's "~200 patients / ~600
referrals" estimate without being tuned to hit it exactly (referral count
per patient record is drawn from a `[1,2,3,4,5]` distribution weighted
toward 2-3, not fixed).** A full load of that cohort through the real
`/sync/push` (`server/scripts/load_cohort.py`, no `docker compose run
--rm api sh -c "time ..."` available in the slim image — `time` isn't
installed — so the loader's own `elapsed_seconds` field is the only source
for this number) took **~38 seconds**, with zero non-`accepted` results.
Phase 8's E1 budget is 18 cells × 3 seeds = 54 loads (ADR-015); 54 × 38s is
about 34 minutes of load time total, comfortably inside a working session —
the honest number ADR-015 required P7.1 to produce, not a projection. Also
checked directly, not assumed: zero `ESCALATED` events anywhere in a freshly
migrated, freshly loaded database (`SELECT count(*) FROM referral_event
WHERE to_state='ESCALATED'` → 0), and every loaded referral's
`origin_org_id` equals its own generated ASHA's `org_unit_id` (joined and
compared row by row, not sampled).

## `server_lamport` is a GLOBAL max, not scoped to a referral or an org — a test that assumes otherwise gets an unpredictable tie

**52. `client/tests/two-device-conflict.spec.ts`'s first draft relied on
two devices "naturally" landing on the identical lamport for the same
transition — device 2 pulls device 1's create event, merges its local
lamport up to that event's lamport, then both independently compute
`nextLamport()` for the same next transition. That only produces a real
tie in isolation.** `app/sync/push.py::handle_push` computes
`server_lamport` as `merge_lamport(SELECT MAX(lamport) FROM
referral_event, [op.lamport for op in ops])` — a single number over the
**entire table**, not filtered by referral, entity, or org — and
`client/src/sync/engine.ts`'s `flush()` merges that global number into the
device's own local counter after every push, while `pullAndApply()`
separately merges in the max lamport among whatever it pulled (which is
org-scoped, not global, a second and different channel). Under a
full-suite Playwright run, device 1 and device 2 pick up noise from every
other concurrently-running spec's ops through these two different
channels, by different amounts, and the intended tie silently becomes an
ordinary race — this spec passed 5/5 in isolation and failed roughly half
the time as part of the full suite, with device 2 coming back
`accepted_stale` (ADR-003 row 4) instead of the intended `conflict` (row
5). **Fixed** by forcing device 2's local lamport, via direct `sync_meta`
manipulation, to something guaranteed to be no less than
`current_lamport` regardless of noise — the same deterministic technique
`server/scripts/demo_walk.py` already uses server-side (hand-picked
lamport values 5/10/11/20 to hit specific ADR-003 rows on purpose) — so
row 5 holds by construction rather than by hoping two independently-noisy
counters happen to agree.

**A second, sharper version of the same bug bit the fix itself.** The
first attempt forced device 2's lamport to a hardcoded constant
(1,000,000). That passed for a while, then started failing again — not
because the fix was wrong in kind, but because `server_lamport` being
GLOBAL and PERSISTENT means every earlier run of this exact spec, against
this same never-reset dev database, had already pushed the shared ceiling
above 1,000,000 too, so device 1's own baseline (merged from that same
climbing ceiling on its own create push) eventually caught up to and
passed the constant. **Fixed for real** by reading device 1's actual
current lamport at the moment device 2's value is set, and adding the
margin to *that* live number instead of to a fixed constant — a hardcoded
"big enough" number decays on a persistent shared counter; a live-relative
margin does not, no matter how many times the spec (or the whole suite)
has already run against the same database.

## `identity-review.spec.ts` (pre-existing, untouched) times out intermittently under a 7-worker full-suite run on this machine

**53. Not a P7.2 finding about anything P7.2 built — recorded because it
was seen repeatedly while stress-testing observation 52's fix, and because
"never hide a failure" applies to failures noticed in passing, not only
ones a session caused.** Running the full client Playwright suite with
Playwright's default worker count (7 on this machine) produced an
intermittent `getByText(...).toBeVisible()` timeout (Playwright's 5s
default) in `identity-review.spec.ts`'s existing, unmodified test, roughly
1 run in 3, always at the same assertion (waiting on a pulled/rendered
name after a `create_referral` push). The same class of symptom —
`dashboard.spec.ts`'s "a new breach" test timing out — was also seen once
this session and traced to a stale `LISTEN`/`NOTIFY` connection after
several `docker compose down -v`/`up` cycles; restarting the `api`
container fixed it immediately and reliably. `identity-review.spec.ts`'s
flake did not respond the same way and was not chased further — it is
almost certainly the same root cause as everything else in this section
(this dev machine's `api`/Postgres pair becoming the bottleneck under 7
concurrent Chromium instances, not a defect in the test or the feature it
covers), but that is inference, not something this session verified the
way the `api`-restart fix was verified. Worth a `--workers=` cap or
per-assertion timeout budget if it recurs and starts costing real time —
not done here because it is outside what P7.2 was asked to build.

---

## Phase 8, P8.1 — the experiment harness

**54. Escalation flags a referral; it does not stop the ASHA/MO from doing
the work she was always going to do — and the loader had no way to
express that, so it silently blocked her instead.** `server/scripts/
load_cohort.py`'s `load()` replays each referral's pre-generated events in
order, and each transition op carries the `from_state` the generator
recorded when it built the walk — a static value, fixed at generation
time. `app/sync/push.py`'s coherence check (ADR-003) accepts a transition
only when its declared `from_state` matches the referral's actual
`current_state`. Those two facts are consistent everywhere `load()` was
used before Phase 8, because P7.1's own exit criterion is *zero escalated
referrals before any sweep runs* — nothing ever changes `current_state`
out from under a planned event. Phase 8's whole premise breaks that: the
sweep can (and, at any real SLA window relative to the generator's 1-36h
per-step dwell, routinely does) escalate a referral that was never
actually going to drop out — just running a little behind its own SLA
window for one step — and the instant that happens, `current_state`
becomes `ESCALATED` while the referral's next planned event still says
`from_state="IN_TRANSIT"` (or whatever it was). Coherent-looking, silently
rejected, forever — `load()` tracks this in `report.non_accepted` but
nothing in `experiments/cell.py` surfaced it, so every escalation-on cell
was quietly closing roughly half of what its matched escalation-off cell
closed, at *every* dropout level and *every* seed, and the numbers still
looked like plausible experiment output. **Found by ADR-017's own r=0
identity check** (escalation raised, nobody responds, must produce the
identical closure rate escalation-off does) — a validity check specified
for exactly this class of failure and it did its job the first time it
ran for real. The real client never has this problem: it constructs an
op's `from_state` from whatever its own pulled cache currently holds
(D20), never from a plan fixed in advance — a device is stateful in the
right direction, a mechanical event replayer is not. Fixed in
`experiments/resume.py`'s `reconcile_natural_continuations`, run once
after a cell's simulated horizon and its final sweep: for every cohort
referral still `ESCALATED`, if the generator's own walk had more steps
planned past the breached state, push them, first one's `from_state`
overridden to `"ESCALATED"` (which resolves the open escalation row via
D22, the same mechanism a real device's next honest transition triggers).
A referral with no further planned events is left alone by construction —
it really did drop out, and that is ADR-017's `resume_escalated_referrals`
concern, not this one's. The two functions look similar (same token
cache, same push shape) and are easy to conflate; the difference that
matters is that reconciliation is unconditional (no `response_rate`
draw — nothing was actually interrupted) while resumption is the
probability-`r` recovery of a genuine drop-out.

**55. PyJWT validates `exp` and `iat` against the real system clock, with
no way to hand it an injected one — invisible under `CLOCK_MODE=real`,
silently wrong under `CLOCK_MODE=simulated` in *both* time directions.**
Every login-then-request round trip before Phase 8 ran under
`CLOCK_MODE=real`, where `RealClock.now()` and PyJWT's own internal
`datetime.now()` check agree by construction, so `app/api/auth.py`'s
plain `jwt.decode(...)` had never been exercised against a clock that
disagreed with real wall time. P8.1's runner sets `CLOCK_MODE=simulated`
with `SIM_START` at the cohort's own generated start (necessarily in the
past relative to real "now," often by months) and then steps the *same*
clock forward through the whole simulated horizon — so every login mints
a token whose `exp` claim comes from `SimulatedClock.now()`, and that
value crosses real wall-clock "now" partway through a long-running cell.
Before it crosses: the token's `exp` is in PyJWT's own idea of the past,
so every request looks expired and `get_current_user` rejects it outright
— found first, and looks like an ordinary expiry bug. After it crosses:
the *same* token's `iat` now looks like it was issued in the future
relative to real wall time, and PyJWT raises `ImmatureSignatureError`
instead — a second, differently-shaped failure from the identical root
cause, found only once a cell ran long enough (many simulated days) to
cross the line from the other side, which is exactly what a stepped-clock
experiment does and no earlier phase's simulated-clock use (P5.1's sweep
tests, all short and synchronous) ever did. Fixed by decoding with
`verify_exp=False, verify_iat=False` and checking `exp` by hand against
`clock.now()` (the same injected `Clock` every other module in this
codebase already uses, ADR-001) — `iat` has no equivalent manual check,
because nothing in this app treats "issued in the future" as meaningful
on its own once `exp` already governs the token's valid window. A latent
bug in already-shipped code, not a Phase 8 API change: `CLOCK_MODE=real`
(production, and every earlier phase's test suite) was never affected,
because `RealClock.now()` already agrees with PyJWT's own real-time
checks on both claims. Two new unit tests in `server/tests/unit/
test_auth.py` pin both directions with a real `SimulatedClock` via
`app.dependency_overrides`, not just a mocked JWT.

## Phase 8, P8.2 — a shared RNG stream, re-seeded from the same string on
every call, is not the same thing as one independent draw per referral

**56. `experiments/resume.py`'s `resume_escalated_referrals` built one
`Random(f"{cell_seed}:{cell_id}:resume")` per *call*, not one per *cell* —
so every referral that happened to escalate alone in its own sweep pass
(the common case: the function runs once every `SWEEP_STEP_HOURS`, roughly
a thousand times over a cell's horizon, and escalations trickle in a few
at a time) drew the exact same first value from a stream that had just
been reset to the same seed, instead of an independent
`Bernoulli(response_rate)` trial.** The bug was invisible in P8.1's own
exit criteria — the r=0 identity check never exercises this function at
all (response_rate=0 short-circuits before the RNG is even touched,
`if response_rate <= 0.0: return outcome`), and the r>0 cells still
produced a plausible-looking `raw.csv` row: a number, in range, nothing
raised. It surfaced only once a *second* experiment (E2, P8.2) reused the
same function at a different `response_rate` and every cell — four
different SLA windows, three different seeds — came back with
`closure_rate=1.0`. That was the tell: a real 50% draw does not produce
100% success twelve times running. Tracing it back to E1's own
already-committed `server/results/e1/raw.csv` confirmed the same fault
had been there since P8.1: at a fixed (dropout, seed), `resumed_count`
across r={0, 0.25, 0.5, 0.75} went 0 → *all* escalated referrals → some
partial number → *all* again, for one seed, while a **different seed at
the identical r=0.25** showed 0 — the signature of "whichever fixed
draw this (cell_seed, cell_id) pair happens to produce, decides
everything," not of a working probability. Fixed by keying each
referral's own `Random` off the referral's own id —
`Random(f"{cell_seed}:{cell_id}:resume:{referral_id}")`, constructed fresh
inside the per-referral loop rather than once per call — so a referral's
draw depends only on itself, never on how many other referrals happened
to escalate in the same sweep pass or how many times the function had
already been called before it. I7 is untouched: the same seed still
produces the same per-referral outcome, because the key is still fully
deterministic — it was the *sharing* of one stream across independent
referrals that was wrong, not the use of a seeded RNG itself. **Cost:**
E1's full 45-cell grid and E2's full 12-cell grid both had to be
re-run after the fix (E1: ~66 minutes; E2: ~3.9 hours at the corrected
`E2_LOAD_STEP_HOURS=12` — see observation 57) — real wall-clock time
lost to a bug that produced clean exits and readable numbers the entire
time. Nothing about ADR-017's own identity check was wrong; it simply
never had a reason to look at the one code path this bug lived in.

## Phase 8, P8.2 — a swept parameter can't move a metric that a cheaper
harness knob already decided for it

**57. E2 sweeps `sla_profile.max_hours` over {24, 48, 72, 120} hours to
measure the alert-fatigue frontier, but the harness loads a cohort in
batches of `LOAD_STEP_HOURS` (168, weekly — P8.1's own tuning for E1's
wall-clock budget) between sweeps. 168 exceeds every value E2 sweeps, so
a referral's push-batching lag alone was long enough to trigger a breach
regardless of which window was configured — the window never got a
chance to matter.** Found the same way observation 56 was: not by
inspection, but by running one cell at each end of the swept range (24h,
120h) before trusting the full grid, and comparing the actual
`(referral_id, breached_state)` rows the two runs produced — byte for
byte identical, for two windows five times apart. `LOAD_STEP_HOURS`
governs `state_entered_at`'s lag (documented in `experiments/grid.py`
since P8.1, in the context of E1's own `mean_hours_to_detection` bias),
but nobody had reasoned through what that lag does to an experiment whose
*entire x-axis* sits inside it. Fixed with a second, E2-only constant
(`E2_LOAD_STEP_HOURS=12`, below the narrowest swept window) — cells got
noticeably slower (~90s to ~1080-1210s each) but the window began to
matter again: escalation counts and false positives dropped and started
differing between cells rather than repeating the same numbers four times.
A second, separate finding sits underneath this one and is *not* a bug:
even after the fix, `escalations_raised`/`escalations_false_positive`
still don't move much across {24..120}h, because (a) a referral that
genuinely never sends its next event will breach *any* window eventually,
given a long enough horizon, and (b) `generator/timeline.py`'s per-step
dwell time (`rng.uniform(1, 36)` hours) rarely produces a "slow but alive"
referral whose real delay exceeds even the narrowest swept window. That
second fact is a property of the approved cohort and the approved sweep
range meeting each other, not something this session changed or could
fix without changing either — reported as-is in `docs/
Observations_for_report.md`, not smoothed over.
