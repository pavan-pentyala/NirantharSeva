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
