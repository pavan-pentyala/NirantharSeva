# Phase 5 plan — escalation and the live dashboard

**Status:** Planned, not started. Written 2026-08-20 (Opus, plan-only session
— no code, no migration, no dependency installed this session).
**Source of truth for *what*:** `docs/IMPLEMENTATION_PLAN.md` §9. Fifty
lines, one sweep snippet, one SSE snippet, one exit criterion — this file
supplies the rest, the way `docs/PHASE4_PLAN.md` did for §8.
**Source of truth for *how you work*:** `docs/HANDOFF_CLAUDE_CODE.md`.
**Read before starting P5.1:** `docs/PHASE2_OBSERVATIONS.md` (all four
phase sections), ADR-001 (clock), ADR-002 (advisory lock), ADR-005 (org
scoping), ADR-011, ADR-012.
**Design bundle:** `docs/design_handoff_ui_screens/`, Screen 4. Governs
appearance, never architecture (handoff §8).

---

## Context

Phase 5 is the demo showpiece. Plan §9.3 and the handoff both say the same
thing: a breached SLA appearing on the supervisor's dashboard **without a
page refresh** is the twenty seconds a panel remembers. Everything below
exists to make that moment real rather than staged.

Most of the schema for it already exists and has since Phase 2.1:
`sla_profile`, `escalation`, and `uq_escalation_open` — the partial unique
index that makes I5 (no double escalation) structural rather than a Python
`if`. `State.ESCALATED` is already in the state machine, already reachable
from every live state, and already `SYSTEM`-only in `GUARDS`. The scheduler
already runs as its own Compose service. None of that needs designing again.

Four things do, and reading §9 against the code as it stands found each of
them. All four are decided below (D17–D20), two with ADRs.

---

## Decisions taken with the user

Continuing D1–D16 (`docs/PHASE2_PLAN.md`, `docs/PHASE3_PLAN.md`,
`docs/PHASE4_PLAN.md`).

### D17 — SLA windows are seeded, and scaled by `SLA_SCALE` for demos

`sla_profile` is **empty today** — nothing seeds it. The sweep in §9.1
`JOIN`s on it, so as written the sweep would escalate nothing, ever, and
would look like it was working. `app/seed.py` gains one row per escalatable
state.

`max_hours` stays an integer in real hours, because E2's design sweeps
`{24, 48, 72, 120}h` and the column should keep meaning what it says. A new
`SLA_SCALE` float env var (default `1.0`) multiplies the window inside the
sweep query, so the demo config can make a 24-hour SLA breach in seconds
without touching seed data, the schema, or E2.

No ADR: an env-var multiplier and a seed row are not an architectural
decision, the same reasoning D9 and D15 used. Recorded here so it is not
mistaken for a hack later.

### D18 — the scheduler tells the API about a breach via Postgres `LISTEN`/`NOTIFY`. See **ADR-011**.

§9.2 sketches `escalation_bus.subscribe(...)`, an in-process pub/sub. The
scheduler and the API are **separate containers** — plan §2.3 requires that
separation and E4's fault injection depends on it — so an in-process bus in
the API can never see an escalation written by the scheduler process. The
sketch is not implementable as drawn.

### D19 — the SSE endpoint authenticates by query-string token. See **ADR-012**.

`EventSource` cannot send an `Authorization` header, and every other
endpoint in this project authenticates by Bearer token from `localStorage`.

### D20 — `ESCALATED` renders as an overlay; the underlying state is read off the escalating event

The design bundle is explicit
(`docs/design_handoff_ui_screens/README.md`, "State → label mapping"):
overdue is *"shown as an overlay on top of the real state, not a
replacement — the row keeps its real state label and gains the red pill +
bar."* The state machine does the opposite: `current_state` **becomes**
`ESCALATED`, and the prior state is gone from that column.

