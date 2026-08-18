# Phase 3 plan — hardening, replay verification, timeline

**Status:** Planned, not started. ADR-007 and ADR-008 written 2026-08-18.
**Source of truth for *what*:** `docs/IMPLEMENTATION_PLAN.md` §7. That section is
eight lines long, has no subsections, and — alone among the build phases — **no
exit criteria**. This file supplies what it leaves out, and marks every override
"supersedes §7". There is exactly one: D9.
**Source of truth for *how you work*:** `docs/HANDOFF_CLAUDE_CODE.md`.
**Read before starting:** `docs/PHASE2_OBSERVATIONS.md`, then ADR-007 and
ADR-008.

---

## Context

Plan §7 in full is three work items in one sentence — verify I3 by replaying the
full event log, add the timeline endpoint, rehearse the demo — plus an assertion
that "Review-I must be a live demo, not slides."

It calls the week a buffer: "treat the spare capacity as buffer, not as new
features." That instruction is the most important line in the section and it
governs everything below. Phase 3 adds **two** pieces of surface — one CLI and
one read endpoint — and otherwise consolidates what Phase 2 built.

Two facts about the current code shape the work.

**I3 has never been checked as stated.** The invariant says a referral's
`current_state` is always derivable by replaying its event log. What exists is a
Hypothesis property test over random walks of at most six transitions, on
referrals it created itself, and a bare `assert` in the push path that fires only
on referrals being transitioned right now. Neither can answer "does this hold for
every referral in this database." ADR-007 builds the thing that can.

**The event log is not a state history.** I6 keeps losing conflict writes, and
ADR-003 keeps `accepted_stale` operations too. So `referral_event` contains
events that did not move the state, and any timeline has to say which is which —
using the same fold that verifies I3, not a second copy of it. ADR-008 decides
that.

---

## Decisions taken with the user

### D9 — Review-I is a literature review and survey. **Supersedes §7.**

§7 says "**Review-I must be a live demo, not slides.** Rehearse it end to end at
least twice, on a cold `docker compose up`." The user has confirmed this is wrong
for his actual review: Review-I is **mainly a literature review and survey**, a
live demo is not mandatory, and any working logic shown is acceptable.

**Decided:** no rehearsal choreography is budgeted, and no demo rehearsal is an
exit criterion. What replaces it is one cold-start pass — `down -v` → `up -d
--build` → seed → demo walk → verify → timeline curl — with the exact command
list written into `PROGRESS.md`, so working logic can be shown on request without
preparation.

**No ADR.** `PHASE2_PLAN.md` says every override carries one; that convention was
about technical overrides. This is review logistics with no architectural
consequence. Flagged here rather than left implicit.

> **Outside this plan, and worth saying once.** The literature review and survey —
> the thing Review-I is actually graded on — appears **nowhere** in
> `docs/IMPLEMENTATION_PLAN.md`. No document in this repository covers it. It is
> not engineering, so it is not planned here, but nothing else is tracking it
> either.

### D10 — The timeline returns every event, each tagged `advanced`

Not filtered to advancing events (which hides I6 and makes ADR-003's conflict
policy invisible), and not an untagged dump (which cannot tell the caller which
of two competing events counted). The flag comes from the same fold that verifies
I3. Full reasoning in **ADR-008**.

### D11 — The I3 verifier is a CLI plus a pytest test calling the identical function

`python -m app.verify_replay`, mirroring `python -m app.seed`. Not an HTTP admin
endpoint: it is an unbounded whole-table scan, and exposing it would force a role
decision Phase 2 never made. Full reasoning in **ADR-007**.

### D12 — Demo data is pushed through the real `/sync/push`

Including two devices colliding to produce a genuine conflict through
`app/sync/conflicts.py`. Not hand-`INSERT`ed rows — a conflict that never went
through the engine is a prop, and a panel member who asks how it got there
deserves a better answer than "we wrote it into the table."

---

## Build order

One phase, not sub-phases (handoff R5: split only when the user asks). Steps 1–4
change **no** externally visible behaviour; the suite must stay green throughout.

