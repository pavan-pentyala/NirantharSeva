# PROGRESS

> Claude Code reads this at the start of every session and rewrites it at the
> end. It is the only memory that survives between sessions. Keep it honest —
> an optimistic PROGRESS file is worse than no PROGRESS file, because the next
> session builds on top of something that does not exist.

**Last updated:** 2026-08-16
**Last session model:** Opus 5

---

## Current phase

Phase 0 — step 0 (the two ADRs) is done. The Phase 0 **code** has not started
and needs the user's go-ahead plus a switch to Sonnet.

## Done

- Read handoff, preflight, implementation plan (§0–§5, §6.4, §11.2, §12, §15–16).
- Ran the full preflight check. Result recorded below. It is green.
- Renamed `docs/NirantarSeva_Technical_Implementation_Plan.md` to
  `docs/IMPLEMENTATION_PLAN.md` — every other document references that path,
  and plan §2.2 names it that way.
- Kickoff questions answered by the user (see "Settled decisions").
- **Phase 0 + Phase 1 build plan approved** by the user. Saved at
  `C:\Users\pavan\.claude\plans\kind-spinning-fountain.md`. P1 is split into
  P1.1 (server sync core) and P1.2 (client sync engine) at the user's direction.
- **ADR-001** (injectable clock) and **ADR-002** (serialised sequence
  assignment) written and pushed — commit `d1fbd71`.

## In progress / not done

- All Phase 0 code. Nothing has been written yet.

## Preflight status

Green:
- Git 2.55.0, `user.name` and `user.email` both set.
- Node v24.19.0 / npm 11.17.0 (plan wants 20 LTS; host version is not blocking,
  the container pins its own).
- Ports 5432, 8000, 5173 all free.
- Virtualization available (HypervisorPresent = True).
- Git remote configured: `git@github.com:pavan-pentyala/NirantharSeva.git`.

Verified working (second run, 2026-08-16):
- [x] WSL 2 — installed, Docker Desktop runs on it
- [x] Docker Engine 29.7.2, Compose plugin v5.3.1 (`docker compose`, not the old
      hyphenated tool)
- [x] Docker daemon running; `docker run --rm hello-world` prints
      "Hello from Docker!"
- [x] Python on host: 3.14.7 (see Known problems — not a blocker)
- [x] `uv` 0.12.5 installed
- [x] SSH to GitHub: `Hi pavan-pentyala! You've successfully authenticated.`
      Passphrase removed, so Claude Code can push non-interactively.
- [x] First commit pushed: `fd5735c` is on `origin/main`

**Preflight is green. Phase 0 is unblocked.**

Watch:
- P: drive (where this repo lives) has 7.8 GB free of 10 GB total. Docker images
  and the WSL disk go to C: (388 GB free), Playwright browsers go to
  C:\Users\pavan\AppData\Local. Only node_modules (~700 MB) lands on P:.
  Should hold, but there is no margin.

## Settled decisions

- **Name:** NirantharSeva everywhere. `setucare` in the plan is the old name;
  treat every occurrence as NirantharSeva. Python package, Docker services,
  and UI text all use the new name.
- **Python tooling:** `uv`. Commit `uv.lock`.
- **UI design brief:** not ready. Not needed until Phase 4. Claude Code designs
  under handoff §8 until the user says otherwise.
- **Git hosting:** GitHub, private repo, GitHub Actions for CI.
- **Nothing pre-built** to preserve; repo is docs-only.

## Exit criteria status — Phase 0 (Week 1)

- [ ] `docker compose up` starts db, api, scheduler, client
- [ ] API health check returns 200
- [ ] GitHub Actions workflow green on push
- [ ] `Clock` protocol with `RealClock` and `SimulatedClock`, wired as a
      dependency, `CLOCK_MODE` env var working
- [ ] `pg_advisory_xact_lock(4711)` helper in place for event appends
- [x] ADR-001 (injectable clock) and ADR-002 (sequence serialisation) written
- [ ] Review-0 submitted ← the user's task, not Claude's

## Next concrete step

**Switch to Sonnet**, then build Phase 0 exactly as the approved plan describes:
repository skeleton per §2.2, Compose per §2.3, CI per §2.4, injectable clock
per §3.1, `acquire_seq_lock` per §3.2, auth stub, and the Vite/React health
screen.

The approved plan file is the working spec for this and for P1.1 / P1.2. Read it
before starting.

## Decisions taken by Claude Code without asking

_(one line each, so the user can overrule)_

- Renamed the implementation plan file to `docs/IMPLEMENTATION_PLAN.md`.
- Postgres database name is lowercase `nirantharseva`, not `NirantharSeva` as
  written in plan §2.3 — unquoted identifiers fold to lowercase silently.
- `PyJWT` + `argon2-cffi`; the plan names "JWT + argon2id" but not the libraries.
- `ruff` for lint and format; §2.4 requires a linter without naming one.
- Stdlib JSON log formatter rather than `structlog`, to avoid an unnamed
  dependency.
- No `app_user` table in P0 — dev users come from config, so Phase 2 does not
  have to migrate a throwaway table away.
- Timing middleware and `request_timing` land in P1.1, not P0 (§12 says "from
  Phase 1").
- **ADR-001 adds one thing beyond the plan:** a CI grep that fails the build on
  `datetime.now(`, `datetime.utcnow(` or `time.time(` under `server/app/`. The
  no-direct-clock rule fails silently otherwise, and silent is the whole problem.

## Open questions for the user

- Private repo means GitHub Actions minutes are metered (2000/month on free).
  Fine for this project, but worth knowing before P8's heavier CI.

## Known problems and workarounds
- **Schedule.** Plan §4 dates are tentative — the user has confirmed no revised
  calendar is needed. Phase order is what matters, not the dates.
- Host Python is 3.14.7, plan wants 3.12. Not a problem: `uv` will manage a
  private 3.12 for editor support, and the container uses `python:3.12-slim`.
  Do not build against 3.14.
- `uv` is installed via winget at
  `C:\Users\pavan\AppData\Local\Microsoft\WinGet\Links\uv.exe` but is not on the
  PATH of Claude Code's shell. Use the full path, or restart the session.

