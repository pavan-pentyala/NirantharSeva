# Phase 2 plan — domain, state machine, RBAC

**Status:** approved, not started.
**Source of truth for *what*:** `docs/IMPLEMENTATION_PLAN.md` §6. This file does
not replace it — it records the decisions §6 leaves open, and the order of work.
**Source of truth for *how you work*:** `docs/HANDOFF_CLAUDE_CODE.md`.

---

## Context

Phase 1 built the sync engine against a one-field toy model, deliberately, so
that distributed-systems bugs were debugged in isolation. That worked: all five
of plan §5.6's exit criteria are met, including three fault tests that become
experiment E4.

Phase 2 is where the real domain arrives. It is the first phase whose output a
panel reads as *health software* rather than as an engine: eight referral states,
four human roles, an org tree, and a conflict policy that decides what happens
when two health workers act on stale information at the same time. Plan §6.3
calls that conflict policy "the behaviour you defend in Chapter 3."

It is also the first phase that can leak data. Plan §6.4 is blunt about it: a
`/sync/pull` that ignores org scoping is a data leak, and the UI will look
completely correct while it happens.

**Phase 2 is split into P2.1 and P2.2.** Each leaves the repository working,
tested, and committed. The split follows §6.5's own exit criteria: the first
three are domain correctness (P2.1), the fourth is visibility (P2.2).

---

## Decisions taken with the user before planning

These four resolve genuine gaps or contradictions in plan §6. All were put to
the user with options; all took the recommended answer.

### D1 — The toy model survives until Phase 4

Plan §6 opens "throw away `toy` and keep the engine." Taken literally that
deletes Phase 1's fault tests, which are E4 evidence — and two of them are
Playwright tests that need a screen to click, which will not exist for referrals
until Phase 4.

**Decided:** toy tables and `ToyPage` stay, frozen, through P2 and P3. No new
work goes into them. `kill_api.sh` is ported to referrals in P2.1 (it is pure
curl, needs no UI). The two Playwright fault tests are ported at P4 when the
real referral UI exists, and the toy is dropped then, in its own migration.

Consequence: for two phases the schema carries a table nobody is proud of. That
is the price of never having a week where the fault-test evidence is red or
missing. Say so plainly if a panel asks.

### D2 — `SYSTEM` is a fifth value in the `user_role` enum

Plan §6.1 defines `user_role` with four values and types
`referral_event.actor_role` as that enum. Plan §6.2 then assigns `ESCALATED` and
`LOST` to `Role.SYSTEM`, which is not one of them. The Phase 5 scheduler will
write exactly those events.

**Decided:** the enum gets five values —
`('ASHA','ANM','MO','SUPERVISOR','SYSTEM')`. `actor_role` is therefore always
populated, so "who did this" is never null in the event log, which the P3
timeline endpoint and the report both depend on. `actor_user_id` is null for
system-generated events. `app_user.role` is never `SYSTEM` by convention, not by
constraint.

### D3 — The pull contract becomes a generic envelope with a typed payload

The current `/sync/pull` returns toy-shaped events (`toy_id`, `old_value`,
`new_value`). Referral events carry `from_state`/`to_state`/`actor_role`. With
D1, one cursor must serve both entity types.

**Decided:** one event shape for all entity types. Sync-level fields stay flat;
everything type-specific moves into `payload`. This mirrors the push `Op`
contract, which has had a generic `payload` dict since P1.1, and means the
contract is not re-cut again when P6 adds patient events.

```json
{
  "seq": 1183,
  "entity_type": "referral",
  "entity_id": "<uuid>",
  "op_id": "<uuid>",
  "device_id": "d-1",
  "lamport": 17,
  "device_time": "2026-08-10T09:00:00Z",
  "server_time": "2026-08-10T09:00:03Z",
  "payload": {
    "from_state": "CREATED",
    "to_state": "IN_TRANSIT",
    "actor_role": "ASHA",
    "actor_user_id": "<uuid>"
  }
}
```

**This is a breaking change to a frozen contract.** It requires updating
`client/src/api/client.ts` and `client/src/sync/engine.ts` in the same commit,
and the two Playwright fault tests must still pass afterwards — that is the
regression check that the toy path still works through the new envelope.

### D4 — Seed data is a small hand-written fixture

The realistic cohort generator is Phase 7. Phase 2 needs only enough org tree to
prove scoping.

```
PHC Ramnagar
 └── Sub-centre Kotwali
      ├── Village A   (asha_a)
      └── Village B   (asha_b)

users:     asha_a, asha_b, anm1, mo1, supervisor1
patients:  ~4, plausible names per docs/DOMAIN_PRIMER.md
referrals: 2 (one per village)
```

Enough to prove `asha_a` cannot see Village B's referral via API or pull.
Replaced wholesale by the generator at P7.

---

## Step 0 — ADRs (Opus, before any code)

Written first so the implementation follows a recorded decision rather than the
reverse. Format per `docs/decisions/ADR-TEMPLATE.md`.