| # | Work | Model |
|---|---|---|
| 1 | `replay_steps()` in `states.py`; `replay_state()` becomes a wrapper over it | Sonnet |
| 2 | `app/sync/event_log.py`; rewire `push.py` and `tests/property/test_referral_replay.py` onto it | Sonnet |
| 3 | Replace the bare `assert` in `push.py` with a structured ERROR log | Sonnet |
| 4 | Fix `scoping.py`'s and `replay_state`'s docstrings | Sonnet |
| 5 | `app/verify_replay.py` + tests + one CI step (ADR-007) | Sonnet |
| 6 | Timeline schemas + route + tests (ADR-008) | Sonnet |
| 7 | `scripts/demo_walk.py`; run it twice, assert identical row counts | Sonnet |
| 8 | Cold-start pass; rewrite `PROGRESS.md` with the command list | Sonnet |

Dependencies: 1 → 2 → {3, 4}; {1,2} → 5; {1,2} → 6; {5,6} → 7.

ADR-007 and ADR-008 are already written, so unlike Phase 2 there is no Step 0.
**All of Phase 3 is code — switch to Sonnet.**

---

## The shared extraction — the load-bearing choice

`server/app/sync/push.py` and `server/tests/property/test_referral_replay.py`
today hold the identical SELECT and the identical row-to-tuple comprehension.
Neither is extracted. The verifier and the timeline would make four copies.

### In `app/domain/states.py` — the fold, extended downward

```python
def replay_steps(events) -> Iterator[tuple[bool, State | None, int, str | None]]:
    """Per event, in input order: (advanced, state_after, lamport_after, winner_after)."""
    state, lamport, winning_op_id = None, 0, None
    for frm, to, ev_lamport, op_id in events:
        advanced = frm == state
        if advanced:
            state, lamport, winning_op_id = to, ev_lamport, op_id
        yield advanced, state, lamport, winning_op_id


def replay_state(events):          # signature and semantics UNCHANGED
    result = (None, 0, None)
    for _advanced, state, lamport, winner in replay_steps(events):
        result = (state, lamport, winner)
    return result
```

`replay_state`'s contract stays byte-identical, so its unit tests and both
callers are untouched. `states.py` stays DB-free and framework-free, as its own
docstring promises. And the rule `frm == state` then exists **once in the
repository** — which is why "`grep -rn "frm == state" server/app/` returns exactly
one line" is an exit criterion rather than a wish.

### In `app/sync/event_log.py` (new) — the row mapping and the per-referral query

- `triple(row)` — the one place a `referral_event` row becomes a replay tuple.
- `fetch_triples(session, referral_id)` — the per-referral ordered fetch.
- `replay_referral(session, referral_id)` — returns **all three** values, because
  `decide()` takes the lamport and the `sync_conflict` insert takes the winner.

Placed in `app/sync/`, not `app/domain/`, because it imports SQLAlchemy and
`states.py`'s contract forbids that. The api→sync import the timeline creates
mirrors the sync→api import `push.py` already has for `scoping.py`.

### Deliberately NOT shared: the query

The per-referral query (`WHERE referral_id = ? ORDER BY seq ASC`, which hits
`idx_event_referral` exactly) and the verifier's single bulk scan are different
access patterns. Building the bulk scan out of the per-referral function is an
N+1 — two round trips at fixture size, thousands after Phase 7's cohort
generator, and the cohort is what Phase 8 runs the verifier against. Share
`triple()` and the fold; keep the two queries separate on purpose.

---

## The I3 verifier (ADR-007)

`server/app/verify_replay.py`, run as
`docker compose run --rm api python -m app.verify_replay`. Top-level in `app/`
with an `if __name__ == "__main__"` block, mirroring `app/seed.py` — the only
import path that works in all three places (dev laptop, CI `server` job, CI `e2e`
job) that `seed.py` already had to satisfy.

**One query, not N+1:**

