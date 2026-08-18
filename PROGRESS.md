# PROGRESS

> Claude Code reads this at the start of every session and rewrites it at the
> end. It is the only memory that survives between sessions. Keep it honest —
> an optimistic PROGRESS file is worse than no PROGRESS file, because the next
> session builds on top of something that does not exist.

**Last updated:** 2026-08-18
**Last session model:** Opus 5 — Phase 2 observations + Phase 3 planning.
**Documentation only: no file under `server/`, `client/` or `.github/` changed.**

---

## Current phase

**Phase 2 is complete.** P2.1 and P2.2 both built, tested, and CI-green — run
[32101818251](https://github.com/pavan-pentyala/NirantharSeva/actions/runs/32101818251)
on commit `03fdbcf`, all four jobs. `docs/PHASE2_PLAN.md`'s exit criteria are now
ticked to match reality (they had all been left unchecked).

**Phase 3 is planned and its ADRs are written, but NOT started — no code exists
for it.** Per handoff R1, it needs the user's explicit go-ahead. **All of Phase 3
is code: switch to Sonnet before starting it.**

## Done in this session (2026-08-18, docs only)

- **Wrote `docs/PHASE2_OBSERVATIONS.md`** — twelve engineering observations from
  building P2.1 and P2.2 that are not derivable from the code, the ADRs, or git
  history. This file exists because `PROGRESS.md` is overwritten every session,
  so everything learned during a build was being deleted by the next session's
  rewrite. **It is append-only per phase**: Phase 3 adds a section, it never
  rewrites Phase 2's.
- **Wrote ADR-007** (verifying I3 by a full-database replay scan, run as a CLI)
  and **ADR-008** (the timeline returns every event, tagged by whether it
  advanced the state).
- **Wrote `docs/PHASE3_PLAN.md`** — build order, the shared-extraction design,
  the verifier, the timeline, the demo walk, hardening, tests, 18 exit criteria
  and 17 traps. Plan §7 is eight lines with **no exit criteria at all** — the only
  build phase in the document without them — so this file supplies them.
- **Fixed `docs/PHASE2_PLAN.md`'s stale status.** Its header still said "P2.2
  planned, not started" and 16 of its 17 exit criteria were unchecked despite all
  being met. Header and checkboxes corrected; the "13 sites" criterion is
  annotated to record that it was actually 14.
- Settled **D9–D12** with the user (see below).

## Phase 3 decisions (D9–D12) — settled, do not re-litigate

Full reasoning in `docs/PHASE3_PLAN.md`.

- **D9 — Review-I is a literature review and survey, not a live demo.
  Supersedes plan §7.** The user confirmed §7 is wrong about this phase's
  purpose. No rehearsal choreography, and no demo rehearsal is an exit criterion.
  Replaced by one cold-start pass with the command list recorded here. No ADR —
  review logistics, no architectural consequence.
- **D10 — the timeline returns every event, each tagged `advanced`.** ADR-008.
- **D11 — the I3 verifier is a CLI (`python -m app.verify_replay`) plus a pytest
  test calling the identical function.** Not an HTTP admin endpoint. ADR-007.
- **D12 — demo data is pushed through the real `/sync/push`**, including a
  genuine two-device collision through `conflicts.py`. Not hand-`INSERT`ed rows.

## Two things flagged this session that nothing else tracks

1. **The literature review and survey — the thing Review-I is actually graded on
   — appears nowhere in `docs/IMPLEMENTATION_PLAN.md`.** No document in this
   repository covers it. It is not engineering, so it is not in the Phase 3 plan,
   but nothing else is tracking it either.
2. **`docs/mom/` contains only `.gitkeep`.** Plan §16 requires a minutes-of-meeting
   file per week, written the same day, with a monthly bundle. None exist.

## Phase 2 — what was built (summary; detail in the phase plan and the ADRs)

- **P2.1** (`4dd737b`): migration `0003`, the pure state machine
  (`app/domain/states.py`), the five-row conflict table (`app/sync/conflicts.py`),
  referral dispatch in `apply_operation`, the D3 generic pull envelope with the
  client updated in the same commit, `kill_api.sh` ported to referrals. ADR-003,
  ADR-004.
- **P2.2** (`5802b13` + `03fdbcf`): migration `0004` (FKs, `UNIQUE(app_user.name)`,
  `origin_org_id SET NOT NULL`), `app/seed.py`, auth moved off `DEV_USERS` onto
  `app_user`, `app/domain/actor.py`, `app/api/scoping.py`, `GET /referrals` and
  `GET /referrals/{id}`, the D6 write-path lockdown, and referral-branch scoping
  in `/sync/pull`. ADR-005, ADR-006.
- 168 server tests green; both Playwright fault tests green; `kill_api.sh` green.

## Settled decisions (carried forward)

- **Name:** NirantharSeva everywhere.
- **Python tooling:** `uv`. `uv.lock` committed.
- **UI design brief:** filled in, needed at Phase 4 (`docs/UI_DESIGN_BRIEF.md`).
  The referenced `.dc.html` design files are **not in the repo** — they arrive
  attached when Phase 4 starts.
- **Git hosting:** GitHub, private repo, GitHub Actions for CI.
- **`gh` CLI** at `C:\Program Files\GitHub CLI\gh.exe` (not on PATH).
- **`make` will not be installed** — use the `docker compose` equivalents.
- **Screenshots are not required** — do not raise this again.
- **GitHub Actions minutes are not a concern** — do not raise this again.
- **Phase 2 decisions D1–D8** — settled and all built. See `docs/PHASE2_PLAN.md`.

## Next concrete step

**Wait for the user's explicit go-ahead before starting Phase 3** (handoff R1).

When told to start it: **switch to Sonnet**, read `docs/PHASE2_OBSERVATIONS.md`,
then ADR-007 and ADR-008, then `docs/PHASE3_PLAN.md`, and build in the order that
file gives:

1. `replay_steps()` in `app/domain/states.py`; `replay_state()` becomes a wrapper.
2. `app/sync/event_log.py`; rewire `push.py` and `tests/property/test_referral_replay.py`.
3. Replace the bare `assert` in `push.py` with a structured ERROR log.
4. Fix `scoping.py`'s and `replay_state`'s docstrings.
5. `app/verify_replay.py` + tests + one CI step.
6. Timeline schemas + route + tests.
7. `scripts/demo_walk.py`.
8. Cold-start pass; rewrite this file with the command list.

Steps 1–4 must change no externally visible behaviour — the suite stays green
throughout. **Phase 3 needs no migration; head stays `0004`.**

## Known problems and workarounds

- Host Python is 3.14.7; project pins 3.12 via `uv`. Container is
  `python:3.12-slim`. Do not build against 3.14.
- `uv` full path if a fresh shell cannot find it:
  `C:\Users\pavan\AppData\Local\Microsoft\WinGet\Links\uv.exe`.
- **Docker Desktop is at
  `C:\Users\pavan\AppData\Local\Programs\DockerDesktop\Docker Desktop.exe`**, not
  under `Program Files`. If `docker compose` reports it cannot reach the daemon,
  the daemon is not running — start it and wait about a minute.
- `run_id` shows as `""` rather than `null` in `/health` when `RUN_ID` is set to
  an empty string in `.env` — cosmetic.
- **Named Docker volumes (`server_venv`, `client_node_modules`) need `-V`** to
  refresh after a dependency change: `docker compose up -d --build -V <service>`.
- **The rest of the hard-won detail now lives in `docs/PHASE2_OBSERVATIONS.md`** —
  the `setval` trap, the clock-grep false positive, the connection-pool
  exhaustion, the two tests that passed for the wrong reason, and the two places
  a planning document undercounted. Read that file, not this section, before
  touching `server/`.
