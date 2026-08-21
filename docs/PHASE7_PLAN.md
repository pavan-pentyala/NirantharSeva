# Phase 7 plan — the cohort generator and the remaining test layers

**Status:** Planned, not started. Written 2026-08-21 (Opus, plan-only session
— no code, no dependency installed, no config file created this session).
**Source of truth for *what*:** `docs/IMPLEMENTATION_PLAN.md` §11. Thirty
lines, one CLI contract, one test-layer table — this file supplies the rest,
the way `docs/PHASE6_PLAN.md` did for §10.
**Source of truth for *how you work*:** `docs/HANDOFF_CLAUDE_CODE.md`.
**Read before starting P7.1:** `docs/PHASE2_OBSERVATIONS.md` (all six phase
sections — observations 44–46 are the ones this phase can most easily
repeat), `docs/DOMAIN_PRIMER.md` ("Names in test and demo data"), ADR-001
(clock), ADR-002 (sequence lock), ADR-005 (org scoping), ADR-006 (the actor
is server-resolved), ADR-009 (the patient arrives inline), ADR-015 (this
phase's own).
**Design bundle:** not involved. Phase 7 adds no screen.

---

## Context

Phase 7 is the phase Phase 8 cannot start without. Every experiment cell in
§13 begins "load cohort", and there is nothing to load: `generator/` holds
`names.py` and `gold_set.py` (P6.1's slice forward, D23) and nothing else,
`configs/` does not exist, and `experiments/` is a `.gitkeep`.

It is also the phase that closes the test-layer table in §11.2. Four of its
five rows are already full — unit (10 files), integration (20 files), fault
(`kill_api.sh` plus two Playwright specs), E2E (7 specs). Two named items
are genuinely missing, and one of them has been missing quietly since P4.3:

- **The property row's second half.** `tests/property/test_permutation.py`
  was deleted in P4.3 (commit `1c25f35`) with sound reasoning — it was a
  toy-model LWW test, and referral coherence is decided by `from_state`, not
  lamport. But `test_referral_replay.py`'s docstring still points at it, and
  §11.2's "idempotency under arbitrary retry" has no property-level test at
  all. `test_push_idempotent.py` posts one identical batch five times; that
  is one retry pattern, not arbitrary.
- **The E2E row's third item.** "Two-device conflict" has no Playwright
  spec. The conflict *path* is well covered server-side
  (`test_referral_transitions.py`, `test_demo_walk.py`, `test_conflicts.py`),
  but §13.3's fifth E4 row names a specific mechanism — two Playwright
  contexts, both offline, same referral — and that does not exist. E4 is
  four-fifths evidenced.

Six things needed deciding. Four went to the user; two were mine to make
under handoff §2 and are flagged as such.

---

## Decisions taken with the user

Continuing D1–D27 (`docs/PHASE2_PLAN.md` … `docs/PHASE6_PLAN.md`).

### D28 — a cohort is loaded by replaying it through `/sync/push`. See **ADR-015**.

The generator emits CSVs (§11.1's contract, and I7's artifact);
`server/scripts/load_cohort.py` replays them through the real API. The
alternative — bulk `INSERT` into `referral` and `referral_event` — would
mean a second implementation of lamport assignment, sequence ordering and
receipt handling living beside `app/sync/push.py`, free to drift from it
silently, and would make E4 and E6 measurements of a code path no user ever
takes.

### D29 — the generator builds its own district, separate from `app/seed.py`'s

`n_ashas` and `n_facilities` are §11.1 parameters and mean nothing against
`app/seed.py`'s fixed four org units. The generator emits `district.csv`
(org units) and `users.csv` (ASHAs, ANMs, MOs) sized by those parameters,
and the loader creates them by direct SQL — **there is no API for creating
an `org_unit` or an `app_user`, and this phase does not add one.** That is
not a breach of D28: D28 governs the *referral* stream, which is exactly
what `/sync/push` handles.

`app/seed.py`'s D4 fixture is untouched and stays the fixture the test suite
and `make demo` assert against. Two district-creation paths now exist; the
containment is that the generator's never writes into the seeded org tree
(see "Traps").

### D30 — Phase 7 splits into P7.1 / P7.2 (handoff R5)

Approved by the user. **P7.1 is the generator, the configs and the loader** —
everything Phase 8 blocks on. **P7.2 is the two test-layer gaps** plus the
fixture-collision guard. Each ends committed, CI-green and independently
verifiable. No sub-phase starts without an explicit go-ahead (R1).

### D31 — the default cohort targets ~200 patients / ~600 referrals

Big enough that per-cell rates are not noise, small enough that E1's 54
loads (18 cells × 3 seeds) through the real push path stay in hours rather
than overnight. **P7.1 must measure one real cohort load and report the
number** — that measurement, not this estimate, is what Phase 8 budgets
against, and if it comes back far worse than expected the honest move is to
say so before Phase 8 commits, not after.

---

## Decisions taken alone (handoff §2), flagged so they can be overruled

### D32 — the property layer proves idempotency under arbitrary retry, not permutation invariance

§11.2's property row reads "Op-permutation invariance; idempotency under
arbitrary retry". The first half is **false by design for referrals** and
should not be tested as written: ADR-003 decides coherence on `from_state`,
so an op arriving out of order is *legitimately* rejected or conflicted —
permutation invariance is exactly what the state machine refuses to offer.
P4.3 already reached this conclusion when it deleted the toy permutation
test; this records it rather than rediscovering it a third time.

What is true and untested is the second half. P7.2 builds
`tests/property/test_push_idempotency.py`: Hypothesis draws a legal op
sequence *and* an arbitrary retry/duplication/re-interleaving pattern over
it, then asserts the final `current_state`, the replayed state, and the
event count are identical to the no-retry run, and that every `op_id`
appears exactly once in `referral_event`. That is I1 stated as a property
instead of as five identical POSTs.

### D33 — `connectivity_profile` shapes the device→server delay distribution

§11.1 names the parameter and never defines it. It is not a swept variable
in any of E1–E6 (checked against §13.2), so it is a realism knob, not an
independent variable — which is why this is a decision rather than a
question. It controls how long a device held an op before the loader pushes
it: `always_online` (≈0), `intermittent` (most ops prompt, a minority held
hours), `poor` (long tails, many ops held a day or more). It shapes
`events.csv`'s ordering and therefore lamport interleaving, which is what
makes conflicts arise naturally in E6 rather than only under E4's forced
faults.

---

## Build order

### P7.1 — the generator, the configs, the loader. No new screen, no schema change.

| # | Item | Notes |
|---|---|---|
| 1 | `pyyaml` as a **direct** dependency | It is currently transitive (via `uvicorn[standard]`) and importing it directly on that basis is how a lockfile change silently breaks a build. §11.1 mandates YAML configs, so the library is plan-implied — but put it in `server/pyproject.toml` explicitly. Expect the stale-`server_venv` dance (PROGRESS.md "Known problems"). |
| 2 | `configs/` + one real config | Repo-root directory (§11.1's `configs/e1_dropout25.yaml`). Schema fixed below. |
| 3 | `generator/cohort.py` | Patients, the district, duplicates, name variants. Builds on `names.py` (D23); reuses its variant table, does not add a second one. |
| 4 | `generator/timeline.py` | Per-referral state walks with per-stage dropout. **Never emits `ESCALATED`** — see "Traps". |
| 5 | `generator/cli.py` | §11.1's contract verbatim. Emits the seven files listed under "Contracts". |
| 6 | `server/scripts/load_cohort.py` | District by SQL, referrals/events by `/sync/push`. In `scripts/`, not `generator/`, for exactly `demo_walk.py`'s reason — it needs an HTTP client and `httpx` is a dev-group dependency. Keeps `generator/` importable without a running API. |
| 7 | `docker-compose.yml` — mount `./configs` and `./data` | `generator/` is already mounted (P6.1). The CLI reads from one and writes to the other. |
| 8 | CI: extend the clock-discipline grep | `.github/workflows/ci.yml`'s grep covers `server/app` only. `generator/` and `server/scripts/` are outside it and always have been — P6.1 checked them by hand. Make it structural. |
| 9 | Tests | See "What Phase 7 must prove". |

**P7.1 exit criteria**
- [ ] `python -m generator.cli --seed 42 --config configs/<name>.yaml --out data/run_001/` emits all seven files.
- [ ] Same seed twice → **byte-identical** output. Verified by running it twice and diffing, not by reasoning that it should (P6.1's discipline, and its exit criterion).
- [ ] A different seed produces different output — ruling out a generator that ignores its seed, the check P6.1 added after writing the reproducibility one.
- [ ] `config.resolved.yaml` carries the seed actually used and every default filled in; the run is reproducible from `data/run_001/` alone (I7).
- [ ] A cohort loads into a freshly migrated database through `/sync/push`, and **every referral's `origin_org_id` is its generated ASHA's own village** — the executable form of ADR-006 at cohort scale.
- [ ] `python -m app.verify_replay` is clean after a full cohort load. This is the real proof the loader did not corrupt the event log, and it is worth more than any individual loader test.
- [ ] **Zero `ESCALATED` events in the loaded cohort before any sweep runs** — asserted by query, not by inspection.
- [ ] One cohort's load time measured and written into `PROGRESS.md` (D31's Phase 8 budget input).
- [ ] `grep -rnE 'datetime\.(now|utcnow)\(|time\.time\(' generator server/scripts` finds nothing, and CI now enforces it.
- [ ] `alembic heads` still prints `0007` — **P7.1 adds no migration.** Nothing in §11 needs one.
- [ ] `ruff check`, `ruff format --check`, full server suite green.

### P7.2 — the two missing test layers, and a guard for the trap that bit P6.2 twice.

| # | Item | Notes |
|---|---|---|
| 1 | `tests/property/test_push_idempotency.py` | D32. Fresh-engine-per-example, the pattern `test_referral_replay.py` already documents (asyncpg connections cannot cross event loops). |
| 2 | `client/tests/two-device-conflict.spec.ts` | §13.3's fifth E4 row. Two contexts, both offline, same referral, both transition. |
| 3 | Fixture-collision guard test | See "Traps" #4. Asserts no two test-fixture patient names sharing a village score ≥ `IDENTITY_REVIEW_FLOOR`. |
| 4 | Remove the stale `test_permutation.py` reference | `tests/property/test_referral_replay.py`'s docstring points at a file deleted in P4.3. One line; it has already misled one session. |

**P7.2 exit criteria**
- [ ] Hypothesis proves: arbitrary retry/duplication of a legal op sequence yields the same final `current_state`, the same replayed state, and exactly one `referral_event` row per `op_id`.
- [ ] Two offline Playwright contexts transitioning the same referral produce **one `accepted`, one `conflict`**, *both* events present in `referral_event` (I6 — the losing write is never deleted), and one `sync_conflict` row.
- [ ] The fixture-collision guard passes, and **fails if a colliding name is deliberately introduced** — a guard that cannot fail is not a guard.
- [ ] No reference to `test_permutation.py` anywhere: `grep -rn test_permutation server/` is clean.
- [ ] Both suites green, CI green (server, client, and the `e2e` job).

---

## Contracts fixed now, so they are not invented at 1 a.m.

### The config file

```yaml
seed: 42                      # --seed overrides; the resolved value is echoed
n_patients: 200               # D31
n_villages: 8
n_ashas: 8                    # one ASHA per village
n_facilities: 2               # PHCs above the sub-centres
dropout_rate:                 # per-stage (§11.1), NOT one global rate
  CREATED: 0.10               # never left the village
  IN_TRANSIT: 0.25            # never arrived — E1's headline stage
  ARRIVED: 0.10
  TREATED: 0.05
  BACK_REFERRED: 0.05
name_variant_rate: 0.15       # fraction of records using a variant spelling
duplicate_rate: 0.10          # fraction of people with a second record
connectivity_profile: intermittent   # always_online | intermittent | poor
```

### What the CLI emits into `--out`

| File | Contents |
|---|---|
| `patients.csv` | `record_id, person_id, name, age, sex, phone, village` — `person_id` is ground truth; two records sharing one are the same human. |
| `district.csv` | `org_id, name, type, parent_id` — D29. |
| `users.csv` | `user_id, name, role, org_id` — D29. Password is the dev constant; the loader hashes it, the CSV never carries a hash. |
| `referrals.csv` | `referral_id, patient_record_id, origin_user, target_org, reason, priority, created_device_time` |
| `events.csv` | `referral_id, step, from_state, to_state, actor_role, device_time, push_delay_seconds` — `push_delay_seconds` is D33's output. A dropped referral simply has no further rows. |
| `ground_truth_identity.json` | Same shape as P6.1's `generator/gold_set.py` writes, at cohort scale. |
| `config.resolved.yaml` | The fully expanded config including the seed actually used. **This is I7.** |

### The loader's signature

```python
# server/scripts/load_cohort.py
async def load(cohort_dir: Path, upto_device_time: datetime | None = None) -> LoadReport
```

`upto_device_time` exists for Phase 8, not for Phase 7. §13.1's cell is
"load cohort, install `SimulatedClock`, run the timeline, advance the clock
in steps, invoke the sweep at each step" — so the runner needs to push the
events that have "happened" by each clock step, not all of them at once.
Building that seam now costs one parameter; retrofitting it later means
rewriting the loader while Phase 8 is running. `None` means "everything",
which is what P7.1 itself uses and tests.

---

## What Phase 7 must prove, and why each test exists

| Test | Guards against |
|---|---|
| Same seed → byte-identical cohort, twice | I7. Chapter 4 is indefensible otherwise, and this is the cheapest possible check. |
| A different seed → a different cohort | A generator that silently ignores `--seed` passes the test above perfectly. |
| Every referral's `origin_org_id` is its own ASHA's village | ADR-006 at scale. A loader pushing everything as one user makes E5's scoping numbers meaningless and nothing else would notice. |
| `verify_replay` clean after a full cohort load | I3 across ~600 referrals. The single most valuable assertion in P7.1. |
| Zero `ESCALATED` events before the first sweep | E1 measuring its own input instead of the system's behaviour. |
| Dropout rates in the loaded data match the config | A generator whose knobs do not actually move the data — the failure that invalidates every E1 cell at once. |
| Arbitrary retry → identical state, one event per `op_id` | I1, stated as a property rather than as one hand-picked retry pattern. |
| Two offline devices → one `accepted`, one `conflict`, both events kept | I6 and ADR-003, end to end through real browsers. E4's fifth row. |
| No two same-village fixture names score ≥ `REVIEW_FLOOR` | Observations 44 and 46, made executable instead of remembered. |

---

## Traps for this phase

- **The generator must never emit an `ESCALATED` event.** Escalation is the
  system's job — `app/domain/escalation.py`'s sweep, authored by
  `Role.SYSTEM`. E1 asks whether escalation recovers dropped referrals; a
  cohort that ships its own escalations answers that question in the input
  file. There is an exit criterion on this because it would be invisible in
  the output tables.
- **Every referral must be pushed with its own ASHA's token.**
  `origin_user_id` and `origin_org_id` come from the authenticated Actor,
  never from `op.payload` (ADR-006, and `push.py` logs a warning if the
  payload disagrees). The loader therefore logs in as each generated ASHA.
  Pushing the whole cohort as `asha_a` would "work", produce a cohort where
  every referral originates in Village A, and quietly invalidate E5.
- **There is no API for `org_unit` or `app_user`.** The district is created
  by direct SQL, `app/seed.py`'s pattern. Do not read D28 as "everything
  goes through the API" and do not add a user-creation endpoint to make it
  true — that is an auth-surface change, and handoff §2 puts it behind a
  question this phase has not asked.
- **The generator's district must never write into the seeded one.**
  `test_org_units.py` and `tests/unit/test_scoping.py` both assert the
  *exact* set of seeded org names. P6.2 already hit this: a test that
  created its own village broke two unrelated tests in two other files. Give
  generated org units names that cannot collide, and never re-parent
  anything under `Sub-centre Kotwali`.
- **Generated patients have a real `village_org_id`; the existing test
  fixtures do not — and that accident is currently load-bearing.**
  `'Test Patient'` (inserted by `test_referral_replay.py`, 20 rows per run)
  scores **100.0** against `'Scoping Test Patient'` and 85.5 against six
  P6.2 fixture names. Nothing breaks today only because both rows have
  `village_org_id IS NULL` and `blocking.py` filters on equality, which NULL
  never satisfies. A cohort in a real village removes that safety net. The
  guard test in P7.2 exists for this; until it lands, treat every new
  same-village name as suspect and score it before committing it
  (observations 44, 46).
- **`duplicate_rate`'s pairs must be the *only* pairs above `REVIEW_FLOOR`.**
  If two unrelated generated people in one village happen to score 85, E3's
  precision is measuring the generator's carelessness, not the matcher. The
  generator should check its own output and re-draw, and say how many
  re-draws it needed.
- **No `datetime.now()` in `generator/`.** Device times come from the
  config's simulated start plus generated offsets. CI has never checked this
  directory (its grep is scoped to `server/app`), so P6.1 checked by hand —
  item 8 makes it structural.
- **`pyyaml` is transitive today.** Promote it before importing it.
- **`results/` is gitignored, and §12 says to commit it.** P6.1 ignored it
  because a draft sweep is regenerable from a seed; §12 says "Commit the
  `results/` directory. Every experiment output, versioned — this is your
  Chapter 4." Both are defensible and they disagree. Phase 7 does not need
  to resolve it, but **Phase 8 must, before it generates anything it wants
  to keep** — flagging it here so it is a decision then and not a discovery.
  Phase 7 should gitignore `data/` on the same "regenerable from a seed"
  logic and say so.
- **Playwright runs from the host**, and `docker compose` needs the repo
  root as cwd. Both cost a confusing red run in P5.2 (PROGRESS.md, "Known
  problems"). `MSYS_NO_PATHCONV=1` is needed on any `docker compose run`
  passing a container path (observation 41) — the CLI's `--out` and
  `--config` are exactly that shape.

---

## Verify Phase 7 yourself, once built

```bash
docker compose down -v && docker compose up -d --build
docker compose run --rm api sh -c "alembic upgrade head && python -m app.seed"

MSYS_NO_PATHCONV=1 docker compose run --rm api \
  python -m generator.cli --seed 42 --config configs/e1_dropout25.yaml --out /app/data/run_001/
MSYS_NO_PATHCONV=1 docker compose run --rm api \
  python -m generator.cli --seed 42 --config configs/e1_dropout25.yaml --out /app/data/run_002/
diff -r data/run_001 data/run_002        # must be empty — I7

MSYS_NO_PATHCONV=1 docker compose run --rm api python scripts/load_cohort.py --cohort /app/data/run_001/
docker compose run --rm api python -m app.verify_replay
docker compose exec -T db psql -U postgres -d nirantharseva \
  -c "SELECT count(*) FROM referral_event WHERE to_state='ESCALATED';"   # must be 0
```

`alembic heads` should still print `0007` after both sub-phases.

---

## Not in this plan

`experiments/runner.py`, `analysis.py`, and E1–E6 themselves (Phase 8, §13)
— Phase 7 builds the cohort they consume and stops there. The k6 load
script (E5, Phase 8). Any schema change; §11 needs none. A user-creation or
org-creation API. Deployment (Phase 9, §14). Resolving the `results/`
gitignore question — flagged above, owed by Phase 8. The real-phone
airplane-mode clip, which is still owed and still nothing in this repo can
produce.