```sql
SELECT r.id AS referral_id, r.current_state,
       e.from_state, e.to_state, e.lamport, e.op_id
FROM referral r
LEFT JOIN referral_event e ON e.referral_id = r.id
ORDER BY r.id, e.seq
```

- **`LEFT JOIN`** is the whole answer to referrals with no events.
- **`ORDER BY r.id, e.seq`** makes `itertools.groupby` legal and puts each
  referral's events in commit order — the order `replay_state` is defined on.
- **`REPEATABLE READ`**, so a cache updated mid-scan cannot produce a phantom
  mismatch.
- **No `pg_advisory_xact_lock(4711)`.** ADR-002's lock serialises *appends*; a
  read-only full scan holding it stalls every concurrent push behind itself.

**Shape:** `verify_all() -> VerifyReport` **returns a report and neither prints
nor exits.** The `__main__` block prints and sets the exit code — 0 clean, 1 on
any mismatch — so CI wires it in unchanged. That separation is exactly what lets
the pytest test call the identical function.

**A referral with zero events is a violation, not a skip.** `replay_state([])`
returns `None` and `current_state` is `NOT NULL`, so it is reported. That is
correct: a cache asserting a state the log cannot derive is what I3 forbids. Give
it its own `reason` so it is diagnosable.

**Tests** (`server/tests/integration/test_replay_verifier.py`): the whole-database
check; a corrupted-cache test that `UPDATE`s a cache row directly and asserts the
verifier catches that exact referral; and a zero-event test. The last two must
restore in a `finally` — see trap 6.

**CI:** one step in the `server` job, **after** `pytest`, so I3 is checked against
a database the whole suite has just written to.

---

## The timeline endpoint (ADR-008)

`GET /referrals/{referral_id}/timeline`, in the existing `app/api/referrals.py`
router.

- **Scoping:** the `SUBTREE_CTE` predicate goes inside the lookup's `WHERE`, and
  an empty result is **404, never 403**, with the message byte-identical to
  `get_referral`'s. This is the fifth call site.
- **Ordering: `seq ASC`.** Not `server_time` (two events can share a tick), not
  `device_time` (client-supplied), not `lamport` (a partial order, and a losing
  write carries a higher lamport than the winner). `seq` is commit order and
  ADR-002's lock is why. Put that sentence in the docstring.
- **No pagination**, because the fold is prefix-dependent. Write the reasoning in
  the docstring so nobody adds `?cursor=` without reading it.
- **New schemas** in `app/schemas/referral.py`: `TimelineEventOut` (`seq`,
  `op_id`, `from_state`, `to_state`, **`advanced`**, `actor_role`,
  `actor_user_id`, `device_id`, `lamport`, `device_time`, `server_time`) and
  `ReferralTimelineOut` (`referral_id`, `current_state`, `replayed_state`,
  `events`). `EventOut` in `app/schemas/sync.py` is frozen — do not touch it.
- `zip(rows, steps, strict=True)` — ruff selects `B`, and a length disagreement
  should fail loudly.
- **E5 is free.** `TimingMiddleware` is registered app-wide in `main.py`, so the
  endpoint is instrumented with no code. Add a test asserting the `request_timing`
  row appears. Note for the Phase 8 E5 query: the middleware records the concrete
  path, so it must match `LIKE '/referrals/%/timeline'`. `GET /referrals/{id}`
  already behaves this way. **Do not change the middleware in Phase 3** — it is
  instrumentation an experiment depends on.
- Log at ERROR with `referral_id` when `replayed_state != current_state`: a live
  I3 alarm surfacing through a read path.

---

## The demo walk (D12)

`server/scripts/demo_walk.py`, run as
`docker compose run --rm api python scripts/demo_walk.py`.
`DEMO_API_URL` defaults to `http://api:8000` — see trap 7.

**Why `scripts/` and not `app/`:** it needs an HTTP client, and `httpx` is a
**dev-group** dependency. Importing a dev dependency from `app/` is bad layering,
and promoting `httpx` to a runtime dependency is an ask-the-user item. `scripts/`
is dev tooling, where a dev dependency is correct, and the question disappears.
This is a new directory not in plan §2.2's layout — a small structural choice,
recorded so it can be overruled.

