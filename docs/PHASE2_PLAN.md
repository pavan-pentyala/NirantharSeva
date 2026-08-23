# Phase 2 plan — domain, state machine, RBAC

**Status:** **Phase 2 complete.** P2.1 built and CI-green (`4dd737b`); P2.2 built
and CI-green (`5802b13`, docstring fix `03fdbcf`, run `32101818251`). All
exit criteria below are met. What the build actually taught — as opposed to what
this document predicted before it — is in `docs/OBSERVATIONS.md`.
**Source of truth for *what*:** `docs/IMPLEMENTATION_PLAN.md` §6. This file does
not replace it — it records the decisions §6 leaves open, the order of work,
**and the places where a later decision supersedes §6. Every such override is
marked "supersedes §6.x" and carries an ADR.** There is exactly one in Phase 2:
D7.
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

## Decisions taken with the user

**D1–D4 were settled before P2.1; D5–D8 before P2.2 (2026-08-17).** All eight
resolve genuine gaps or contradictions in plan §6. All were put to the user with
options and a recommendation; all took the recommended answer. **None of these
were taken unilaterally** — several touch items CLAUDE.md and handoff §2 require
asking about (schema, auth and roles, API endpoint paths, scope).

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

**Completed at P2.2 planning (not a change to D4 — D4 named the users but
assigned none of them to an org unit and named no `target_org_id`, and scoping
tests cannot be written from that):**

```
PHC Ramnagar            (mo1 · supervisor1)   ← the subtree root for MO tests
 └── Sub-centre Kotwali (anm1)
      ├── Village A     (asha_a)
      └── Village B     (asha_b)

patients:  ~4, names per docs/DOMAIN_PRIMER.md
referrals: 2 — one per village, both target_org_id = PHC Ramnagar
```

Note the property that makes origin-only filtering correct (D7, ADR-005): **the
target is always an ancestor of the origin**, so the receiving MO sees the
referral through `origin_org_id` alone. A test asserts this holds for the seeded
fixture, so the assumption is machine-checked rather than prose.

### D5 — P2.2 ships a minimal scoped referral read API

Plan §6.5's fourth exit criterion says an ASHA "cannot see, via API or pull, a
referral from village B". **There is no referral API.** The only endpoints are
`POST /auth/login`, `GET /health`, `POST /sync/push`, `GET /sync/pull`. The
criterion is untestable as written.

**Decided:** `GET /referrals` and `GET /referrals/{id}`, both scoped through
`app/api/scoping.py`. Outside the subtree returns **404, not 403** — a 403
confirms the referral exists, which turns the endpoint into an enumeration
oracle over UUIDs the caller was never given.

This *implements* §6.5 rather than extending it, and it is not new structure:
plan §2.2's repository layout already lists `api/referrals.py`. Only its phase
was unstated. **It is an API, not a UI** — "any real referral UI" stays on the
NOT-in-Phase-2 list and P4 still owns screens. It is also not P3's timeline
endpoint; that one calls the same scoping helper when it arrives.

Incidental but worth knowing: `SUPERVISOR` appears in no `GUARDS` entry, so this
read API is the first thing that role can actually use. That is the honest shape
of RBAC here — write-guards for ASHA/ANM/MO, read-scope for SUPERVISOR.

### D6 — the write path is locked down in both directions

P2.1 wrote `origin_org_id` straight from the client payload, recorded at the
time as a compromise because `DEV_USERS` had no real org UUID to derive from.
The moment scoping exists, **that field is the security boundary and it is
attacker-controlled** — a device that names another village's org places its
referral inside that village's subtree, and every scoping query honours it.

Separately, P2.1 enforces I4 by *role* but never checks whether the actor has
any relationship to the referral. An ASHA in Village A can close Village B's
referral: the role guard passes, the conflict table passes, the state moves.

**Decided:**
- `origin_org_id` / `origin_user_id` come from the authenticated identity.
  Payload keys of those names are **ignored** — logged at WARN with the `op_id`,
  never rejected (rejecting turns a stale offline client into a data-loss path).
- `target_org_id` **stays** a payload field. It is a clinical routing choice the
  device legitimately makes and, per ADR-005, is not a visibility input.
