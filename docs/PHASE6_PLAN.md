# Phase 6 plan — identity resolution and the review queue

**Status:** Planned, not started. Written 2026-08-20 (Opus, plan-only session
— no code, no migration, no dependency installed this session).
**Source of truth for *what*:** `docs/IMPLEMENTATION_PLAN.md` §10. Forty-five
lines, one pipeline snippet, four exit criteria — this file supplies the
rest, the way `docs/PHASE5_PLAN.md` did for §9.
**Source of truth for *how you work*:** `docs/HANDOFF_CLAUDE_CODE.md`.
**Read before starting P6.1:** `docs/OBSERVATIONS.md` (all five phase
sections), `docs/DOMAIN_PRIMER.md` ("Names in test and demo data"), ADR-001
(clock), ADR-005 (org scoping), ADR-009 (why this phase owns exactly one
call site), ADR-013, ADR-014.
**Design bundle:** `docs/design_handoff_ui_screens/`, Screen 6. Governs
appearance, never architecture (handoff §8).

---

## Context

Phase 6 is the measurement phase. Phases 1–5 built a system; this one is
the first that has to produce a *number a panel can attack* — precision,
recall, F1 and blocking recall over a threshold sweep, plus a failure
taxonomy that says which stage let each error through. Plan §10.2 is blunt
about why that is possible at all: the generator creates the name variants,
so it knows ground truth, and the gold set is therefore free rather than
hand-labelled.

Most of the ground for this already exists. `patient` and `patient_alias`
have been in the schema since migration 0003. ADR-009 deliberately left
`_resolve_patient` (`server/app/sync/push.py`) as an exact match on
`(normalized_name, village_org_id)` and named it as the single call site
this phase replaces — one call site, verified: `grep -rn _resolve_patient
server/` finds the definition, that one call, and one test docstring.
`server/app/linkage/` exists and is empty, with the four module names §2.2
already fixed. `anm1` already routes to `/identity-review`, currently a
placeholder.

Five things needed deciding, and reading §10 against the code as it stands
found each of them. All five are decided below (D23–D27), two with ADRs.

---

## Decisions taken with the user

Continuing D1–D22 (`docs/PHASE2_PLAN.md`, `docs/PHASE3_PLAN.md`,
`docs/PHASE4_PLAN.md`, `docs/PHASE5_PLAN.md`).

### D23 — the gold set comes from a name-variant generator sliced forward from Phase 7

§10's exit criteria need labelled ground truth. §10.2 says that comes from
the generator's `ground_truth_identity.json` — but the generator is **Phase
7** (§11.1). As written, Phase 6 cannot verify itself.

Resolved by building `generator/names.py` — the hand-written Indian
transliteration variant table the plan (§11.1) and `docs/DOMAIN_PRIMER.md`
both already demand — plus `generator/gold_set.py`, inside Phase 6. Phase 7
then builds the full cohort (referrals, timelines, dropout, the CLI) *on
top of* that module rather than duplicating it.

This is the smallest correct slice: you cannot test a fuzzy matcher without
name variants at all, `names.py` is already its own file in §2.2's layout,
and the alternative — reordering Phase 7 ahead of Phase 6 in full — would
delay the review queue by a phase for the sake of cohort-generation code
half of which (test layers) depends on nothing here.

No ADR: this is build order, not architecture, the same reasoning D21 used
for the P5.1/P5.2 split. Recorded here so Phase 7 does not rebuild it.

### D24 — Phase 6 splits into P6.1 / P6.2 (handoff R5)

Approved by the user. Each sub-phase ends committed, CI-green and
independently verifiable. No sub-phase starts without an explicit
go-ahead (R1). Boundary chosen so P6.1 is measurable with **no migration
and no UI** and P6.2 is the product integration — the same shape as
P5.1/P5.2.

### D25 — the ANM's merge decision is a plain REST call, not a sync op. See **ADR-013**.