**Idempotent by I1, not by a guard.** Every `op_id` and the referral's
`entity_id` are `uuid5`-derived from a stable key, like `seed.py`'s `_stable_id`.
A second run finds every receipt already claimed and applies nothing. The script
is therefore idempotent *because of the invariant it exists to demonstrate*, and
the second run is itself an I1 proof.

It calls `seed()` first (idempotent) and creates **its own** referral against
seeded patient Lakshmi Devi in Village A. It must not advance a seeded referral —
see trap 8.

| # | User | Device | from → to | lamport | Expected |
|---|---|---|---|---|---|
| 1 | asha_a | demo-phone-a | — → CREATED | 10 | `accepted` |
| 2 | asha_a | demo-phone-a | CREATED → IN_TRANSIT | 11 | `accepted` |
| 3 | asha_a | demo-phone-c | CREATED → IN_TRANSIT | 5 | **`accepted_stale`** |
| 4 | anm1 | demo-phone-b | CREATED → IN_TRANSIT | 20 | **`conflict`** |
| 5 | mo1 | demo-phone-d | IN_TRANSIT → ARRIVED | 30 | `accepted` |
| 6 | mo1 | demo-phone-d | ARRIVED → TREATED | 31 | `accepted` |
| 7 | mo1 | demo-phone-d | TREATED → BACK_REFERRED | 32 | `accepted` |
| 8 | asha_a | demo-phone-a | BACK_REFERRED → CLOSED | 33 | `accepted` |

Step 4 is a genuine conflict through the real `conflicts.py`: the cache is
already `IN_TRANSIT`, so `from_state != current_state`, and `20 > 11` sends
`decide()` to row 5. `anm1` is used because ANM is in `GUARDS[IN_TRANSIT]` and
Sub-centre Kotwali is an ancestor of Village A, so D6's `outside_org_scope`
pre-check passes. Step 3 produces the *other* kind of non-advancing event, so the
timeline demonstrates that `advanced=false` covers both.

Final state: `CLOSED`, 8 events, 6 advancing, 2 not, one `sync_conflict` row.

The script **asserts each step's returned status** — so it is a smoke test, not
just a data loader — and prints the verify and timeline curl commands rather than
running them. Mirror the walk as an integration test; that is what pins the flags
in CI.

---

## Hardening

**The bare `assert` in `push.py`.** Two real problems. `python -O` deletes it, so
the tripwire vanishes in exactly the optimised runs Phase 8 might use. And an
`AssertionError` in a request handler is an unhandled 500 that rolls back a
*legitimate* write because of *pre-existing* corruption — which a sync client
then retries forever. Replace with a structured ERROR log carrying `referral_id`
and `op_id`, and continue with `current_state`. This is only defensible *because*
`verify_replay` now exists as a real detector; see ADR-007's Consequences.

**Doc drift.** `scoping.py`'s docstring says three call sites; there are four, and
the timeline makes five. Change it to **enumerate** them rather than count — a
count drifts, a list is checkable — with a line saying "if you add one, add it
here." `replay_state`'s docstring says "the P3 replay endpoint"; it is a CLI.
**Do not rewrite ADR-005** to fix its "three" — `ADR-TEMPLATE.md` forbids
rewriting a decided ADR, and the correction is already recorded in ADR-008's
Context and in `docs/PHASE2_OBSERVATIONS.md`.

**`sync_conflict` is written and read by nothing.** Do not add a conflicts
endpoint — that is Phase 6's review queue. The timeline's `advanced=false` *is*
the read. An integration test asserts the demo's conflict event appears with
`advanced=false` **and** that a `sync_conflict` row exists for the same `op_id`.
Zero new surface; I6 becomes demonstrable.

---

## No migration — head stays `0004`

The timeline reads only existing columns. `idx_event_referral (referral_id, seq)`
is already exactly `WHERE referral_id = ? ORDER BY seq ASC`. The verifier's scan
needs no new index. And storing `advanced` as a column would be a second source
of truth for a derived fact — the exact bug I3 exists to prevent (ADR-008's
alternatives table).