- A `transition` against a referral outside the actor's subtree is `rejected`
  with reason `outside_org_scope`, **writing no event**.

This is the same rule P2.1 already applied to `actor_role` ("a device cannot be
trusted to name its own role"), extended to the fields that became
security-relevant. Full reasoning in **ADR-006**.

### D7 — the toy branch of `/sync/pull` stays unscoped, until P4

**This supersedes plan §6.4's unqualified "Apply the same scoping to
`/sync/pull`."** The referral branch is scoped; the toy branch is not.

`toy_event` has no org, no user and no patient data — there is nothing to filter
by. Scoping it would mean inventing an org column on a table D1 froze and P4
deletes, and excluding it outright breaks the two Playwright fault tests that
are experiment E4's evidence.

**This is an application of D1, not an exception to it** — D1 says no new work
goes into the toy model, and this is the decision not to do any.

Time-boxed: it ends when the Phase 4 migration drops `toy_event`. ADR-005
records why this is not the failure ADR-004 warns about, and which half of that
warning still binds in full.

### D8 — migration `0004` is a full integrity pass, and needs `down -v`

P2.1 deliberately left the org/user columns bare, with a stated condition:
"Phase 2.2's real auth and seed data are what give these something real to
reference." The seed script is exactly that data, so the condition is met.

**Decided:** `0004` adds `UNIQUE (app_user.name)` — without it `sub` can resolve
to two rows and "who is acting" has no answer — an index on
`referral.origin_org_id`, the deferred FKs, and `referral.origin_org_id SET NOT
NULL`.

The `NOT NULL` is not tidiness. Every referral written during P2.1 has
`origin_org_id IS NULL`, and `NULL IN (subtree)` is never true — so **before
`0004`, the data-leak test passes vacuously**, because nothing is visible to
anyone. `0004` is what makes the most important test in Phase 2 mean something.

It cannot apply to a database holding those rows. `docker compose down -v` is
required; all data here is synthetic by explicit project choice, so this costs
nothing. The migration pre-checks for NULLs and fails with an error naming the
wipe, rather than emitting a bare constraint violation.

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
- **ADR-005 — org-subtree visibility (read side).** ✅ Written 2026-08-17.
  The recursive CTE and its three call sites; why the predicate lives inside
  each union branch before `LIMIT`; why `target_org_id` does not participate;
  the time-boxed toy exception (D7) and why it is not the failure ADR-004 warns
  about; why a `NULL` origin makes the leak test pass vacuously.
- **ADR-006 — server-derived org identity (write side).** ✅ Written 2026-08-17.
  Why `origin_org_id` comes from the session and never from the payload, why the
  payload value is ignored rather than rejected, why the database rather than the
  token is authoritative for role and org, and why `outside_org_scope` is a
  pre-check ahead of ADR-003's table rather than a sixth row of it.

**Two ADRs, not the one the plan budgeted.** They are two decisions with two
failure modes — ADR-005 fails as *a user sees data they should not*, ADR-006 as
*a device asserts an identity it does not have* — with disjoint rejected
alternatives. They also expire differently: ADR-005 carries a clause that dies
at P4, ADR-006 carries none. `ADR-TEMPLATE.md` forbids renumbering and rewriting
decided ADRs but says nothing about how many exist, and handoff R9 requires one
per architectural decision taken.

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

- [x] A referral traverses CREATED → … → CLOSED through the API
- [x] Every guard violation returns `rejected` and writes no event
- [x] All five conflict-table rows have a passing test
- [x] I3 property test passes (replayed state == cached state)
- [x] Both Playwright fault tests still green through the new envelope
- [x] ADR-003 and ADR-004 written
- [x] CI green — run `32019283579` on commit `4dd737b`

**All met. P2.1 done.**

---

# P2.2 — auth on the real user table, RBAC, org scoping

Decisions D5–D8 above govern this sub-phase. Read **ADR-005** and **ADR-006**
before writing code; they are already written.

## Auth moves off `DEV_USERS`

Phase 0 deliberately kept users in a config env var so that no throwaway table
would need migrating away. `app_user` now exists, so:

- `app/api/auth.py` looks up `app_user` by name and verifies against
  `password_hash` with argon2id. `DevUser`, `_parse_dev_users` and
  `_dev_user_store` are deleted.
- **The `@lru_cache` goes and does not come back.** Caching `app_user` rows
  means a role or org change needs an API restart to take effect — and after D6,
  org membership is a security boundary.
- **JWT claim shape is literally unchanged**: `sub`, `role`, `org_unit_id`,
  `iat`, `exp`. But two value-level things move, and "no contract change" is
  only true at the name level:
  - `org_unit_id` stops being the placeholder string `"1"` and becomes a real
    `org_unit` UUID.
  - `CurrentUser.org_unit_id` is typed `str` today; it becomes a `UUID`, and
    `CurrentUser` gains `id`.
- **`get_current_user` becomes async and DB-backed**, resolving `sub` to the
  `app_user` row on each authenticated request. The row's `role` and
  `org_unit_id` are what the server acts on; the matching token claims remain to
  satisfy the §6.4 contract. Reasoning and the cost are in ADR-006 — briefly, a
  token is an eight-hour stale snapshot of a value that is now the
  confidentiality boundary.

### The `DEV_USERS` blast radius — the complete list

The old text named four files. The real set is thirteen, and two of them are
*additions* that removal creates rather than deletions.

| # | File | Change |
|---|---|---|
| 1 | `server/app/config.py` | drop `dev_users` |
| 2 | `server/app/api/auth.py` | delete the stub store; `login` and `get_current_user` become async + DB-backed; rewrite the module docstring |
| 3 | `server/app/schemas/auth.py` | `CurrentUser` gains `id: UUID`; `org_unit_id` becomes `UUID` |
| 4 | `.env.example` | delete the `DEV_USERS` line — **this also deletes `admin1:dev:ADMIN:1`, closing a live bug** (see below) |
| 5 | `docker-compose.yml` | remove `DEV_USERS` from the `api` service |
| 6 | `.github/workflows/ci.yml` — `server` job | remove the `DEV_USERS` env line; **add a seed step** between `alembic upgrade head` and `pytest` |
| 7 | `.github/workflows/ci.yml` — `e2e` job | **add a seed step** after the API-health wait, before `npx playwright test` (so it also precedes `kill_api.sh`) |
| 8 | `server/tests/conftest.py` | `auth_headers` logs in as `asha_a`; add `asha_b` and `supervisor` fixtures; add a session-scoped seed fixture |
| 9 | `server/tests/unit/test_auth.py` | **full rewrite** — monkeypatching `DEV_USERS` is meaningless once users are rows |
| 10 | `client/tests/helpers.ts` | `loginToken` username → `asha_a` |
| 11 | `server/tests/fault/kill_api.sh` | login username → `asha_a`; **now depends on the seed having run** |
| 12 | `server/app/sync/push.py`, `server/app/api/sync.py`, `server/tests/property/test_referral_replay.py` | the trailing `actor_role: str` parameter becomes an actor value carrying user id, role and org (see below) |
| 13 | `Makefile` | `demo` stops being an echo stub |

Two notes on that table.

**The username change is smaller than it looks.** D4's users are `asha_a`,
`asha_b`, `anm1`, `mo1`, `supervisor1`. The existing fixtures use `asha1`,
`anm1`, `mo1` — so `anm1` and `mo1` already match D4 and do not move. The only
literal that changes is `asha1` → `asha_a`, in exactly three files (#8, #10,
#11). Keep the *fixture names* (`auth_headers`, `anm_auth_headers`,
`mo_auth_headers`) as they are; only the username they log in with changes.

**Entry #12 is the one that gets missed.** `test_referral_replay.py` calls
`handle_push()` directly with `Role.ASHA.value` — no client, no login, no JWT.
A test containing no reference to authentication is inside this change's blast
radius. The actor type belongs in `app/domain/`, not `app/api/`: putting it in
the API layer would make `app/sync/` import from `app/api/`, inverting the
dependency.

**`admin1:dev:ADMIN:1` is a live bug, not just dead config.** `ADMIN` is not one
of the five `user_role` values, so `admin1` can log in, receive a valid token,
and have every push rejected as `unknown_role`. Removing `DEV_USERS` closes it.
Do not try to preserve that user — it has no home in the enum.

## The seed script — `server/app/seed.py`

The earlier text offered "`server/app/seed.py` (or `generator/seed_phase2.py`)".
That choice is now load-bearing, because the seed has to run in **three** places:
a dev laptop, CI's `server` job (uv on the runner, no Docker), and CI's `e2e` job
(inside Compose). Only `server/app/` is on the import path in all three.
`generator/` is empty, is not in the api image, and plan §2.2 reserves it for
P7's cohort generator (`cohort.py names.py timeline.py cli.py`) — a different
artifact that replaces this fixture wholesale.

**Decided: `server/app/seed.py`, invoked as `python -m app.seed`.**

- **Idempotent**, upserting by `app_user.name` / `org_unit.name`, so re-running
  is safe and CI needs no conditional logic.
- **Uses the injected `Clock`.** ADR-001 applies to seed code exactly as it
  applies to migrations, and CI's `clock-discipline` job greps for
  `datetime.now(`.
- Builds D4's completed fixture above, with names from `docs/DOMAIN_PRIMER.md`.
- Passwords are the literal `dev` for all five users, argon2id-hashed. Synthetic
  and demo-only; the project has no real credentials anywhere by explicit choice.
- **`conftest.py` calls the same `seed()` function** from a session-scoped
  fixture, so the demo data and the test data cannot drift apart.

## `app/api/scoping.py` — one helper, one place to audit

One recursive CTE, per plan §6.4:

```sql
WITH RECURSIVE subtree AS (
  SELECT id FROM org_unit WHERE id = :root
  UNION ALL SELECT o.id FROM org_unit o JOIN subtree s ON o.parent_id = s.id)
```

`:root` is the actor's org unit. Three call sites: `GET /referrals`,
`GET /referrals/{id}`, and the referral branch of `GET /sync/pull`.

- **The helper returns a SQL fragment plus params, not a Python list of ids.** A
  materialised list is a second round trip, truncates silently as the tree grows,
  and moves a security predicate out of the database into application code where
  a later refactor can drop it without any query visibly changing.
- **Visibility is decided by `origin_org_id` alone.** `target_org_id` does not
  participate — see ADR-005 for why, and for the named condition that would
  force a revisit.

## The read API (D5)

`app/api/referrals.py` (new router, wired into `main.py`) and
`app/schemas/referral.py` (new).

- `GET /referrals?state=&limit=&cursor=` — `limit` default 50, max 200, ordered
  `state_entered_at DESC, id`. A list, not a timeline and not a dashboard.
- `GET /referrals/{id}` — **404 outside the subtree, indistinguishable from a
  genuinely missing id.**
- **Implementation note that stops the 403 creeping back:** the scope predicate
  is part of the *lookup*, not a check after it. One query,
  `WHERE id = :id AND origin_org_id IN (SELECT id FROM subtree)`, empty result →
  404. No code path ever holds an out-of-scope row and then decides to hide it.

## Union-branch scoping in `/sync/pull`

- `referral_event` has no org column. The referral branch becomes
  `FROM referral_event e JOIN referral r ON r.id = e.referral_id`, filtered on
  `r.origin_org_id IN (SELECT id FROM subtree)`.
- **The toy branch is deliberately unscoped** (D7). Leave an inline comment
  pointing at ADR-005 so nobody "fixes" it.
- **The predicate goes inside each branch, before `LIMIT`** — never in Python
  after the fetch. `handle_pull` ends with
  `cursor = events[-1].seq if events else since`, so a page filtered to empty
  leaves the cursor at `since` with `has_more` false and the client **stops
  advancing permanently**. See trap 7.

## The write path (D6)

- `_apply_create_referral` stops reading `op.payload.get("origin_org_id")` and
  `("origin_user_id")`. Both come from the actor. `target_org_id` stays a
  payload field.
- `_apply_referral_transition` gains an `outside_org_scope` pre-check that
  **writes no event**, exactly like ADR-003's rows 1 and 2. Test the
  `referral_event` row count, not just the returned status (trap 4).
- **This does not modify ADR-003's five-row table.** It is a pre-check ahead of
  it, in the same position as ADR-003's own "Gap 2" (`unknown_referral`,
  `already_exists`). ADR-003 is Accepted and is not edited.