Every other write in this project goes through `/sync/push` and the outbox.
This one deliberately does not, because a merge decided offline against a
pair that has already been decided or changed is a *wrong* merge, and the
design says twice that a wrong merge is worse than a slow one.

### D26 — Screen 6 keeps two buttons; there is no "not sure" path

`docs/design_handoff_ui_screens/README.md` explicitly defers this one
("confirm with the team whether a 'not sure, ask supervisor' path is
needed before build"). Confirmed with the user: **no third option.**
"Different people — keep both" is already the safe answer under
uncertainty — it merges nothing, loses nothing, and the pair can be
revisited later. A third path would need an escalate route, another status
value, and a supervisor-side queue view, which is scope this phase does not
have.

### D27 — blocking always uses village; phone only narrows when both sides have one. See **ADR-014**.

§10.1's `block(village_id=village_id, phone_prefix=phone[:4])` raises
`TypeError` on a patient with no phone, and even guarded it would make
every phone-less patient permanently unmatchable. The design's own Screen 6
mockup shows exactly that case — "No number given" — as a field the nurse
is asked to weigh.

---

## Build order

### P6.1 — the pipeline, the gold set, the threshold sweep. Server only, no migration, no UI.

| # | Item | Notes |
|---|---|---|
| 1 | `rapidfuzz` dependency | Named in `CLAUDE.md`'s stack list but **not in `server/pyproject.toml`** — `uv lock`, then rebuild. Expect the stale-`server_venv` dance from PROGRESS.md's "Known problems"; `-V` alone did not do it for apscheduler. |
| 2 | `IDENTITY_AUTO_ACCEPT` / `IDENTITY_REVIEW_FLOOR` in `app/config.py` + `.env.example` | Floats, defaults `92` / `80` (§10.1). Env vars, not constants, because E3 sweeps them — same reasoning as D17's `SLA_SCALE`. |
| 3 | `app/linkage/normalize.py` | NFKD, strip diacritics, lowercase, collapse whitespace. **No database imports** — same discipline `app/domain/states.py` promises. |
| 4 | `app/linkage/scoring.py` | `max(fuzz.token_set_ratio, fuzz.WRatio)` over two already-normalised strings. **No database imports** — the sweep re-scores a fixed candidate set six times and must not need six round trips. |
| 5 | `app/linkage/blocking.py` | Candidate fetch. D27/ADR-014's predicate. Takes a session. |
| 6 | `app/linkage/pipeline.py` | `resolve()` — exact → alias → blocked fuzzy → threshold. Returns `Resolution` (shape below). Takes a session and the injected `Settings`. |
| 7 | `generator/names.py` | Hand-written variant table (D23). **No random character noise** (§11.1, DOMAIN_PRIMER) — it invents mistakes no human makes and flatters the matcher. |
| 8 | `generator/gold_set.py` | Seeded, reproducible: same seed → byte-identical output. Emits patients + `ground_truth_identity.json`. Must include cross-village and phone-changed duplicates — see "Traps". |
| 9 | `docker-compose.yml` — mount `./generator` | `- ./generator:/app/generator` on the `api` service, so it imports as `generator.*` with no `PYTHONPATH` fiddling. `generator/` is a repo-root directory (§2.2) and is otherwise invisible inside the container. |
| 10 | `server/scripts/e3_draft_sweep.py` | Loads the gold set, runs `resolve()` at each threshold, writes `results/e3_draft/`. Phase 8's `experiments/e3.py` supersedes this — it does not duplicate it. |
| 11 | Tests | See "What P6.1 must prove". |

**P6.1 exit criteria**
- [ ] `alembic heads` still prints `0006` — P6.1 adds **no migration**.
- [ ] `grep -rnE '^from app\.db|^from sqlalchemy|import sqlalchemy' server/app/linkage/normalize.py server/app/linkage/scoring.py` finds nothing — the two pure modules stay pure.
- [ ] Same seed → identical gold set and identical sweep numbers, twice in a row (I7's spirit, before I7 formally arrives in Phase 7).
- [ ] The gold set contains true-duplicate pairs that blocking **rejects**, so blocking recall is a live number below 100%, not a tautology.
- [ ] Threshold sweep over {80, 85, 88, 90, 92, 95} writes precision, recall, F1, auto-resolution rate and blocking recall to `results/e3_draft/`.
- [ ] Naive exact-match baseline in the same table, same cohort.
- [ ] Failure taxonomy: every error attributed to the stage that let it through (normalize / blocking / scoring / threshold).
- [ ] `grep -rnE 'datetime\.(now|utcnow)\(|time\.time\(' server/app` still finds nothing outside `app/clock.py` (ADR-001, CI-enforced).
- [ ] `ruff check`, `ruff format --check`, full server suite green.

### P6.2 — schema, wiring, the review API, and Screen 6.

| # | Item | Notes |
|---|---|---|
| 1 | Migration `0007` | Three changes, detailed under "Schema" below. **Never edit a shipped migration** — `0006` is untouched. |
| 2 | Backfill `patient.normalized_name` | The old values came from ADR-009's `name.strip().lower()`, which is **not** the new `normalize()`. Without this the exact-match step silently misses on every pre-existing row. See "Traps". |
| 3 | `blocking.py` gains `merged_into_id IS NULL` | Cannot be written in P6.1 — the column does not exist until `0007`. Without it a merged-away duplicate is re-suggested forever. |
| 4 | Wire `pipeline.resolve()` into `push.py::_resolve_patient` | ADR-009's named call site, and **only** that one. The `review_queue` outcome still creates the referral and a provisional patient — an ASHA's offline write never blocks on a nurse's decision. |
| 5 | `GET /identity/reviews`, `POST /identity/reviews/{id}/decide` | ADR-013. Org-scoped via `SUBTREE_CTE` — **add both to `app/api/scoping.py`'s enumerated call-site list** (ADR-005's own exit criterion; it has gone stale twice). |
| 6 | Client: queue cache + Screen 6 | Dexie v6 cache table, fetched over REST and rendered from Dexie — same shape P5.2's dashboard used, so "screens read Dexie" stays one rule rather than two. Decisions `POST` directly, then refetch. |
| 7 | Screenshots | `docs/screenshots/`, including a pair with a disagreeing field. |

**P6.2 exit criteria**
- [ ] `alembic heads` prints `0007`; `0006` unmodified.
- [ ] A pre-existing patient row whose `normalized_name` was written by the old rule is matched by the new exact step — a test that fails without the backfill.
- [ ] Score ≥ `AUTO_ACCEPT`: the existing patient is reused, a `patient_alias` row records the spelling, no review is queued.
- [ ] `REVIEW_FLOOR` ≤ score < `AUTO_ACCEPT`: the referral is created, a **new** patient row is created, one `identity_review` row is queued — and the push still returns `accepted`.
- [ ] Score < `REVIEW_FLOOR`: new patient, no review row.
- [ ] Two pushes producing the same pending pair → **exactly one** `identity_review` row, and the test asserts this is `uq_identity_review_open`'s doing: delete any Python duplicate-check and it must still pass (the P5.1 discipline, handoff §R6).
- [ ] `decide` merge: referrals repointed, alias written, `merged_into_id` set, status `merged`. A second identical POST is harmless and returns the same outcome.
- [ ] `decide` keep-separate: nothing repointed, status `kept_separate`, and the pair is **not** re-queued by a later push.
- [ ] A merged-away patient never appears as a blocking candidate again.
- [ ] An ANM sees only her own sub-centre's pairs — asserted by a two-branch test, the same shape as `test_org_scoping.py`'s pull test.
- [ ] Screen 6 renders a pair, boxes only the fields that disagree, shows queue position, and both buttons work end to end.
- [ ] No banned word (brief §6) in any rendered Screen 6 copy — read every source match by hand, not a hit count (observations 13, 29, 30).
- [ ] `tsc --noEmit`, `npm run build`, both suites green.

---

## Contracts fixed now, so they are not invented at 1 a.m.

```python
# app/linkage/pipeline.py
@dataclass(frozen=True)
class Resolution:
    patient_id: uuid.UUID | None      # the patient to USE; None => caller creates one
    method: Literal["exact", "alias", "fuzzy_auto", "review_queue", "new_patient"]
    score: float
    candidate_id: uuid.UUID | None    # set only for review_queue: who it might be
```

§10.1's snippet returns `Resolution(best, 'review_queue', score)`, which is
ambiguous: on the review path the caller must **create a new patient** and
*also* remember the candidate it might duplicate. One field cannot carry
both. `patient_id=None, candidate_id=best.id` is the shape that actually
works at the call site.

### Schema — migration `0007` (P6.2)

```sql
ALTER TABLE patient ADD COLUMN merged_into_id uuid NULL REFERENCES patient(id);
ALTER TABLE patient_alias ADD COLUMN normalized_alias text NOT NULL;  -- table is empty today; verify
CREATE TABLE identity_review (
  id uuid PRIMARY KEY,
  new_patient_id uuid NOT NULL REFERENCES patient(id),
  candidate_patient_id uuid NOT NULL REFERENCES patient(id),
  score numeric NOT NULL,
  method text NOT NULL,
  status text NOT NULL DEFAULT 'pending',      -- pending | merged | kept_separate
  created_at timestamptz NOT NULL,             -- injected Clock, never DEFAULT now()
  decided_by uuid NULL REFERENCES app_user(id),
  decided_at timestamptz NULL,
  run_id text NULL                             -- R8
);
CREATE UNIQUE INDEX uq_identity_review_open
  ON identity_review (new_patient_id, candidate_patient_id) WHERE status = 'pending';
```

`uq_identity_review_open` is deliberately the same shape as
`uq_escalation_open`: the duplicate-queue guard is **structural**, not an
`if` in Python. `ON CONFLICT` against it must name the predicate —
`ON CONFLICT (new_patient_id, candidate_patient_id) WHERE status = 'pending'`
— or the insert raises instead of no-op'ing (P5.1's trap, verbatim).