Also rejected: a `replay_check` results table for report evidence. A new table for
output a CLI already prints, and a schema change is on the ask-first list. If
Chapter 4 wants the evidence, redirect the CLI into `results/` at Phase 8 — plan
§12 already commits that directory.

If any of this turns out false mid-phase, **stop and ask** (schema changes are on
the ask list), then add `0005`. Never edit `0004`.

---

## Tests

| Layer | Covers |
|---|---|
| Unit | `replay_steps` per-event advancement, including a log where a middle event does not advance. `replay_state`'s existing tests must pass **unchanged** |
| Integration | `verify_all()` reports `ok` for the whole database |
| Integration | `verify_all()` **detects** a deliberately corrupted `current_state` — restored in a `finally` |
| Integration | A referral with zero events is reported, with its own reason — cleaned up in a `finally` |
| Integration | The timeline returns every event in `seq` order with correct `advanced` flags, and `replayed_state == current_state` |
| Integration | The timeline 404s for `asha_a` against Village B's referral, and for an unknown UUID |
| Integration | The demo walk's exact shape: 8 events, 6 advancing, the conflict `advanced=false` **and** a `sync_conflict` row for its `op_id` |
| Integration | A `request_timing` row is written for a timeline request |
| Regression | Full suite green with zero behaviour change after steps 1–2 |

---

## Phase 3 exit criteria

Plan §7 provides none. These are Phase 3's.

- [ ] `docker compose run --rm api python -m app.verify_replay` exits **0** on a
      freshly seeded database and prints the referral and event counts checked
- [ ] The identical `verify_all()` is called by a pytest test, and a second test
      proves it **detects** a deliberately corrupted `current_state`
- [ ] A referral with zero events is **reported as a violation**, not skipped
- [ ] `verify_replay` runs in CI's `server` job after `pytest`, green
- [ ] `GET /referrals/{id}/timeline` returns every event in `seq` order, each with
      `advanced`, plus `current_state` and `replayed_state`
- [ ] The timeline returns **404, never 403**, outside the caller's subtree —
      tested for `asha_a` against Village B, and for an unknown UUID
- [ ] `grep -rn "frm == state" server/app/` returns **exactly one line**
- [ ] `push.py`, the verifier, the timeline and `test_referral_replay.py` all go
      through `app/sync/event_log.py`
- [ ] `grep -rn "assert " server/app/sync/push.py` returns nothing; the I3
      divergence path is a structured ERROR log, with a test proving the request
      still succeeds
- [ ] `python scripts/demo_walk.py` drives a real walk through `/sync/push`,
      produces exactly one `conflict` and one `accepted_stale` through
      `conflicts.py`, and asserts every step's status
- [ ] A second demo run changes **no** row counts — because every op replays from
      its receipt (I1), not because of a guard
- [ ] An integration test pins the demo's shape, including the `sync_conflict` row
- [ ] A `request_timing` row is written for a timeline request
- [ ] `scoping.py`'s docstring enumerates all five call sites; `replay_state`'s no
      longer says "endpoint"
- [ ] ADR-007 and ADR-008 written and Accepted
- [ ] **No new migration** — `alembic heads` is still `0004`
- [ ] `ruff check .` and `ruff format --check .` clean; full suite green
- [ ] CI green on all four jobs
- [ ] One cold-start pass done end to end, with the command list in `PROGRESS.md`

Explicitly **not** an exit criterion, per D9: any live-demo rehearsal.

**Stop. Report. Wait.**

---

## Verify Phase 3 yourself

