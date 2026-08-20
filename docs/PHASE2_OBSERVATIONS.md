# Phase 2 — implementation observations

**Status:** Phase 2 complete (P2.1 `4dd737b`, P2.2 `5802b13`+`03fdbcf`), CI green.
**What this file is for:** engineering memory. Things learned by building P2.1
and P2.2 that are not derivable from the code, the ADRs, or the git history.
**Who it is for:** the next session. Read it before touching `server/`.

**This file is append-only per phase.** Phase 3 adds its own section at the
bottom; it never rewrites Phase 2's. `PROGRESS.md` is overwritten every session
and cannot hold any of this.

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