- `actor_user_id` stops being NULL.

**The read path returns an undifferentiated 404 while the write path returns a
distinct `outside_org_scope`.** That asymmetry is deliberate, not an oversight —
the reasoning is in ADR-006, and both ADRs cross-reference it.

## Migration `0004_org_integrity.py`

- `UNIQUE (app_user.name)` — `name` is the login handle and `sub` is that
  handle. Without it, two rows can answer one `sub`.
- `CREATE INDEX idx_referral_origin_org ON referral(origin_org_id)` — every
  scoped read and every pull page filters on it.
- The deferred FKs: `referral.origin_org_id`, `referral.target_org_id`,
  `patient.village_org_id` → `org_unit.id`; `referral.origin_user_id`,
  `referral_event.actor_user_id`, `patient.created_by`,
  `patient_alias.confirmed_by`, `escalation.escalated_to_user_id`,
  `sync_conflict.resolved_by` → `app_user.id`; `referral.sla_profile_id` →
  `sla_profile.id`.
- `referral.origin_org_id SET NOT NULL`.
- **Pre-check for NULL `origin_org_id` and fail with an error naming
  `docker compose down -v`**, rather than letting Postgres emit a bare
  constraint violation.
- **`0002` and `0003` are not edited.** `event_seq` is not touched — ADR-004's
  third cost still stands.

