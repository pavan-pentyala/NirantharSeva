# PROGRESS

> Claude Code reads this at the start of every session and rewrites it at the
> end. It is the only memory that survives between sessions. Keep it honest —
> an optimistic PROGRESS file is worse than no PROGRESS file, because the next
> session builds on top of something that does not exist.

**Last updated:** 2026-08-19
**Last session model:** Sonnet 5 — Phase 3 build, start to finish.
**Files under `server/` and `.github/` changed. No file under `client/` changed.**

---

## Current phase

**Phase 3 is complete.** All 18 exit criteria in `docs/PHASE3_PLAN.md` are met
and ticked. Built in the exact order the plan gives, steps 1–8, commits
`110d2b2` through `2ff889a` on `main`, plus one CI-infrastructure fix
(`dc20b52`, see below) needed to actually get a green run. Pushed and
CI-checked.

## Done this session (2026-08-19)

Built in the order `docs/PHASE3_PLAN.md`'s "Build order" table gives:

1. **`replay_steps()`** in `app/domain/states.py` (`110d2b2`) — a generator
   yielding the per-event `(advanced, state, lamport, winning_op_id)` fold.
   `replay_state()` is now a four-line wrapper over it; its signature, return
   type, and existing unit tests are unchanged.
2. **`app/sync/event_log.py`** (`2af5e2f`) — `triple()`, `fetch_triples()`,
   `replay_referral()`. `push.py` and
   `tests/property/test_referral_replay.py` both go through it now instead of
   each holding their own copy of the query and the row-to-tuple mapping.
3. **The bare `assert` in `push.py` downgraded to a structured ERROR log**
   (`27a46b0`) — carries `referral_id` and `op_id`; the write continues with
   the cached `current_state`, same as before. A new test proves a corrupted
   cache no longer 500s the request.
4. **Docstring fixes** (`de43687`) — `scoping.py` now enumerates its five
   `SUBTREE_CTE` call sites by name instead of counting them (ADR-005's
   "three" was already stale before this session; D6 and the timeline made it
   five). `replay_state`'s docstring no longer calls itself "the P3 replay
   endpoint" — it names `python -m app.verify_replay`.
5. **`app/verify_replay.py`** (`5a3b5a7`, ADR-007) — one `LEFT JOIN` scan
   over every referral and event, `REPEATABLE READ`, no advisory lock.
   `verify_all()` returns a report; the `__main__` block prints and sets the
   exit code. A zero-event referral is reported as its own violation, not
   skipped. Wired into CI's `server` job after `pytest`. Three integration
   tests, including a deliberately corrupted cache detected and restored in a
   `finally`.
6. **`GET /referrals/{id}/timeline`** (`14740e0`, ADR-008) — one query, an
   `INNER JOIN` of `referral` to `referral_event` filtered by the subtree
   predicate, so "doesn't exist," "out of scope," and "exists with zero
   events" all collapse to the same 404. `advanced` comes from
   `replay_steps`, zipped against the event rows with `strict=True`. No
   pagination — the fold is prefix-dependent, and the docstring says so.
7. **`scripts/demo_walk.py`** (`2ff889a`, D12) — drives a referral
   `CREATED → … → CLOSED` through the real `/sync/push` over HTTP, including
   a genuine two-device conflict and a stale write through the real
   `app/sync/conflicts.py`. Idempotent by I1 (`uuid5`-derived `op_id`s and
   `entity_id`), not a guard — verified manually by running it twice against
   the live stack: 8 `referral_event` rows and 1 `sync_conflict` row after
   the first run, identical counts after the second.
   `tests/integration/test_demo_walk.py` mirrors the same table against the
   ASGI test client and pins the shape in CI, including the second-run
   idempotency check.
8. **Cold-start pass**, this session, command-by-command (see below).

Two things worth flagging, not silent calls:

- **Grep-based exit criteria bit twice this phase** — `grep -rn "frm == state"
  server/app/` and `grep -rn "assert " server/app/sync/push.py` both initially
  matched twice/once-more than expected, because explanatory prose near the
  code contained the literal pattern the grep was hunting for. Both fixed by
  rewording, not by weakening the grep. Full account in
  `docs/PHASE2_OBSERVATIONS.md`'s new Phase 3 section, observation 13.