```bash
docker compose down -v && docker compose up -d --build
docker compose run --rm api sh -c "alembic upgrade head && python -m app.seed"
docker compose run --rm api python scripts/demo_walk.py

# I3 across every referral — exit 0, and it prints what it checked
docker compose run --rm api python -m app.verify_replay

# the timeline: 8 events, two with "advanced": false
TOKEN=$(curl -s -X POST localhost:8000/auth/login -H 'content-type: application/json' \
  -d '{"username":"asha_a","password":"dev"}' | python3 -c "import json,sys; print(json.load(sys.stdin)['access_token'])")
curl -s "localhost:8000/referrals/<demo-referral-id>/timeline" \
  -H "authorization: Bearer $TOKEN" | python3 -m json.tool

# full suite
docker compose run --rm \
  -e DATABASE_URL="postgresql+asyncpg://postgres:dev@db:5432/nirantharseva_test" \
  api sh -c "alembic upgrade head && python -m app.seed && ruff check . && pytest -q && python -m app.verify_replay"
```

---

## Traps specific to this phase

1. **The `clock-discipline` grep is a substring match** and hits the banned
   literal inside comments and docstrings. `verify_replay.py` and `event_log.py`
   are exactly where you would write "never calls it". Write "the injected
   Clock — see ADR-001" instead. This already cost one red run in Phase 2.
2. **The verifier must not take `pg_advisory_xact_lock(4711)`.** That lock is for
   appends; a read-only full scan holding it serialises every concurrent push
   behind it. Use a `REPEATABLE READ` snapshot instead.
3. **`replay_state` keeps its exact signature and return type.** Add
   `replay_steps` beneath it and make `replay_state` a wrapper. It has heavy unit
   tests and two existing callers.
4. **The `advanced` fold is prefix-dependent.** You cannot compute it for a page
   without the running state from everything before it. That is why the timeline
   does not paginate — do not add a cursor later without carrying the state in it.
5. **A referral with zero events is a violation, not "nothing to check".** Do not
   add a `continue` for the empty case.
6. **The corrupted-cache test poisons the whole-database test** if it leaks, and
   pytest ordering is not something to rely on. Restore in a `finally`, and
   corrupt a referral the test created itself — never a seeded one.
7. **`docker compose run --rm api ...` means `localhost` is the wrong host.** That
   is a *new* container on the compose network; the API is at `http://api:8000`.
   Default to that, env-override for host runs.
8. **The demo must not advance a seeded referral.** `seed()` uses
   `ON CONFLICT DO NOTHING` on `referral`, so a mutated seeded referral is never
   reset, and `test_org_scoping.py`'s assertions then run against dirty data. The
   demo owns its own referral.
9. **Seed events hardcode `lamport = 1`.** A demo transition with a lower lamport
   lands `accepted_stale`, the walk silently does nothing, and every HTTP response
   is still 200.
10. **Do not name the demo script `test_*.py`.** `testpaths = ["tests"]` plus
    pytest's default pattern would collect it, and it needs a live HTTP server the
    suite never starts.
11. **Do not rewrite ADR-005** to fix its "three call sites". Fix `scoping.py`'s
    docstring — the thing a developer actually reads.
12. **`EventOut` in `app/schemas/sync.py` is frozen.** Write a new schema; do not
    "improve" it.
13. **404, never 403 — and the predicate goes inside the lookup's `WHERE`.** Same
    rule as `GET /referrals/{id}`; the failure mode is an enumeration oracle.
14. **`ruff` selects `B`, so `zip()` needs `strict=True`** when pairing rows with
    fold steps.
15. **`assert` in a request path is not a check.** `python -O` deletes it.
16. **Extracting the query is easy; extracting it into an N+1 is easier.** The
    verifier's query is *not* the per-referral query in a loop.
17. **`_apply_referral_transition` still needs all three return values** — the
    lamport for `decide()`, the winner for the `sync_conflict` insert.

---

## What is deliberately NOT in Phase 3

A conflicts/review-queue endpoint (Phase 6), the escalation sweep and SSE
(Phase 5), the PWA and any referral UI (Phase 4), the cohort generator (Phase 7),
a `replay_check` results table, route-template timing in `TimingMiddleware`, and
any change to `get_current_user`'s session handling. The toy model and `ToyPage`
stay frozen until Phase 4 per D1.

Plan §7 says buffer, not features. Two pieces of new surface — one CLI, one read
endpoint — is the whole of it.
