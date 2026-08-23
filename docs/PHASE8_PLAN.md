# Phase 8 plan — the experiment harness and the E1–E6 runs

**Status:** Planned, not started. Written 2026-08-23 (Opus, plan-only
session — no code, no dependency installed, no config file created).
**Source of truth for *what*:** `docs/IMPLEMENTATION_PLAN.md` §13, plus §12
for the instrumentation it assumes. Forty-five lines, two tables — this
file supplies the rest, as `docs/PHASE7_PLAN.md` did for §11.
**Source of truth for *how you work*:** `docs/HANDOFF_CLAUDE_CODE.md`.
**Read before starting P8.1:** ADR-001 (the clock — this is the phase it was
built for), ADR-015 (a cohort loads by replay), **ADR-016** and **ADR-017**
(this phase's own), `docs/PHASE7_PLAN.md`'s "Traps", and
`docs/OBSERVATIONS.md`'s Phase 7 section (observations 47–53).
**Design bundle:** not involved. Phase 8 adds no screen.

---

## Context

Phase 8 is execution, not construction — §13 opens with "By now the code is
frozen except for bug fixes." That sentence is a constraint on this plan,
not just a description: where a decision here could have been resolved by
editing `server/app/`, it was resolved another way, and ADR-016 records the
one place that trade was closest.

Four things about the starting state materially shaped the plan.

**`experiments/` is an empty `.gitkeep`.** Everything in §13.1 — the runner,
the per-cell lifecycle, the clock stepping, the metrics collection,
`analysis.py` — does not exist. This is the phase's real build.

**E4 is already four-fifths evidenced, and nobody has said so.** §13.3's
five-row fault matrix maps onto tests built in Phases 1–7:

| §13.3 fault | Already implemented in |
|---|---|
| Partition mid-sync | `client/tests/offline-sync.spec.ts` |
| API killed mid-push | `server/tests/fault/kill_api.sh` |
| Client killed mid-push | `client/tests/client-kill-resume.spec.ts` |
| Duplicate replay ×5 | `tests/integration/test_push_idempotent.py`, and P7.2's `tests/property/test_push_idempotency.py` for the arbitrary-retry generalisation |
| Concurrent offline edit | `client/tests/two-device-conflict.spec.ts` (P7.2) |

So E4 in Phase 8 is **evidence collection and tabulation**, not test
writing. Budget it accordingly, and do not let it become a reason to write
a sixth fault test nobody asked for.

**§12 and §13.1 contradict each other on cell isolation**, and `referral`
has no `run_id` column to make §12's version work. Resolved by D35 and
recorded in ADR-016, which also documents the import-time engine binding in
`app/db.py` that makes the process boundary non-negotiable rather than
stylistic.

**E1 as literally specified cannot produce a non-null result.** Escalation
surfaces a stalled referral; it never moves one. With nothing in the
simulation responding to an alert, escalation-on and escalation-off give
identical closure rates by construction. Resolved by D34 and recorded in
ADR-017. This was the single most important thing this planning session
found, and it would have been discovered in week 9 otherwise, with no time
to do anything but report the null.

**One correction to carry forward.** `PROGRESS.md` records "54 loads (18
cells × 3 seeds)" as the Phase 8 budget. That figure does not match the
specs in §13.2. The real count is below, and it is larger, because of
ADR-017.

---

## Decisions taken with the user

Continuing D1–D33 (`docs/PHASE2_PLAN.md` … `docs/PHASE7_PLAN.md`).
All four answered 2026-08-23.

### D34 — E1 reports measured detection and modelled recovery, separately. See **ADR-017**.

Measured: detection rate, time-to-detection, escalation volume — properties
of code that ran. Modelled: loop closure as a function of an assumed
`escalation_response_rate` swept over {0, 0.25, 0.5, 0.75}, labelled as an
assumption in every caption. The two are never blended into one figure.
E1 grows from 6 cells to 15.

### D35 — one database and one OS process per experiment cell. See **ADR-016**.

`DROP DATABASE` / `CREATE DATABASE` per cell, `DATABASE_URL` set before any
`app.*` import, the real FastAPI app driven through an in-process ASGI
transport. Supersedes §13.1's `docker compose down -v && up` and §12's
"eighteen cells without eighteen databases". `run_id` keeps its labelling
job and does not become an isolation mechanism.

### D36 — `results/` is committed, minus bulk per-request dumps