No `DEFAULT now()` on any timestamp — migration 0003's own rule, still in
force.

---

## What Phase 6 must prove, and why each test exists

| Test | Guards against |
|---|---|
| `normalize()` folds diacritics, case, whitespace, NFKD | The whole pipeline resting on a normaliser nobody checked. |
| Blocking never returns a candidate from another village | **The handoff's fourth unforgivable thing.** A cross-village merge is invisible until someone is treated on the wrong history. |
| A phone-less patient is still blockable | D27/ADR-014 — the naive `phone[:4]` makes them permanently unmatchable, and the design shows this exact case. |
| Scoring is pure and deterministic | A sweep that cannot be re-run is not a result. |
| Threshold boundaries: exactly `AUTO_ACCEPT`, exactly `REVIEW_FLOOR` | Off-by-one at the band edges, which silently moves every borderline pair into the wrong bucket. |
| Same seed → identical gold set and numbers | I7's spirit; Chapter 4 is indefensible otherwise. |
| Blocking recall < 100% on the gold set | A cohort where blocking rejects nothing makes the metric a tautology (§10.2's whole point). |
| Two pushes → one review row | The partial index, not a Python guard. Delete the guard, it must still pass. |
| Review path still returns `accepted` | An ASHA offline must never lose a referral to a matching decision she cannot see. |
| Merged patient excluded from later blocking | The same pair re-queued forever. |
| ANM sees only her subtree's pairs | ADR-005, on a brand-new pair of endpoints. |

---

## Traps for this phase

- **`patient.normalized_name` is stale by construction.** ADR-009 wrote it
  as `name.strip().lower()`; Phase 6's `normalize()` is NFKD + diacritic
  strip + whitespace collapse. Every row written before `0007` is in the
  old encoding, so the exact-match step misses on all of them until the
  migration backfills. Backfill in `0007`, and pin the behaviour with a
  test — a row stored under the old rule must be found under the new one.
- **`block(phone_prefix=phone[:4])` raises `TypeError` on a null phone**
  and, guarded naively, makes phone-less patients unmatchable forever.
  ADR-014 has the predicate. `patient.phone` is nullable and the design
  mockup shows "No number given" as a real case, not an edge case.
- **`Resolution` needs both `patient_id` and `candidate_id`** — see
  "Contracts" above. §10.1's three-field return cannot express the review
  case.
- **A `review_queue` outcome must not block the write.** The referral is
  created, a provisional patient row is created, the review is queued, and
  the push returns `accepted`. Anything else loses an offline ASHA's work
  to a decision she never sees.
- **The gold set must contain pairs blocking rejects.** If every generated
  variant shares a village and a phone prefix, blocking recall is 100% by
  construction and the metric says nothing. Emit some cross-village
  duplicates and some phone-changed duplicates deliberately.
- **No random character noise in `names.py`** (§11.1, DOMAIN_PRIMER). Hand
  table only: Lakshmi/Lakshmy/Laxmi, Krishnan/Krishnnan,
  Muhammad/Mohammed/Mohamad. Random noise produces errors no human makes
  and inflates the matcher's numbers.
- **Thresholds are compared in Python, not SQL.** Keep it that way. If
  anyone later pushes the comparison into a query, it needs
  `CAST(:threshold AS double precision)` — observation 37 is the story of a
  float env var silently becoming `0` inside `make_interval`, invisible at
  the production default.
- **`patient_alias` is empty today** (verified: `SELECT count(*)` → 0), so
  `normalized_alias NOT NULL` applies cleanly. Re-verify before running
  `0007` against any database that is not freshly seeded.
- **Screen 6 shows two fields the schema does not have.**
  *"Husband's name"* has no column — **drop it** (handoff §8: never
  introduce a field that appears in the design but is not in scope).
  *"Last seen"* is derivable from the patient's most recent referral —
  **keep it**, computed, not stored.
- **`SUBTREE_CTE`'s call-site list is enumerated by name, not counted**
  (`app/api/scoping.py`). Phase 6 adds two. It has gone stale twice
  already.
- **Playwright runs from the host**, not `docker compose exec` — and
  `docker compose` needs the repo root as cwd. Both cost a confusing red
  run in P5.2; see PROGRESS.md's "Known problems".

---

## Verify Phase 6 yourself, once built

```bash
docker compose down -v && docker compose up -d --build
docker compose run --rm api sh -c "alembic upgrade head && python -m app.seed"
docker compose run --rm api python -m generator.gold_set --seed 42 --out /app/results/e3_draft/
docker compose run --rm api python scripts/e3_draft_sweep.py --gold /app/results/e3_draft/
```

`alembic heads` should still print `0006` after P6.1 and `0007` after P6.2.
Run the sweep twice with the same seed and diff the output — identical, or
the numbers are not reproducible and Chapter 4 cannot use them.

---

## Not in this plan

The full cohort generator — referrals, timelines, dropout rates,
connectivity profiles, `generator/cli.py` (Phase 7; `names.py` and
`gold_set.py` are the only pieces sliced forward, D23). The real E3 table
at three seeds (Phase 8 — Phase 6 produces a **draft**, per the §4 phase
map). Merging patients across villages by an operator's manual search;
there is no patient-search screen and this phase does not add one.
Un-merging a merged pair — `merged_into_id` makes it recoverable in SQL,
but no UI does it. Any use of `escalation.escalated_to_user_id`, still
unpopulated since P5.1.