One known gap, flagged now rather than discovered at P4: `app_user.name` is
doing double duty as login handle and display name, and `asha_a` is not a name a
panel wants on a demo screen. Nothing displays a user's name until P4, so decide
it there — a `display_name` column, or renamed seed rows. Do not add a column in
`0004` for a screen that does not exist.

## Tests

| Layer | Covers |
|---|---|
| Unit | The recursive CTE returns the right subtree at each of the three tree levels. |
| Integration | `asha_a` gets 404 on Village B's referral via `GET /referrals/{id}`, and Village B is absent from `GET /referrals`. |
| Integration | **`asha_a` cannot see Village B's events via `/sync/pull`.** The data-leak test — and it **must assert the positive case in the same test** (she does see her own village), or it cannot tell "correctly scoped" from "completely broken". |
| Integration | An ANM at the sub-centre sees both villages; the PHC MO sees everything below. |
| Integration | A `create_referral` whose payload *claims* another org still lands in the actor's org. |
| Integration | A transition against an out-of-scope referral returns `outside_org_scope` **and writes zero events** (row count). |
| Integration | Login works against `app_user`; wrong password, unknown user and tampered token are all rejected; the token's `org_unit_id` equals the user's real org row. |
| Regression | Toy events are still returned **unscoped** by `/sync/pull` — a test that pins D7 so a later session cannot silently "fix" it. |
| Fixture | Every seeded `target_org_id` is an ancestor of its `origin_org_id`, machine-checking ADR-005's assumption. |