`docs/PHASE7_PLAN.md` deferred this to Phase 8 explicitly ("Phase 8 must
[resolve it], before it generates anything it wants to keep"). Resolution:
**un-gitignore `results/`**; commit `raw.csv`, the derived tables and
figures, `cells.resolved.yaml` and `manifest.json` — everything Chapter 4 is
built from, so no number in the report requires a thirty-minute re-run to
show. Keep raw per-request timing dumps out (they are large, and
regenerable from seed + config under I7). §12's "commit the results
directory" is honoured for everything that is actually evidence.

### D37 — E2's SLA sweep sets every profile's `max_hours` to the cell value

Uniform, not proportional. All five escalatable `sla_profile` rows take the
cell's window for that cell, so the x-axis means exactly one thing and the
alert-fatigue frontier is readable. This is already how P7.3's C1 paragraph
describes 120h ("one cell of E2's sweep"). The seeded per-state values
(24/48/24/48/72) remain what `app/seed.py` ships and what the demo uses;
only experiment cells override them.

---

## Decisions taken alone (handoff §2), flagged so they can be overruled

### D38 — a cell runs in a child process, and the runner is a parent orchestrator

D35 settled *per-cell database + in-process ASGI*. This is the mechanism
that makes it actually work, and it is a structural choice rather than a
naming one, so it is flagged here rather than buried.

`app/db.py` creates its engine at import time and `app/api/sync.py` passes
the module-level `async_session_factory` straight into `handle_push` — not
through `Depends`. FastAPI's `dependency_overrides` therefore cannot
redirect the **push** path to a per-cell database, only the pull path. A
single-process harness would have to either edit that route (frozen code,
I1's transaction boundary) or monkeypatch module globals (silent failure if
one call site is missed). Both are worse than a process boundary.

So: `experiments/runner.py` is the parent — it plans cells, creates and
drops databases, spawns one child per cell, captures the child's output,
and appends rows to `raw.csv`. `experiments/cell.py` is the child entry
point — it reads its cell spec from argv/stdin, sets nothing that isn't an
env var, imports `app.*` only after `DATABASE_URL` is set, runs the cell,
and prints one JSON row on stdout. **This is the pattern the test suite
already uses** (`docker compose run --rm -e DATABASE_URL=...nirantharseva_test
api sh -c "... pytest"`), not a new one.

### D39 — `SLA_SCALE` is pinned to `1.0` for every experiment process

Simulated time does the compression in Phase 8; the scale factor does not.
If both compress, E2's {24, 48, 72, 120}h axis reports a window that is not
the window, and E1's time-to-detection is in units nobody can name. The
runner **asserts** `settings.sla_scale == 1.0` in each child and refuses to
run otherwise, rather than trusting the environment. Observation 37 is the
supporting argument: fractional scales are a live silent-truncation hazard
in exactly this query.

`SLA_SCALE` remains what it is for demos, and P7.3's C2 paragraph
(`docs/Observations_for_report.md`) already frames it correctly for the
report — this decision does not change that framing, it keeps the two uses
from colliding.

---

## D40 — sub-phase split. **Approved by the user 2026-08-23** (handoff R5)

Phase 8 is too big for one session: a harness, six experiments, an analysis
layer, a load test, and a tool (k6) that has never been in the repository.

| Sub-phase | Builds | Independently verifiable by |
|---|---|---|
| **P8.1** | `experiments/` package: parent runner, child cell, per-cell DB lifecycle, `SimulatedClock` stepping, the ADR-017 response model, metrics collection — proved end to end by running **E1** in full | E1's `raw.csv` has all 45 rows; re-running one cell with the same seed reproduces its row byte-identically; the `r = 0` identity check holds |
| **P8.2** | **E2, E3, E6** on the P8.1 harness, plus `analysis.py` | Each experiment's `raw.csv` + derived tables exist; `analysis.py` regenerates every table from `raw.csv` alone, with the database gone |
| **P8.3** | **E4** evidence collection and tabulation; **E5** k6 load harness, before/after indexing, `EXPLAIN ANALYZE` | E4's five-row matrix filled from real recorded runs; E5's p50/p95 per endpoint, both index states |

P8.1 is the large and risky one — everything after it reuses the harness.
P8.3 depends on nothing in P8.2 and could be cut or deferred to Phase 9
without affecting E1/E2/E3/E6.

### D41 — deployment belongs to Phase 9, not Phase 8. **Decided with the user 2026-08-23.**

The phase map (§4) lists "deploy" under P8; §14 puts deployment in Phase 9
alongside the demo script and the recorded clip. They disagree, and the
disagreement is resolved in §14's favour: Phase 8 is already three
sub-phases of experiment work, deployment is not an experiment, and §14
already treats local `docker compose up` as the *primary* demo path with a
deployed URL secondary. **Phase 8 ships no deployment.** The phase map's P8
row is the stale one; §14 governs.

---

## Contracts fixed now, so they are not invented at 1 a.m.

### The runner CLI

```
python -m experiments.runner --exp E1 --out results/e1/ \
    [--seeds 42,7,13] [--cell <cell_id>] [--dry-run] [--keep-db]
```

`--dry-run` prints the resolved cell plan and exits without touching a
database — the cheap way to check a grid before spending forty minutes on
it. `--cell` re-runs exactly one cell (a failed one, without the other
sixty-two). `--keep-db` leaves a cell's database behind for inspection.

### The analysis CLI — reads `raw.csv`, never the database

```
python -m experiments.analysis --exp E1 --in results/e1/ --out results/e1/
```

### What a run writes into `--out`

| File | Contents |
|---|---|
| `raw.csv` | One row per (cell, seed). The only input `analysis.py` is allowed to read. |
| `cells.resolved.yaml` | Every cell's fully expanded parameters and the seeds actually used. **This is I7 for Phase 8**, the same role `config.resolved.yaml` plays for the generator. |
| `manifest.json` | git SHA, `alembic heads`, start/end timestamps, total wall seconds, per-cell wall seconds, harness version. |
| `table_*.csv`, `figure_*.png`, `summary.md` | Written by `analysis.py`. What Chapter 4 pastes. |

### `raw.csv` columns

Common to every experiment: `exp, cell_id, seed, run_id, wall_seconds,
cohort_patients, cohort_referrals, cohort_events, git_sha, alembic_head`.

| Exp | Additional columns |
|---|---|
| E1 | `escalation_on, dropout_rate, response_rate, referrals_total, referrals_closed, closure_rate, dropped_total, escalations_raised, escalations_true_positive, escalations_false_positive, dropped_detected, detection_rate, mean_hours_to_detection, resumed_count, resumed_and_closed` |
| E2 | `sla_window_hours, response_rate, referrals_total, referrals_closed, closure_rate, escalations_raised, escalations_per_100_referrals, escalations_false_positive` |
| E3 | `threshold, precision, recall, f1, auto_resolution_rate, blocking_recall, miss_normalize, miss_blocking, miss_scoring, miss_threshold` |
| E6 | `referrals_total, closed, lost, stuck_open, escalated_unresolved, unresolvable_fraction, identity_review_pending` |

E5 writes k6's own JSON summary plus `explain_open_loops_{before,after}.txt`
rather than a `raw.csv` row per cell.

### The cell loop, in order

```
parent: DROP DATABASE IF EXISTS / CREATE DATABASE  ns_e1_c07_s42
parent: spawn child with DATABASE_URL=...ns_e1_c07_s42, SLA_SCALE=1.0, RUN_ID=e1_c07_s42
  child:  assert settings.sla_scale == 1.0                      (D39)
  child:  alembic upgrade head; python -m app.seed
  child:  generator -> cohort for this (config, seed)           (in-process, not the CLI)
  child:  apply cell overrides (E2: sla_profile.max_hours)      (D37)
  child:  clock = SimulatedClock(cohort_start)
  child:  loop until horizon:
  child:      load.upto_device_time(clock.now())                (push what has "happened")
  child:      if escalation_on: sweep(session_factory, clock)
  child:      if escalation_on and r > 0: draw + resume escalated referrals   (ADR-017)
  child:      clock.advance(step_hours)
  child:  collect metrics; verify_replay; print one JSON row on stdout
parent: append row to raw.csv; DROP DATABASE (unless --keep-db)
```

### Cell counts and the wall-clock budget

| Exp | Cells | × seeds | Cohort loads |
|---|---|---|---|
| E1 | 15 (3 escalation-off + 3 dropout × 4 response) | 3 | 45 |
| E2 | 4 | 3 | 12 |
| E3 | 1 (six thresholds scored offline from one pass, per `e3_draft_sweep.py`) | 3 | 3 |
| E6 | 1 | 3 | 3 |
| **Total** | | | **63** |

E4 needs no cohort load. E5 needs one loaded database, twice (before and
after indexing).

At P7.1's measured ~38s per load over HTTP that is ~40 minutes of loading;
ADR-016's in-process transport should beat it. **P8.1 must re-measure and
record the real number** — the same discipline D31 imposed on P7.1, and for
the same reason: a budget built on an estimate is not a budget.

**Seeds: 42, 7, 13.** 42 and 7 are already exercised by P7.1's
reproducibility checks.

---

## What Phase 8 must prove, and why each check exists

| Check | Guards against |
|---|---|
| One cell re-run with the same seed → byte-identical `raw.csv` row | I7. Chapter 4 is indefensible otherwise, and it is the cheapest possible check. |
| Escalation-on at `r = 0` closure rate **==** escalation-off closure rate, same dropout and seed | ADR-017's free identity check. A disagreement means state is leaking between cells — the exact failure ADR-016 exists to prevent, and one that produces plausible-looking wrong numbers. |
| `python -m app.verify_replay` clean inside each cell's own database | I3 at experiment scale. A corrupted event log invalidates every metric derived from it, silently. |
| Zero `ESCALATED` events after load, before the first controlled sweep | E1 measuring its own input instead of the system's behaviour. Also catches a stray scheduler container (observations 35, 39). |
| `analysis.py` regenerates every table with the databases dropped | That `raw.csv` is genuinely sufficient — the difference between "we have results" and "we have a machine that had results in week 9". |
| Dropout rates in the loaded cohort match the cell's config | A knob that does not move the data invalidates every E1 cell at once. (P7.1's own check, re-asserted per cell.) |
| A child process that dies produces a loud failure and no `raw.csv` row | A silently missing row that `analysis.py` then averages over — a wrong mean with no error anywhere. |
| Three seeds produce three *different* cohorts | A standard deviation of zero that looks like precision and is an artefact of re-running one deterministic cohort. |