These reconcile without changing either one, and without a wire change:
**the `ESCALATED` event's own `from_state` is the breached state.** It is
already in the pull payload (ADR-004's flat fields), already folded into
`referral_event_cache` by `applyPulledReferralEvent` (P4.2), and already
mirrored server-side by `escalation.breached_state`. So:

- Display state for a referral whose `current_state` is `ESCALATED` = the
  `from_state` of the most recent cached event whose `to_state` is
  `ESCALATED`.
- Screens 1/3/5 render `StatePill(displayState)` **plus** the overdue
  treatment (solid red pill with the `!` mark, 4px red left bar).
- `ashaActionFor` / `moActionFor` are asked about the **display state**,
  not `current_state`. Without this an escalated referral shows no action
  button at all and quietly becomes unworkable in the UI — the opposite of
  what escalation is for.

Decided by Claude Code, not the user, because it changes no contract, no
schema and no invariant — only how an existing field is rendered. Stated
here so it can be overruled.

### D21 — Phase 5 splits into P5.1 / P5.2 (handoff R5)

Approved by the user. Each sub-phase ends committed, CI-green and
independently verifiable. No sub-phase starts without an explicit
go-ahead (R1).

### D22 — an escalation resolves when the referral transitions out of `ESCALATED`

`escalation.resolved_at` is set inside `_apply_referral_transition`, in the
**same transaction** as the event append (I1), whenever the referral leaves
`ESCALATED`. This matters structurally, not cosmetically:
`uq_escalation_open` is `UNIQUE (referral_id, breached_state) WHERE
resolved_at IS NULL`, so an unresolved row permanently blocks re-escalation
in that state. Resolving on exit is what lets a referral that breaches,
gets updated, then stalls *again* in the same state escalate a second time —
which is correct behaviour, not a duplicate.

---

## Build order

### P5.1 — SLA profiles, the sweep, escalation lifecycle. Server only, no UI.

| # | Item | Notes |
|---|---|---|
| 1 | `SLA_SCALE` in `app/config.py` + `.env.example` | Float, default `1.0`. D17. |
| 2 | `app/seed.py` — SLA profile rows | One per escalatable state (`CREATED`, `IN_TRANSIT`, `ARRIVED`, `TREATED`, `BACK_REFERRED`), each with a real-hours `max_hours` and an `escalate_to_role`. Idempotent like every other seed row. |
| 3 | `app/domain/escalation.py` — `sweep()` | Plan §9.1's query, plus `SLA_SCALE`, plus the corrections in "Traps" below. Takes the injected `Clock`. Returns the escalated referral ids. |
| 4 | System event append | `actor_role='SYSTEM'`, `actor_user_id=NULL`, `device_id='scheduler'`, deterministic `op_id`. Reuses `_append_referral_event`'s shape — extract if that is cleaner than duplicating. |
| 5 | Escalation resolution in `push.py` | D22 — same transaction as the transition's event append. |
| 6 | `app/scheduler/run.py` — APScheduler | Replaces the `sleep(3600)` placeholder. Interval from a new `SWEEP_INTERVAL_SECONDS` env var (300 production, 10 demo, per §9.1). |
| 7 | Tests | See the list under "What P5.1 must prove" below. |

**P5.1 exit criteria**
- [ ] `alembic heads` is still `0006` — P5.1 adds **no migration**; every table it needs has existed since 0003.
- [ ] Seeding populates `sla_profile` with one active row per escalatable state; re-seeding does not duplicate them.
- [ ] A referral past its (scaled) SLA is escalated by one `sweep()` call: an `escalation` row exists, a `SYSTEM` `ESCALATED` event is appended, and `referral.current_state` is `ESCALATED`.
- [ ] A referral inside its SLA, and one already `CLOSED`/`LOST`/`ESCALATED`, are left untouched.
- [ ] Two consecutive sweeps over the same breached referral produce **exactly one** `escalation` row and **one** event — and the test asserts this is the index's doing, not a Python guard (delete the guard, the test still passes).
- [ ] Transitioning out of `ESCALATED` sets `resolved_at`; a subsequent re-breach in the same state creates a second `escalation` row.
- [ ] `python -m app.verify_replay` clean after a sweep — I3 holds across system-written events.
- [ ] `grep -rnE 'datetime\.(now|utcnow)\(|time\.time\(' server/app` still finds nothing outside `app/clock.py` (ADR-001, CI-enforced).
- [ ] `ruff check`, `ruff format --check`, full server suite green.

### P5.2 — SSE transport and Screen 4

| # | Item | Notes |
|---|---|---|
| 1 | `NOTIFY` on escalation | Scheduler emits after commit. ADR-011. |
| 2 | `GET /dashboard/stream` | `LISTEN`s, fans out, heartbeat comment every 20s (§9.2). Query-token auth, ADR-012. |
| 3 | Dashboard read endpoint | Stat strip counts + open-escalation list, both org-scoped via `SUBTREE_CTE`. New call sites — **update `app/api/scoping.py`'s enumerated list** (ADR-005 discipline; it names its call sites rather than counting them). |
| 4 | Client subscription | `EventSource`, auto-reconnect. Writes into Dexie; screens read Dexie only (brief §8) — the dashboard must not become the one screen that reads the network directly. |
| 5 | Screen 4 | Stat strip, overdue list sorted worst-first, 4px red left bar per row, ~2s `ease-out` pale-red→white fade on arrival, in-place count increment, one-line dismissible banner. No sound. Severity is **not** further colour-coded (brief §7). |
| 6 | D20 overlay applied to Screens 1/3/5 | Escalated referrals keep their real state label and gain the overdue treatment; action buttons follow the display state. |
| 7 | Screenshots | `docs/screenshots/`, including the dashboard mid-fade if it can be caught. |

**P5.2 exit criteria**
- [ ] With demo config, create a referral, wait, and watch it appear on the dashboard **with no page refresh** (plan §9.3 — the headline).
- [ ] A Playwright test does that headlessly: subscribe, trigger a breach, assert the row arrives on the open connection.
- [ ] Killing and restarting the API mid-stream: `EventSource` reconnects on its own and the dashboard re-converges.
- [ ] An escalated referral shows its real state label + overdue treatment on Screens 1, 3 and 5, and still offers the correct action button (D20).
- [ ] A supervisor sees only their own subtree's escalations — asserted by a test with two org branches, the same shape as `test_org_scoping.py`'s existing pull test.
- [ ] No banned word (brief §6) in any rendered dashboard copy — read every source match by hand, not a hit count (observations 13, 29, 30).
- [ ] `tsc --noEmit`, `npm run build`, both test suites green.

---

## What P5.1 must prove, and why each test exists

| Test | Guards against |
|---|---|
| Breached referral escalates | The sweep works at all. |
| Within-SLA referral does not | An off-by-one in the interval arithmetic silently escalating everything. |
| `CLOSED`/`LOST`/`ESCALATED` skipped | Re-escalating dead referrals, and escalation loops. |
| Two sweeps → one row, one event | **I5.** Delete any Python duplicate-check and this must still pass — the partial index is the mechanism (handoff §R6). |
| Resolution on transition out | D22. Without it, a referral can never escalate twice, and the bug is invisible until a demo runs long. |
| Re-breach after resolution → second row | That the resolution above did not over-correct into "escalate once, ever". |
| `verify_replay` clean post-sweep | **I3** across events no human wrote. |
| Sweep honours a simulated `Clock` | **ADR-001.** Experiments E1/E2 are worthless if the sweep reads wall-clock time. |
| `SLA_SCALE` changes the window | That the demo path and the experiment path are the same code. |

---

## Traps for this phase

- **`ON CONFLICT` against a *partial* index needs the predicate.** §9.1's
  `ON CONFLICT DO NOTHING` will not match `uq_escalation_open` unless it is
  written `ON CONFLICT (referral_id, breached_state) WHERE resolved_at IS
  NULL DO NOTHING`. Get this wrong and the insert raises instead of
  no-op'ing, or silently targets nothing.
- **The sweep appends events, so it needs `pg_advisory_xact_lock(4711)`
  first — every time, in the same transaction (ADR-002/I2).** The scheduler
  is a *second* writer process; this lock is the only thing keeping `seq`
  in commit order across both. Omitting it produces intermittent pull-cursor
  skips that will look like a client bug.
- **One transaction per escalation, not per sweep.** Same reasoning as
  push's one-per-op: a single failure must not roll back its neighbours.
- **`referral_event.op_id` is `NOT NULL UNIQUE`,** but a swept event never
  came through `/sync/push` and has no client op. Derive it deterministically
  (`uuid5` of referral + breached state, the `demo_walk.py` pattern) so a
  retried sweep is idempotent by I1's own mechanism rather than by luck.
- **`SimulatedClock` is per-process and in-memory.** The API and the
  scheduler each build their own; advancing one does not move the other.
  For the live demo this means **real clock + `SLA_SCALE`**, not simulated
  time. Simulated time is for experiment runs, where one process drives.
- **`ReferralEventCacheRow.actor_user_id` is typed `string`** but a system
  event's is `null`. Widen it, or the first escalation to reach a client
  writes a row that lies about its own shape. (`timeline.ts` already maps
  `SYSTEM` → "by the system" — P4.2 built that ahead of time.)
- **Do not let the dashboard read the network directly.** Every other
  screen reads Dexie (brief §8, plan §8.3). The dashboard is the tempting
  exception because it is "live"; it is not an exception. SSE writes to
  Dexie, the screen renders Dexie.
- **`SUBTREE_CTE`'s call-site list is enumerated by name, not counted**
  (`app/api/scoping.py`). Phase 5 adds at least two. Add them to that list —
  ADR-005's own exit criterion, and it has gone stale twice already.
- **Grep-based checks match your prose, your identifiers, and your
  framework's required syntax.** Three instances on record (observations
  13, 29, 30). Read every match.

---

## Verify Phase 5 yourself, once built

```bash
docker compose down -v && docker compose up -d --build
docker compose run --rm api sh -c "alembic upgrade head && python -m app.seed"
docker compose exec -T db psql -U postgres -d nirantharseva -c "SELECT state, max_hours, escalate_to_role FROM sla_profile ORDER BY state;"
```

`alembic heads` should still print `0006` after P5.1 — this phase adds no
migration. Then, per sub-phase, run that sub-phase's exit-criteria commands.

The headline check, once P5.2 lands: set demo config, open
`http://localhost:5173/supervisor` as `supervisor1`, create a referral as
`asha_a` in another window, and **do not touch the supervisor tab**. The
row should arrive on its own.

---

## Not in this plan

Screen 6 (ANM identity review) — Phase 6. Notifying the escalated-to user
by any channel other than the dashboard (SMS/IVR/push are all frozen
scope). `escalation.escalated_to_user_id` is populated from
`sla_profile.escalate_to_role` but nothing acts on it beyond display.
Escalation *policy* beyond a per-state hour window — no business-hours
awareness, no weekend handling, no per-facility override; E2 varies one
number and that is the whole design.