## P2.2 exit criteria

- [x] An ASHA in village A cannot see a referral from village B, via
      `GET /referrals`, `GET /referrals/{id}`, **or** `/sync/pull`
- [x] Scoping tests pass at all three tree levels
- [x] `origin_org_id`/`origin_user_id` come from the session; a payload claiming
      otherwise is ignored, with a test proving it
- [x] A transition against an out-of-scope referral is
      `rejected`/`outside_org_scope` and writes zero events
- [x] Auth works against `app_user`; `DEV_USERS` is gone from all 13 sites —
      **it was 14.** The list above missed `client/src/pages/ToyPage.tsx`'s
      hardcoded dev auto-login. See observation 10 in
      `docs/OBSERVATIONS.md`
- [x] `0004` applies to a cold database; `origin_org_id` is NOT NULL and
      indexed; `app_user.name` is unique
- [x] The seed runs in dev, in CI's `server` job, and in CI's `e2e` job
- [x] `docker compose run --rm api python -m app.seed` seeds a working district
      (the `make demo` equivalent — `make` is not installed here)
- [x] Both Playwright fault tests and `kill_api.sh` still green
- [x] ADR-005 and ADR-006 written
- [x] CI green — run `32101818251` on commit `03fdbcf`, all four jobs

**All met. P2.2 done. Phase 2 done.**

---

## Verify Phase 2 yourself

