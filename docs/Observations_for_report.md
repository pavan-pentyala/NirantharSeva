# Observations for the report

**What this file is for:** a running collection of results, discussions, and
framing decisions that belong in the final written report (Chapters 3-5,
appendices) — as opposed to `docs/OBSERVATIONS.md`, which is engineering
memory for the next coding session, or `PROGRESS.md`, which is overwritten
every session. Nothing here is derivable from the code alone; it is the
*why* and the *so what* a panel or a reader would ask for.

**Not gitignored, unlike `docs/LEARNING_PLAN.md`/`docs/PROJECT_REFERENCE.md`** —
this is report material, not a personal study aid, so it is committed.

**Append-only per session.** Each session's report-worthy material gets its
own dated section at the bottom. Earlier sections are never rewritten —
if a later session supersedes an earlier claim, it says so explicitly and
links back, the same convention `docs/OBSERVATIONS.md` uses.

---

## 2026-08-23 — Phase 7, P7.3 (review-hardening backlog)

Six items from the P7.3 backlog (`docs/PHASE7_PLAN.md`) were report/doc
paragraphs by design — no code. They are recorded here as the actual report
material, not as a checklist.

### The SLA window is a swept parameter, not a fixed configuration

Nowhere in this system is 120 hours *the* SLA window. The seeded profiles
(`app/seed.py`) give each escalatable state its own real window — 24h for
CREATED, 48h for IN_TRANSIT, 24h for ARRIVED, 48h for TREATED, 72h for
BACK_REFERRED. 120 hours appears only as one cell of E2's planned sweep over
{24, 48, 72, 120} hours, testing how escalation behaviour changes as the
window widens or tightens — it is an experimental input, not a configured
default, and the report must not imply otherwise anywhere it restates this
number.

### `SLA_SCALE` is an experiment mechanism, not a demo shortcut

`SLA_SCALE` (`app/domain/escalation.py`, applied inside the breach query at
query time, never altering the stored `max_hours` column) exists so E2 can
run its three-seed sweep without three seeds' worth of wall-clock hours per
cell. The committed default is `1.0` (`.env.example`) — production-real
hours — and every demo run that sets it smaller is deliberately simulating
compressed time, the same problem and the same answer as ADR-001's injected
`Clock`. The report should present it that way: a parameter that makes a
week of simulated SLA behaviour observable in seconds, not a hack to make
demos look responsive.

### Single-hop referral is a named limitation, not an oversight

A referral's `origin_org_id → target_org_id` is exactly one hop, set once at
creation (P7.3's B1 now validates that the target is a real ancestor of the
origin, but does not add a second hop). A referral that needs to go on from
a PHC to a district hospital is not a modelled transition in this system —
it would have to be a second, independent referral, with no structural link
back to the first. This matters for how E1's loop-closure rate should be
read: it measures completion of one hop, not of a patient's full journey
through the health system, and the report should say so explicitly rather
than let a reader assume multi-hop chains were tried and excluded for
performance reasons. Multi-hop referral was frozen out of scope from the
start (`docs/IMPLEMENTATION_PLAN.md`), not discovered to be infeasible.

### Admin and master-data provisioning is a stated scope boundary, not a gap

There is no API for creating an `org_unit` or an `app_user`, and no phase
before Review-II adds one — this is D29, taken deliberately
(`docs/PHASE7_PLAN.md`), not an accidental omission a panel should read as
unfinished work. What exists instead: an idempotent `app/seed.py` using
stable UUIDv5 ids so re-seeding never duplicates rows, argon2id-hashed
passwords for the fixture users, and — at cohort scale — the P7.1 generator
writing its own `district.csv`/`users.csv` and `server/scripts/
load_cohort.py` loading them by direct SQL. The concrete future work this
implies, and which the report should name rather than leave vague: a
`village → facility` catchment table with an `is_default` flag — the table
an admin screen would exist to edit, if this became a real deployment
rather than a case study.

### The three offline-demo paths, ranked

`docs/IMPLEMENTATION_PLAN.md` §14 already ranks these; P7.3 (C5) additionally
made `make demo` print them so the sequence is not improvised while being
watched (see the `demo` target in `Makefile`). For the report:

1. **Browser DevTools "offline" checkbox** — `context.setOffline(true)` in
   Playwright terms. The primary demo path: instant, reliable, and the exact
   mechanism the automated offline test suite (`offline-sync.spec.ts`) uses,
   so a live demo and a passing CI test are provably the same code path.