---

## Traps for this phase

- **`SLA_SCALE` must be exactly `1.0` in every experiment process** (D39).
  Assert it in the child; do not trust the environment. Observation 37 is
  what happens when this query meets a fractional scale without the CAST.
- **No scheduler container may be running while experiments run.**
  Observations 35 and 39 are two separate incidents of a `docker compose run
  --rm -d` scheduler outliving its tool call and re-escalating a supposedly
  fresh database. Per-cell database names make contamination structurally
  unlikely, but assert zero pre-existing `escalation` rows anyway — the
  assertion costs one query and has already paid for itself twice.
- **`upto_device_time` has never been exercised.** P7.1 built the parameter
  and tested only `None` ("everything"). The stepped clock loop is its first
  real use, and an off-by-one at the boundary (`<` vs `<=`) silently shifts
  which events land in which step, which moves every time-to-detection
  number without failing anything. Write its test before running E1.
- **Three seeds means three cohorts, not three runs of one cohort.** The
  generator is deterministic by exit criterion — same seed, byte-identical
  output. Re-running one cohort three times yields three identical rows.
- **The generator must still never emit `ESCALATED`.** A P7.1 exit
  criterion, and it matters more here than it did there: E1's entire result
  is about escalations. Re-assert by query per cell, do not inherit the
  guarantee.
