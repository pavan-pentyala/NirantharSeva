# PROGRESS

> Claude Code reads this at the start of every session and rewrites it at the
> end. It is the only memory that survives between sessions. Keep it honest —
> an optimistic PROGRESS file is worse than no PROGRESS file, because the next
> session builds on top of something that does not exist.

**Last updated:** 2026-08-16
**Last session model:** Opus 5

---

## Current phase

Preflight. Phase 0 not started — waiting on host tool installation and on the
user's explicit go-ahead.

## Done

- Read handoff, preflight, implementation plan (§0–§5, §12).
- Ran the full preflight check. Result recorded below.
- Renamed `docs/NirantarSeva_Technical_Implementation_Plan.md` to
  `docs/IMPLEMENTATION_PLAN.md` — every other document references that path,
  and plan §2.2 names it that way.
- Kickoff questions answered by the user (see "Settled decisions").

## In progress / not done

- Everything in Phase 0. No code written.

## Preflight status

Green:
- Git 2.55.0, `user.name` and `user.email` both set.
- Node v24.19.0 / npm 11.17.0 (plan wants 20 LTS; host version is not blocking,
  the container pins its own).
- Ports 5432, 8000, 5173 all free.
- Virtualization available (HypervisorPresent = True).
- Git remote configured: `git@github.com:pavan-pentyala/NirantharSeva.git`.

Blocking, user is installing:
- [ ] WSL 2 — not installed (`wsl --install`, admin PowerShell, then reboot)
- [ ] Docker Desktop — not installed; must use the WSL 2 backend
- [ ] Docker daemon running; `docker run --rm hello-world` passes
- [ ] Python 3.12 — no `python`, no `py` launcher on PATH
- [ ] `uv` — not installed (chosen tooling)
- [ ] SSH key for GitHub — `ssh -T git@github.com` returns
      "Permission denied (publickey)". Cannot push until fixed.
- [ ] First commit pushed to the remote

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
- [ ] ADR-001 (injectable clock) and ADR-002 (sequence serialisation) written
- [ ] Review-0 submitted

## Next concrete step

User finishes installing WSL 2, Docker Desktop, Python 3.12, uv, and the GitHub
SSH key. Then, on his explicit go-ahead, start Phase 0 **on Sonnet**: repository
skeleton per plan §2.2, Compose skeleton per §2.3, CI workflow per §2.4, clock
per §3.1, advisory-lock helper per §3.2.

ADR-001 and ADR-002 are design work — write them on Opus, either before the
Phase 0 code session or after it.

## Decisions taken by Claude Code without asking

_(one line each, so the user can overrule)_

- Renamed the implementation plan file to `docs/IMPLEMENTATION_PLAN.md`.

## Open questions for the user

- Private repo means GitHub Actions minutes are metered (2000/month on free).
  Fine for this project, but worth knowing before P8's heavier CI.

## Known problems and workarounds

- **Schedule slip.** Plan §4 dates put P0 at Aug 3–9 and P1 at Aug 10–16. Today
  is Aug 16 and nothing is built. The project is starting roughly two weeks
  behind the plan's calendar. The phase *order* is still right; the dates are
  not. Needs a re-planned calendar before Review-0.