- **Step 3's own exit criteria required a new test**, which reads in tension
  with the build-order note that steps 1–4 have "no test edits other than
  rewiring `test_referral_replay.py`." Read the constraint as protecting the
  168 pre-existing tests from being altered to hide a regression, not as
  forbidding a new test for a newly introduced code path. No existing test
  was touched; one was added. Full reasoning in observation 16 of the same
  file.

## Exit criteria status

All 18 in `docs/PHASE3_PLAN.md` are `[x]`. Verify any of them yourself with
the commands in that file's "Verify Phase 3 yourself" section, or the
cold-start block below.

## Cold-start pass — run this session, command by command

```bash
docker compose down -v && docker compose up -d --build
docker compose run --rm api sh -c "alembic upgrade head && python -m app.seed"
docker compose run --rm api python scripts/demo_walk.py
docker compose run --rm api python -m app.verify_replay
```

Result: 8 steps, statuses `accepted, accepted, accepted_stale, conflict,
accepted, accepted, accepted, accepted` — matching the table in
`docs/PHASE3_PLAN.md` exactly. Verifier: `checked 3 referrals, 10 events —
I3 holds`.

```bash
TOKEN=$(curl -s -X POST localhost:8000/auth/login -H 'content-type: application/json' \
  -d '{"username":"asha_a","password":"dev"}' | python3 -c "import json,sys; print(json.load(sys.stdin)['access_token'])")
curl -s "localhost:8000/referrals/<demo-referral-id>/timeline" \
  -H "authorization: Bearer $TOKEN" | python3 -m json.tool
```

Result: 8 events, `advanced` flags `[true, true, false, false, true, true,
true, true]`, `current_state` and `replayed_state` both `CLOSED`.

```bash
docker compose run --rm \
  -e DATABASE_URL="postgresql+asyncpg://postgres:dev@db:5432/nirantharseva_test" \
  api sh -c "alembic upgrade head && python -m app.seed && ruff check . && pytest -q && python -m app.verify_replay"
```

Result: `ruff check .` clean, **180 passed**, verifier clean, `alembic heads`
still `0004`.

CI: green on all four jobs, run
[32240152464](https://github.com/pavan-pentyala/NirantharSeva/actions/runs/32240152464)
on commit `dc20b52`. Getting there took an extra fix: `e2e` hung three runs in
a row (20+ minutes each, no error) on `npx playwright install --with-deps
chromium` — apt-get blocking on an interactive `needrestart` prompt with no
TTY attached, a recent Ubuntu runner-image behaviour, unrelated to any Phase 3
code. Fixed in `dc20b52` by setting `DEBIAN_FRONTEND=noninteractive` and
`NEEDRESTART_MODE=a` on that step, plus `timeout-minutes: 15` on the job so a
future hang fails within minutes instead of running silently for hours. This
was flagged and confirmed with the user before touching `ci.yml`, since
editing the pipeline itself was outside what Phase 3's build order asked for.

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
- **D9–D12 (Phase 3)** — settled and built. See `docs/PHASE3_PLAN.md`.
- **Phase 2 decisions D1–D8** — settled and all built. See `docs/PHASE2_PLAN.md`.
- Review-I (per D9) is a literature review and survey, not a live demo. No
  rehearsal is budgeted or required.

## Next concrete step

**Wait for the user's explicit go-ahead before starting Phase 4** (handoff
R1). Phase 4 is the offline client — PWA, Dexie, outbox, optimistic UI. It
needs the `.dc.html` design bundle from `docs/UI_DESIGN_BRIEF.md`, which is
not yet in the repo; confirm it has arrived before starting.

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
- **A persistent test-database volume across many manual `pytest` runs
  eventually breaks `/sync/pull?limit=1000`-based tests** — not a code
  regression, just accumulated rows. Reset with `docker compose exec db psql
  -U postgres -c "DROP DATABASE nirantharseva_test;" -c "CREATE DATABASE
  nirantharseva_test;"` before trusting a red run that touches pull. Detail in
  `docs/PHASE2_OBSERVATIONS.md`'s Phase 3 section, observation 15.
- **Grep-based exit criteria (and CI gates) match your explanatory comments
  too, not just the code.** Two more instances this phase beyond the
  Phase 2 clock-discipline one. Detail in the same file, observation 13.
- **The rest of the hard-won detail lives in `docs/PHASE2_OBSERVATIONS.md`** —
  read it, not this section, before touching `server/`. It now has a Phase 2
  section and a Phase 3 section; both are append-only and neither rewrites
  the other.