- **ADR-003 — conflict resolution policy.** The five-row decision table, why a
  losing write is recorded and never deleted (I6), why a genuine conflict
  changes nothing and asks a human instead of picking a winner. This is the
  Chapter 3 centrepiece and the most likely thing a sharp panel member probes.
- **ADR-004 — the generic sync envelope.** Why the pull contract was re-cut once,
  deliberately, at the last moment it was cheap; what it costs (a client-side
  discriminated union) and what it buys (no further re-cut at P6).
- **ADR-005 — org-subtree visibility.** Recursive CTE, applied identically to
  the API and to `/sync/pull`. Protects against the data leak §6.4 warns about.
  Write this one in P2.2, next to the code it governs.

---

# P2.1 — schema, state machine, conflict policy

## Migration `0003_referral_domain.py`

Everything in plan §6.1, with these implementation notes:

- **No `DEFAULT now()` on any timestamp column.** Plan §6.1 writes
  `server_time TIMESTAMPTZ DEFAULT now()`; that would bypass the injected clock
  and silently break simulated-time experiment runs. Write it from the `Clock`,
  exactly as `0002` already does. This is ADR-001, applied again.
- **`user_role` gets five values** (D2).
- **Foreign keys are declared** where §6.1's column list clearly implies them
  (`referral.patient_id → patient.id`, `referral_event.referral_id →
  referral.id`, `app_user.org_unit_id → org_unit.id`, and so on). §6.1 writes
  most of these as bare `UUID` columns; declaring the constraint is implementing
  the intent, not changing the schema.
- **`uq_escalation_open` is the whole of I5.** Double escalation is prevented by
  this unique partial index, never by an `if` in Python:
  ```sql
  CREATE UNIQUE INDEX uq_escalation_open ON escalation(referral_id, breached_state)
    WHERE resolved_at IS NULL;
  ```
  Nothing writes `escalation` rows until Phase 5. The table and index exist now
  so the constraint is in place before anything can violate it.
- Also create `idx_referral_open`, `idx_event_referral`, `idx_patient_norm` as
  written.

## `app/domain/states.py` — pure functions

No database imports. No framework imports. Nothing but enums and dicts. This is
the module that gets unit-tested hardest and quoted in Chapter 3.

`TRANSITIONS` and `GUARDS` exactly as plan §6.2 writes them, plus `is_legal()`
and `may()`. Note that `ESCALATED` returns to the ordinary path rather than
being terminal — that is what makes escalation a supervisory signal instead of a
parallel workflow, and the `escalation.breached_state` column is what lets the
referral resume rather than restart.

## `app/sync/conflicts.py` — the five-row decision table

Replaces the P1.1 stub. Checked in this order:

| # | Condition | Outcome | Event written? | `current_state` changes? |
|---|---|---|---|---|
| 1 | Role not permitted for `to_state` | `rejected` | no | no |
| 2 | `(from_state → to_state)` not in `TRANSITIONS` | `rejected` | no | no |
| 3 | `from_state == current_state` | `accepted` | yes | yes |
| 4 | `from_state != current_state`, incoming `lamport` **<** current | `accepted_stale` | yes | no |
| 5 | `from_state != current_state`, incoming `lamport` **>** current | `conflict` | yes | no, **and** a `sync_conflict` row is written |

Three things to get right:

- **Rows 1 and 2 check the op's own coherence**, not the referral's state.
  `is_legal(op.from_state, op.to_state)` — the op must be internally valid
  before its staleness is even considered.
- **"current lamport"** means the lamport of the event that produced the current
  state. There is no lamport column on `referral`; look it up from
  `referral_event`, the same pattern `apply_operation` already uses in P1.1.
- **`lamport ==` current is not in the table.** Break the tie on `device_id`,
  consistently with the LWW rule P1.1 already established. Record this in
  ADR-003 as a gap the plan left open rather than pretending the table covered
  it.

## Referral operations through the existing push handler

`handle_push` in `app/sync/push.py` does not change — its receipt-claim,
advisory-lock, apply, finalise structure is entity-agnostic and is I1. Only
`apply_operation` grows a dispatch on `op.entity`:

- `entity="referral", operation="create_referral"` → `from_state` null,
  `to_state` CREATED
- `entity="referral", operation="transition"` → payload carries
  `from_state`/`to_state`
- `entity="toy", operation="set_value"` → unchanged, still passing (D1)

The push `Op` shape does not change. `payload` is already a generic dict.

## Pull contract change (D3)

`app/schemas/sync.py` — `EventOut` becomes the generic envelope. `app/sync/pull.py`
reads from both `toy_event` and `referral_event` into one seq-ordered stream.

Client updated in the same commit: `client/src/api/client.ts` and
`client/src/sync/engine.ts`. `applyPulledEvents` reads `payload.value` for toy
events instead of `new_value`.

## Tests

