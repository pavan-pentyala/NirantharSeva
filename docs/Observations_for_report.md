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

### Decision recorded: no "simulate offline" button was built, and why

`navigator.onLine` is read at three call sites in `client/src/sync/
engine.ts` (lines 120, 194, 284 as of this session). A hand-rolled
fake-offline toggle would have to be threaded through all three, and the
moment such a switch exists in the shipped app, a panel can reasonably ask
whether the offline demo is genuine or staged. Cutting the actual network —
any of the three paths above — costs one keystroke or one command and
is unarguable by construction. This was a deliberate decision, not an
unbuilt feature, and the report should state it as such if the question
comes up.