2. **`docker compose stop api`** — the browser still believes it has a
   network (`navigator.onLine` stays true), so this exercises the *retry*
   path rather than the *offline-detection* path: a request is attempted,
   fails, and the outbox's backoff logic takes over. This is also how E4's
   `docker kill api` fault-injection experiment works, so it is worth
   demoing separately from DevTools-offline precisely because it proves a
   different code path.
3. **A real phone in airplane mode**, added to the home screen as a PWA —
   the only one of the three that is not simulated in any way. Slowest to
   set up, and the fallback of last resort (the owed real-phone clip,
   `PROGRESS.md`'s open item) if a live demo cannot be risked.

### Decision recorded: no "simulate offline" button was built, and why (P7.3 C6)

`navigator.onLine` is read at three call sites in `client/src/sync/
engine.ts` (lines 120, 194, 284 as of this session). A hand-rolled
fake-offline toggle would have to be threaded through all three, and the
moment such a switch exists in the shipped app, a panel can reasonably ask
whether the offline demo is genuine or staged. Cutting the actual network —
any of the three paths above — costs one keystroke or one command and
is unarguable by construction. This was a deliberate decision, not an
unbuilt feature, and the report should state it as such if the question
comes up.

---

## 2026-08-23 (later) — Phase 8 planning (Opus, plan-only)

No code this session. Three documents produced: `docs/PHASE8_PLAN.md`,
`docs/decisions/ADR-016.md`, `docs/decisions/ADR-017.md`. Two findings
below belong in the report regardless of how Phase 8 turns out.

### The headline experiment had a hole in it, found before it was run

This is the most important thing to say honestly in Chapter 4, and it is a
better story than the result it replaced.

E1 was specified as *escalation {on, off} × dropout {10, 25, 40}%*,
reporting loop closure rate. Planning it revealed that **the experiment as
written could not produce a non-null result**. Escalation in this system
*surfaces* a stalled referral — the sweep writes an `escalation` row and a
`SYSTEM`-authored event, and the dashboard lights up. It never *moves* the
referral. What moves it is a supervisor reading Screen 4 and telephoning an
ASHA: a human act, outside the software, and deliberately so (SMS/IVR is on
the frozen scope list, so an automated nudge was never in scope).

Meanwhile the generator models drop-out as a timeline that simply stops.
Nothing in the generator, the loader, or the server ever restarts a stopped
timeline. So escalation-on and escalation-off would have produced
*identical* closure rates — not as a finding, but as an artefact of a
harness incapable of showing anything else.

The resolution (ADR-017) splits E1 into two results that are never blended:

- **Measured** — detection rate, time-to-detection, and escalation volume.
  Properties of code that actually ran, with no assumption anywhere.
- **Modelled** — loop closure as a function of an assumed
  `escalation_response_rate`, swept over {0, 0.25, 0.5, 0.75}, with the
  assumption stated in every caption and axis label.

The reportable claim therefore changes shape: not "escalation improves loop
closure by X%", but "escalation improves closure by X% *if supervisors act
on a quarter of alerts*, by Y% *if they act on half*" — a frontier a reader
can locate their own field reality on. The sentence worth defending in
Chapter 4 is the break-even one: the responsiveness below which escalation
costs more attention than it returns.

**Why this is worth a paragraph rather than a footnote.** A panel member who
has run a simulation will ask "what in your model responds to an alert?" —
and the answer being *already in the design, with the assumption swept
rather than assumed* is a much stronger position than discovering the gap
under questioning. It also generalises: a system that measures a
notification mechanism must be explicit about whether it is measuring
notification or measuring the response to it, because those are different
claims and only one of them is usually in evidence.

### The instrumentation plan contradicted itself, and the schema settled it

`docs/IMPLEMENTATION_PLAN.md` §12 and §13.1 give incompatible answers for how
one experiment cell is isolated from the next: §13.1 says a fresh database
per cell via container teardown, §12 says a `run_id` column is "how you run
eighteen E1 cells without eighteen databases."

The schema decided it. Migration `0003`'s docstring drew a line at the time
it was written — `referral_event` and `sync_conflict` carry `run_id` because
they "record something happening during a specific run"; cache and lookup
tables (`referral`, `patient`, `escalation`) do not. So `run_id` cannot
scope `app/domain/escalation.py`'s sweep, which selects from `referral`. In
a shared database the sweep would escalate other cells' referrals, and E1's
headline number would be measuring cross-contamination.

Worth recording in the report as a small, concrete instance of a general
point: **an instrumentation decision taken in week 3 constrained an
experiment design in week 9, and the constraint was invisible until the
experiment was planned in detail.** The resolution (ADR-016 — one database
and one OS process per cell) also documents a related trap: `app/db.py`
binds its engine at import time and `app/api/sync.py` passes the
module-level session factory directly into `handle_push` rather than through
FastAPI's dependency system, so a harness that relied on
`dependency_overrides` would have redirected reads and not writes — and
produced plausible, wrong numbers with nothing failing.

---

## 2026-08-23 (later still) — Phase 8, P8.1 implementation (Sonnet)

### E1's first real run silently produced a wrong headline number, and the harness's own internal check caught it before a table did

`experiments/runner.py` ran the full E1 grid (45 cells: 3 dropout levels ×
3 seeds escalation-off, plus 3 dropout × 4 response rates × 3 seeds
escalation-on) twice before it produced a result worth keeping. The first
run finished cleanly — exit 0, all 45 rows written, nothing crashed — and
would have been indistinguishable from a correct result by looking at
`raw.csv`'s shape alone. ADR-017's r=0 identity check (escalation-on with
nobody responding to an alert must produce *exactly* the closure rate
escalation-off does, since raising an alert nobody acts on cannot close a
loop) failed on every one of the nine dropout × seed pairs it applies to,
and by a large, consistent margin — escalation-on's closure rate was
roughly half of escalation-off's, every time, not noisy in either
direction. That consistency is what made it legible as a real bug rather
than sampling variance: a harness contaminating its own measurement
produces a *pattern*, not scatter.

The mechanism (`docs/OBSERVATIONS.md` observation 54) was that the
cohort loader replays each referral's events with a `from_state` fixed at
generation time, and once the sweep escalates a referral that was never
actually going to drop out — just running a little behind its own SLA
window for one step, a routine timing accident at any real SLA scale —
its next planned event is silently and permanently rejected, because the
referral's real `current_state` has moved to `ESCALATED` underneath a
plan that doesn't know that happened. The system's own real client never
has this problem, because it always builds an outgoing transition from
whatever state it last pulled, not from a plan decided in advance; the
experiment harness, standing in for many real devices at once, took a
shortcut a real device never takes, and the shortcut was invisible until
an experiment used escalation *and* checked its own arithmetic against a
known-should-be-identical baseline.

**Why this belongs in the report, not just the fix log.** It is a clean,
concrete illustration of a broader point worth making in Chapter 5's
discussion of validity: a headline number that "runs cleanly" is not
evidence that it is correct, and the difference between the two was
entirely a designed internal consistency check, not code review, not a
unit test on the harness (there wasn't one, and one testing "does
escalation ever get resolved" in isolation would not have caught this —
the bug only appears once a referral that was *never* going to drop out
also gets escalated, an interaction between two mechanisms, not a defect
in either one alone), and not eyeballing the numbers (the second run's
`closure_rate` values are not obviously "more correct" looking than the
first run's — both are plausible-looking fractions between 0 and 1). The
identity check existed specifically because ADR-017 anticipated that E1's
harness could contaminate itself and said so before any code ran; it is
the reason this is a footnote about a caught bug rather than an
unexamined headline number in Chapter 4.

### PyJWT and a simulated clock disagree about what time it is, in both directions

A second, unrelated defect surfaced while getting the harness working at
all: `app/api/auth.py`'s token validation used PyJWT's built-in `exp`/`iat`
checks, which compare against the real system clock unconditionally —
there is no PyJWT option to hand it an injected clock. Every earlier
phase's tests ran under `CLOCK_MODE=real`, where this is invisible by
construction (the real clock and PyJWT's internal check are the same
clock). P8.1's stepped-clock runner is the first caller to mint a token
under `CLOCK_MODE=simulated` and then keep advancing that same clock long
enough to cross real wall-clock "now" mid-run — before crossing, every
token looked pre-expired; after, the identical token's `iat` looked
issued in the future, and PyJWT rejected it for the opposite reason.
Worth a paragraph in whichever chapter discusses the injectable-clock
design (ADR-001): the clock discipline the codebase enforces everywhere
else (no direct `datetime.now()` calls, checked by a CI grep) turned out
to have one gap that no amount of grepping this codebase's own source
would find, because the offending clock read is inside a third-party
library's own code, not this project's.
