# Phase 9 plan — the demo path, the last measurement, and deployment readiness

**Status:** Planned, not started. Written 2026-08-24 (Opus, plan-only
session — no code, no dependency installed, no config file created).
**Source of truth for *what*:** `docs/IMPLEMENTATION_PLAN.md` §14, plus
§8.5 (the recorded clip), §3 (the advisory-lock sentence this phase finally
measures), and §2.2 (the repository layout this phase reconciles).
**Source of truth for *how you work*:** `docs/HANDOFF_CLAUDE_CODE.md`.
**Read before starting P9.1:** `PROGRESS.md` in full, **ADR-018** (this
phase's own), and this file. `docs/OBSERVATIONS.md` observations 54–59 if
you touch `experiments/` or the escalation/dashboard sort.
**Design bundle:** not involved. Phase 9 adds no screen.

---

## Context

Phase 9 is the last build phase, and it is the one whose deliverable is
read by people who will never read the code: a README, a demo that works
while someone is watching, a recorded clip, and a configuration that
answers "could this be deployed?".

Five facts about the starting state shaped this plan, all verified against
the repository rather than assumed.

**The written report is not in this repository, and is deliberately not in
this phase.** Nothing report-shaped exists here — tracked, untracked, or
ignored — beyond `docs/Observations_for_report.md`, which is accumulated
raw material rather than chapters. The phase map's P7 row ("report 50%")
and P9 row ("Chapters 4–5, appendices") both assume a report that this
repository has never contained. **D42 settles this: the report is deferred
until after Phase 9 completes, on the user's own plan, and is out of scope
here.** This is the largest single deviation from the phase map in the
whole project, and it is deliberate, not drift.

**`README.md` is five phases stale.** It states "Phases 0–4 complete",
"Phase 5 … is planned but not built", and lists `anm1`/`supervisor1` as
seeing "Placeholder screens (Phases 5–6)". All seven screens are real;
`PlaceholderPage` was deleted in P6.2. Every phase through P8.3 is built.
This is the first file a panel member, an external reader, or a future
maintainer opens, and it currently describes a half-finished project.

**§3 promised a Chapter 4 sentence that no experiment ever measured.** Line
232: *"measure the cost in E5 and report it — 'the sequencing lock adds Xms
to p95 write latency, accepted in exchange for a gap-free pull cursor' is a
much better Chapter 4 sentence than silence."* E5 as built (P8.3) measured
p50/p95 before and after an **index** change. It never isolated the
**advisory lock**. §3 also names this as one of "the two decisions a sharp
panel member is most likely to probe", so the gap sits exactly where
scrutiny is most likely. **D44: measure it.**

**`make demo` does not do what §14 asks.** §14 specifies: reset the
database, seed a small cohort, open the dashboard, print the scripted
scenario steps. The current target migrates, seeds the six-org fixture
district, and echoes P7.3's ranked offline-demo paths. It does not reset,
does not seed a cohort, does not surface the dashboard, and prints
fallback paths rather than a scenario. Separately, **`make` is not
installed on the reference machine** (a settled decision in `PROGRESS.md`),
so a Makefile target alone cannot be the delivery mechanism.

**Small, real gaps.** `docs/mom/` is empty where §2.2 asks for weekly
minutes — ten weeks, zero files; these are records of real meetings and
belong to the user, not to this phase, but they should not be discovered
missing at submission. `results/` at the repository root is a bare
`.gitkeep` while every actual result lives in `server/results/`, so §2.2's
own layout diagram points at the wrong directory. `temp.txt` is a stray
empty file at the root. `/openapi.json` returns 200, so Appendix A's
artifact half is straightforward whenever the report needs it.

---

## Decisions taken with the user

Continuing D1–D41 (`docs/PHASE2_PLAN.md` … `docs/PHASE8_PLAN.md`).
All four answered 2026-08-24.

### D42 — the written report is deferred until after Phase 9

Not written here, not scaffolded here, not outlined here. The user has his
own plan for it and will share it once Phase 9 is complete. Phase 9
therefore produces **artifacts a report can later draw on** (a verified
demo, a measured number, a production config) but **no report prose and no
chapter structure**. The phase map's P9 row ("Chapters 4–5, appendices") is
superseded on this point, the same way §12's isolation claim was superseded
by ADR-016 — recorded here so a future reader does not treat the phase
map's own row as the live scope.

### D43 — deployment-ready configuration, not a deployed instance. See **ADR-018**.

A production Compose configuration (no bind mounts, no `--reload`, built
static client, unpublished database port, restricted CORS, secrets with no
development defaults), documented deployment steps, and a verification that
it actually starts and serves. No hosting account, no live URL, no
dependency of any deliverable on one. Local Compose stays the primary demo
path per §14; the recorded clip stays the fallback.

### D44 — measure the advisory lock's write-latency cost

Deliver §3's promised sentence with a real number. Same k6 tooling P8.3
introduced, same `request_timing`-is-the-source-of-truth discipline (plan
§12), run twice against a scratch database — once with
`acquire_seq_lock` active, once with it neutralised by a **temporary,
never-committed** local edit. See "Traps" for the two ways this measurement
can produce a meaningless number and the one way it can damage the
repository.

### D45 — Phase 9 splits into three sub-phases (handoff R5)

Approved 2026-08-24. Reshaped from the originally proposed split after D42
removed the report from scope — the original P9.2 was "report assets", and
what remained of it merged with the deployment and measurement work.

| Sub-phase | Builds | Independently verifiable by |
|---|---|---|
| **P9.1** | Deliverable hygiene and the demo path: `README.md` rewritten to reality, stray-file cleanup, the demo runner rebuilt to §14's specification, `docs/DEMO_SCRIPT.md` written and rehearsed | A clean machine runs one documented command and reaches a seeded, demo-ready stack with the scenario printed; the scripted click path has been walked end to end at least once, cold |
| **P9.2** | The advisory-lock measurement (D44) and deployment-ready configuration (D43/ADR-018), including the CORS item deferred from the pre-Phase-9 audit | `server/results/e5_lock/` holds p50/p95 for `POST /sync/push` in both lock states from a write-concurrent profile, with the read endpoints as a noise control; the production Compose file has been brought up and served a request; `git status` is clean and `git diff` empty afterward |
| **P9.3** | Recording scripts and submission readiness: the two-minute demo clip's shot list, the real-phone airplane-mode clip (§8.5), and a submission checklist | Both recording scripts exist with every click path verified working beforehand; the checklist names every Review-III deliverable and its current state |

P9.1 is the highest-value and lowest-risk. P9.3 needs the user's own hands
(a phone, a screen recorder) and cannot be completed by a session alone —
what a session *can* do is make every path it records verified-working
first, so recording is a recording and not a debugging session.

---

## Decisions taken alone (handoff §2), flagged so they can be overruled

### D46 — the demo logic lives in a script; the Makefile target is a wrapper

`make` is not installed on the reference machine (settled decision), so a
Makefile target cannot be the only entry point. The demo's real logic goes
in `server/scripts/demo.sh` (or equivalent), invoked directly *and* by
`make demo`. This also keeps the demo's steps readable and reviewable
rather than buried in tab-indented Make syntax.

### D47 — "reset the database" means drop and recreate the database, not `docker compose down -v`

§14 says "reset the database". Taken literally as a full volume teardown,
`make demo` would stop the client container and any running `vite preview`
mid-preparation, and force a full rebuild before a demo — the opposite of
what a pre-demo command should do. The reset drops and recreates the
application database, then migrates and seeds. The stack stays up.

### D48 — the demo seeds for *states*, not for volume

A demo needs particular referrals to exist in particular states, not a
large cohort. Concretely it needs: referrals visible to the ASHA on Screen
1; at least one advanceable by the MO on Screen 5; at least one already
overdue so Screen 4 is not empty on arrival; one pending identity-review
pair for Screen 6; and — the headline — at least one referral positioned to
breach *during* the demo, so the live-escalation moment (§8's "twenty
seconds the panel will remember") actually fires while someone is watching.
That last one depends on a demo-scale scheduler (`SLA_SCALE=0.0004`,
`SWEEP_INTERVAL_SECONDS=5`, the recipe already proven in `PROGRESS.md`), so
the demo runner is responsible for starting it or for telling the presenter
to, explicitly, not for assuming it.

### D49 — §14's "open the dashboard" is satisfied by printing the URL

Launching a host browser from inside a container is not possible, and the
host-side equivalents are platform-specific (`xdg-open` / `start` /
`open`). The runner prints the dashboard URL and the login prominently
instead. A deliberate, documented deviation from §14's literal wording, not
an omission.

---

## Contracts fixed now, so they are not invented at 1 a.m.

### The demo entry point

```
bash server/scripts/demo.sh          # the real thing
make demo                            # thin wrapper, same behaviour
```

Prints, in order: what it reset, what it seeded (with counts), the URLs and
logins, whether the demo-scale scheduler is running, and the numbered
scenario steps. Exits non-zero if any precondition it needs is missing,
rather than printing a script for a stack that is not ready.

### `docs/DEMO_SCRIPT.md`

The written companion to what the runner prints: the exact click path, who
is logged in at each step, what to say while it happens, roughly how long
each beat takes, what the headline moment is, and — per P7.3's C5 work,
which already ranked these — what to fall back to when a step misbehaves.
This is the document read while rehearsing; the terminal output is the
reminder while presenting.

### The lock measurement's output

`server/results/e5_lock/` — same shape P8.3 established for E5:

| File | Contents |
|---|---|
| `table_e5_lock_latency.csv` | p50/p95 per endpoint, per lock state, from `request_timing` — the source of truth, not k6's own summary (plan §12) |
| `k6_lock_{on,off}_summary.json` | k6's own summaries, kept as a cross-check only |
| `summary.md` | The measured sentence §3 asked for, plus what the number does and does not support |

`RUN_ID=e5_lock_on` / `e5_lock_off` distinguishes the rows, exactly as
`e5_before`/`e5_after` did in P8.3.

### The production configuration

`docker-compose.prod.yml` (or equivalent) plus its documented steps in the
README. ADR-018 fixes what "production" must differ in; the plan does not
restate it here.

---

## What Phase 9 must prove, and why each check exists

| Check | Guards against |
|---|---|
| Every claim in `README.md` verified line by line against the running system | The most-read file in the repository describing a project five phases behind reality — the current state, and the reason this check is per-line rather than "update the status section" |
| One documented command on a clean machine → seeded, demo-ready stack, scenario printed, no remembered manual step | §14's whole stated purpose: not improvising a sequence while being graded |
| The scripted click path walked end to end, cold, at least once before it is called done | A script that reads correctly and does not survive contact with the actual UI |
| The lock measurement uses a **write-concurrent** profile | Measuring a serialisation lock under no contention, which reports ≈0 by construction and would be a fabricated non-finding rather than a real one (see Traps) |
| Read endpoints reported alongside the write endpoint in both lock states | A difference on `/sync/push` that is really just run-to-run noise — if `/dashboard` p95 moves by as much, the measurement is noise, and the control says so |
| `git status` clean and `git diff` empty after the lock experiment | The temporary lock-disabling edit escaping into the repository — an ADR-002/I2-breaking change committed by accident, which is the single worst outcome available in this phase |
| The production Compose file brought up and observed serving | "Deployment-ready" as an unverified claim (ADR-018's own stated standard) |
| Full server suite, client suite, lint, and `verify_replay` green at the end of each sub-phase | The last phase quietly breaking something the previous nine established |

---

## Traps for this phase

- **A lock costs nothing when nothing contends, and P8.3's k6 profile
  creates almost no write contention.** That profile is 10 VUs with
  `sleep(1)` and three reads per single write — under it, concurrent
  `/sync/push` calls barely overlap, so `acquire_seq_lock` would measure
  ≈0ms whether or not it is doing anything. Measuring D44 with the existing
  profile unchanged would produce a number that is technically true and
  substantively meaningless. The lock run needs its own **write-heavy,
  higher-concurrency, no-sleep** profile, and the profile it used must be
  reported next to the number — a serialisation cost is a statement about a
  concurrency level, never a constant.
- **The lock-disabling edit must never be committed.** It neutralises
  ADR-002's guarantee and therefore I2's. Scratch database only, never the
  dev database, and `git status` / `git diff` checked explicitly after the
  run — not assumed. Treat this as the one genuinely dangerous action in
  Phase 9.
- **A CORS restriction can break the local demo.** The client runs on
  `:5173` (dev) and `:4173` (built preview, which `offline-sync.spec.ts`
  needs). Tightening CORS for production must leave both working locally,
  or the last phase breaks the demo it exists to protect.
- **The full Playwright suite rewrites `docs/screenshots/`.** Found during
  the pre-Phase-9 audit: running the client suite modified fourteen
  committed screenshots with no source change, and they had to be reverted
  before committing. Check `git status` for screenshot churn after any
  client test run, and do not commit it as though it were intentional.
- **Do not re-run Phase 8's experiments.** Already established during the
  audit: nothing in Phase 9 touches the code path `experiments/` exercises.
  `server/results/e1`–`e6` stay as committed. The lock measurement writes a
  *new* directory (`e5_lock/`), it does not modify `e5/`.
- **`MSYS_NO_PATHCONV=1`** on any `docker compose run` passing a container
  path — the recurring Windows/Git-Bash trap (observation 41), which bit k6
  again in P8.3.
- **The demo's headline moment depends on a scheduler that must already be
  running.** A breach that appears live requires the demo-scale scheduler
  to have been sweeping *before* the moment arrives. A demo runner that
  seeds perfectly and leaves the scheduler stopped produces a dashboard
  that never updates, on the one screen §8 says will be remembered.
- **A demo-scale scheduler escalates real rows and outlives its tool
  call.** Observations 35 and 39 are two separate incidents of exactly
  this. `docker ps -a` before trusting a "fresh" reset, and stop the
  scheduler when the demo ends.
- **`SLA_SCALE` must stay a value Postgres binds as a float.** Observation
  37: `0.0004` is fine, but never remove the `CAST(... AS double
  precision)` from the breach query.

---

## Verify Phase 9 yourself, once built

```bash
# P9.1 — the demo path, from a stack that is up
bash server/scripts/demo.sh
# expect: what it reset, seeded counts, URLs + logins, scheduler state,
# and the numbered scenario. Then walk the printed steps in a browser.

# P9.2 — the lock measurement (writes a NEW directory, never touches e5/)
cat server/results/e5_lock/summary.md
cat server/results/e5_lock/table_e5_lock_latency.csv
git status                      # must be clean — no stray lock edit

# P9.2 — deployment readiness
docker compose -f docker-compose.prod.yml up -d --build
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8000/health   # expect 200
docker compose -f docker-compose.prod.yml down -v

# Every sub-phase ends here
docker compose exec db psql -U postgres -c "DROP DATABASE IF EXISTS nirantharseva_test;" -c "CREATE DATABASE nirantharseva_test;"
docker compose run --rm -e DATABASE_URL="postgresql+asyncpg://postgres:dev@db:5432/nirantharseva_test" \
  api sh -c "alembic upgrade head && python -m app.seed && ruff check . && ruff format --check . && pytest -q && python -m app.verify_replay"
# expect 269 passed, clean, alembic head 0009
```