- **`identity_review` rows during cohort load are expected, not a bug.** At
  cohort scale with `duplicate_rate`, the review band creates a provisional
  patient *and* queues a review, and `/sync/push` still returns `accepted`
  (P6.2). Harmless noise for E1/E2/E6; the subject matter for E3. Do not
  "fix" it.
- **Un-gitignoring `results/` must not sweep in `server/results/e3_draft/`.**
  The current rule is a bare `results/`, which matches at any depth. P6.1's
  draft sweep output is regenerable scratch and should stay ignored — the
  replacement rule has to be path-anchored, not just deleted.
- **`experiments/` at the repo root needs the same treatment `generator/`
  needed.** Compose mount, `pythonpath`, and `[tool.ruff.lint.isort]
  known-first-party`. Observations 47–48: without it, `experiments`-importing
  tests behave differently inside Docker and on CI's bare `server` job, and
  the divergence is invisible until something imports it in the wrong
  environment. Extend CI's clock-discipline grep to `experiments/` at the
  same time.
- **A child's stderr must reach the operator.** ADR-016 puts each cell in a
  subprocess; swallowing its output turns a crash into a missing row.
- **`MSYS_NO_PATHCONV=1`** on any `docker compose run` passing a container
  path — `--out /app/results/e1/` is exactly the shape observation 41
  describes, and a `--rm` container erases the evidence when it mangles.
- **k6 is genuinely new** (P8.3). Nothing in the repository references it
  today, though `CLAUDE.md`'s stack list names it. It needs a Compose
  service, and it is the one piece of Phase 8 that could surprise on setup
  cost.

---

## Verify Phase 8 yourself, once built

```bash
docker compose up -d --build

# The plan, without spending forty minutes on it
MSYS_NO_PATHCONV=1 docker compose run --rm api \
  python -m experiments.runner --exp E1 --out /app/results/e1/ --dry-run

# E1 for real
MSYS_NO_PATHCONV=1 docker compose run --rm api \
  python -m experiments.runner --exp E1 --out /app/results/e1/

# Reproducibility: re-run one cell, diff its row
MSYS_NO_PATHCONV=1 docker compose run --rm api \
  python -m experiments.runner --exp E1 --out /app/results/e1_recheck/ --cell c07 --seeds 42
# the c07/seed-42 row must be byte-identical to the one in results/e1/raw.csv

# Tables regenerate from raw.csv alone — no database involved
MSYS_NO_PATHCONV=1 docker compose run --rm api \
  python -m experiments.analysis --exp E1 --in /app/results/e1/ --out /app/results/e1/
```

Expect: `raw.csv` with 45 rows; the `r = 0` and escalation-off cells
agreeing on `closure_rate` at every dropout level and seed; `manifest.json`
carrying the git SHA and `alembic_head = 0008`; the re-run row identical.