| Layer | Covers |
|---|---|
| Unit | `is_legal` / `may` across all 8 states × 5 roles. Terminal states have no outgoing transitions. `ESCALATED` returns to the ordinary path. |
| Unit | The five-row conflict table, one test per row, plus the `lamport ==` tiebreak. |
| Integration | A referral traverses CREATED → IN_TRANSIT → ARRIVED → TREATED → BACK_REFERRED → CLOSED through the real API, with the right role acting at each step. |
| Integration | Every guard violation returns `rejected` and writes **no** `referral_event` row. Assert the row count, not just the status. |
| Integration | A `conflict` writes both the `referral_event` and the `sync_conflict` row, and leaves `current_state` untouched. |
| Property | I3: for a random legal transition sequence, `current_state` replayed from the event log equals the cached value. |
| Regression | Both Playwright fault tests still pass through the new pull envelope. |

## P2.1 exit criteria

- [ ] A referral traverses CREATED → … → CLOSED through the API
- [ ] Every guard violation returns `rejected` and writes no event
- [ ] All five conflict-table rows have a passing test
- [ ] I3 property test passes (replayed state == cached state)
- [ ] Both Playwright fault tests still green through the new envelope
- [ ] ADR-003 and ADR-004 written
- [ ] CI green

**Stop. Report. Wait.**

---

# P2.2 — auth on the real user table, RBAC, org scoping

## Auth moves off `DEV_USERS`

Phase 0 deliberately kept users in a config env var so that no throwaway table
would need migrating away. `app_user` now exists, so:

- `app/api/auth.py` looks up `app_user` by name, verifies against
  `password_hash` with argon2id.
- JWT claims are unchanged — `sub`, `role`, `org_unit_id`. **No contract change.**
- `DEV_USERS` is removed from `config.py`, `.env.example`, `docker-compose.yml`,
  and the CI workflow env in the same commit.

## Org-subtree scoping

`app/api/scoping.py` — one recursive CTE helper, per plan §6.4:

```sql
WITH RECURSIVE subtree AS (
  SELECT id FROM org_unit WHERE id = :root
  UNION ALL SELECT o.id FROM org_unit o JOIN subtree s ON o.parent_id = s.id)
SELECT ... WHERE origin_org_id IN (SELECT id FROM subtree)
```

Applied to referral endpoints **and to `/sync/pull`**. The pull is the one that
matters and the one that is easy to forget — plan §6.4 says so explicitly, and
the UI will look correct while leaking.

## Seed script

`server/app/seed.py` (or `generator/seed_phase2.py`), building D4's fixture.
Wire `make demo` to it, replacing the "not implemented until Phase 4" stub.
Use `docs/DOMAIN_PRIMER.md` for names and vocabulary — a panel reads the demo
screen before it reads the code.

## Tests

| Layer | Covers |
|---|---|
| Unit | The recursive CTE returns the right subtree for each level of the tree. |
| Integration | `asha_a` cannot see Village B's referral via the referral API — 404 or empty, not 403 leaking existence. |
| Integration | **`asha_a` cannot see Village B's events via `/sync/pull`.** The data-leak test. |
| Integration | An ANM at the sub-centre sees both villages; the PHC MO sees everything below. |
| Integration | Login works against `app_user`; a wrong password and a tampered token are both rejected. |

## P2.2 exit criteria

- [ ] An ASHA in village A cannot see a referral from village B, via API **or** pull
- [ ] Auth works against `app_user`; `DEV_USERS` is fully removed
- [ ] Scoping tests pass at all three tree levels
- [ ] `make demo` (or its `docker compose` equivalent) seeds a working district
- [ ] ADR-005 written
- [ ] CI green

**Stop. Report. Wait.**

---

## Verify Phase 2 yourself

```bash
docker compose down -v && docker compose up -d --build

# full suite
docker compose run --rm \
  -e DATABASE_URL="postgresql+asyncpg://postgres:dev@db:5432/nirantharseva_test" \
  api sh -c "alembic upgrade head && ruff check . && pytest -v"

# fault tests still green (regression through the new envelope)
cd client && npx playwright test && cd ..
bash server/tests/fault/kill_api.sh

# the data-leak check, by hand
# log in as asha_a, pull, and confirm no Village B referral_id appears
```

---

## Traps specific to this phase

1. **`/sync/pull` scoping.** The single most consequential thing in Phase 2. A
   pull that ignores the org subtree is a data leak that no screen will reveal.
2. **`current_state` is a cache (I3).** The event log is the truth. Never write
   `current_state` without appending the event in the same transaction, and
   never read it where the log is what the question actually asks about.
3. **I5 is the unique partial index**, not application logic. Do not add a
   defensive `if` that checks for an existing open escalation — that is exactly
   the pattern the index exists to replace.
4. **A rejected op writes no event.** Test the row count, not just the returned
   status. A `rejected` that quietly appends is invisible until the replay test
   in P3 disagrees with the cache.
5. **No `datetime.now()`.** CI greps for it. Same rule, third phase running.
6. **Never edit `0002`.** Add `0003`.

## What is deliberately NOT in Phase 2

The escalation *sweep* (that is P5 — P2 only creates the table and its index),
SSE, the dashboard, identity resolution and fuzzy matching (P6), the PWA and
service worker (P4), any real referral UI, and the seeded cohort generator (P7).
The toy model and `ToyPage` stay frozen until P4 per D1.