`make` is not installed here — these are the equivalent `docker compose`
commands, and the `app.seed` line is what `make demo` runs.

```bash
# 0004 is not backward-compatible with pre-0004 rows. The wipe is required.
docker compose down -v && docker compose up -d --build

# seed the district (this is `make demo`)
docker compose run --rm api sh -c "alembic upgrade head && python -m app.seed"

# full suite, against the test database
docker compose run --rm \
  -e DATABASE_URL="postgresql+asyncpg://postgres:dev@db:5432/nirantharseva_test" \
  api sh -c "alembic upgrade head && python -m app.seed && ruff check . && pytest -v"

# fault tests still green. kill_api.sh now needs the seed above — it logs in
# as asha_a, and origin_org_id is server-derived and NOT NULL.
cd client && npx playwright test && cd ..
bash server/tests/fault/kill_api.sh

# the data-leak check, by hand. asha_a must see exactly ONE referral, not two.
TOKEN=$(curl -s -X POST localhost:8000/auth/login -H 'content-type: application/json' \
  -d '{"username":"asha_a","password":"dev"}' | python3 -c "import json,sys; print(json.load(sys.stdin)['access_token'])")
curl -s localhost:8000/referrals -H "authorization: Bearer $TOKEN"
curl -s "localhost:8000/sync/pull?since=0&limit=1000" -H "authorization: Bearer $TOKEN"
# then repeat as mo1 at the PHC — both referrals must be visible.
```

**If login suddenly returns 401, the seed did not run.** That is the symptom
seeding failure presents as; there is no clearer error.

---

## Traps specific to this phase

1. **`/sync/pull` scoping — but only the referral branch.** The single most
   consequential thing in Phase 2. The toy branch is deliberately unscoped
   (D7/ADR-005) — do not "fix" it: toy has no org to filter by, and excluding it
   breaks two Playwright tests that are E4's evidence.
2. **`current_state` is a cache (I3).** The event log is the truth. Never write
   `current_state` without appending the event in the same transaction, and
   never read it where the log is what the question actually asks about.
3. **I5 is the unique partial index**, not application logic. Do not add a
   defensive `if` that checks for an existing open escalation — that is exactly
   the pattern the index exists to replace.
4. **A rejected op writes no event.** Test the row count, not just the returned
   status. A `rejected` that quietly appends is invisible until the replay test
   in P3 disagrees with the cache.
5. **No `datetime.now()`.** CI greps for it — including in `seed.py`, which is
   ordinary application code as far as ADR-001 is concerned.
6. **Never edit `0002` or `0003`.** Add `0004`.
7. **Scope in SQL, per branch, before `LIMIT`.** Filtering in Python after the
   fetch does not merely under-page. `handle_pull` ends with
   `cursor = events[-1].seq if events else since`, so a page filtered to empty
   leaves the cursor at `since` and `has_more` false — and the client stops
   advancing **permanently**. ADR-004 warned about the per-branch half; this is
   the other half.
8. **A NULL `origin_org_id` makes the leak test pass for the wrong reason.**
   `NULL IN (subtree)` is never true, so before `0004` nothing is visible to
   anyone and the test goes green vacuously. Run it after `0004` and after the
   seed, and assert the positive case — asha_a *does* see her own referral — in
   the same test.
9. **404 on read, `outside_org_scope` on write.** Deliberately different. Read
   ADR-005 and ADR-006 before unifying them.
10. **The seed is a dependency of `kill_api.sh` and of every auth fixture.** In
    CI it must run before Playwright *and* before the fault test.
11. **Do not put an `lru_cache` back over the user lookup.** After D6, org
    membership is a security boundary; a cached row means a moved or disabled
    user keeps their old scope until the process restarts.

## What is deliberately NOT in Phase 2

The escalation *sweep* (that is P5 — P2 only creates the table and its index),
SSE, the dashboard, identity resolution and fuzzy matching (P6), the PWA and
service worker (P4), **any real referral UI**, P3's timeline endpoint, and the
seeded cohort generator (P7). The toy model and `ToyPage` stay frozen until P4
per D1.

D5 adds two JSON read endpoints. That is an API, not a screen — the UI is still
P4's, and `GET /referrals/{id}` is a summary, not P3's timeline.
