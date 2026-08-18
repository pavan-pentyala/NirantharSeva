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
