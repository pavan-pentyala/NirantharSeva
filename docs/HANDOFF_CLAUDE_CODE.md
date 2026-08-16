# NirantharSeva — Technical Handoff for Claude Code

**Read this file first, every session, before touching any code.**

**Project:** NirantharSeva — a fault-tolerant, offline-first referral continuity
system for community health workflows. (Earlier working name: *SetuCare*. The
implementation plan still uses the old name in places; treat the two as the same
project.)

**Context:** This is an individual MTech case-study project with a graded panel
review schedule and a written report as the final output. It is not a commercial
product. Code quality matters, but *evidence* matters more: tests, experiment
results, screenshots, and a working live demo.

**Companion documents you have been given:**

| File | Role |
|---|---|
| `CLAUDE.md` (repo root) | Loaded automatically every session. Short summary of the hard rules; points here. |
| `docs/IMPLEMENTATION_PLAN.md` | The build spec. Source of truth for **what** to build, in what order, and what "done" means. |
| `docs/HANDOFF_CLAUDE_CODE.md` | This file. The rules of engagement. Source of truth for **how you work**. |
| `PROGRESS.md` | Session state. Read it at the start of every session, rewrite it at the end. |
| `docs/SETUP_PREFLIGHT.md` | Environment check. Run it before Phase 0. Do not assume any tool exists. |
| `docs/DOMAIN_PRIMER.md` | Who ASHAs, ANMs and MOs are, and the words to use in the interface. Read before writing any user-facing text. |
| `docs/UI_DESIGN_BRIEF.md` | The user's design instructions. If filled in, follow it. If it says "Claude decides", see §8. |
| `docs/decisions/ADR-TEMPLATE.md` | Format for architecture decision records. ADR-001 and ADR-002 are due in Phase 0. |

If this handoff and the implementation plan ever disagree, **this handoff wins on
process, the plan wins on technical content.** If they disagree on something
important, stop and ask the user.

---

## 1. Operating rules

These are not suggestions. They are the contract.

### R1 — One phase at a time, on command

Do not start a phase until the user explicitly tells you to. Do not roll into the
next phase because the current one finished early. When a phase is done, stop,
report, and wait.

At the start of a phase, before writing code:

1. State which phase you are in and its exit criteria (copy them from the plan).
2. State your plan for this session in 5–10 lines.
3. List any decisions you need from the user (see §2).
4. **Wait for the user's go-ahead.**

### R2 — Model discipline

| Work | Model |
|---|---|
| Writing, editing, refactoring, testing, debugging code | **Sonnet** |
| Architecture, phase planning, schema design, trade-off analysis, ADR writing, code review, experiment design, report structure | **Opus** |

Enforce this yourself:

- If the session is on **Opus** and the user asks you to write code, say so and
  ask them to switch to Sonnet before you begin.
- If the session is on **Sonnet** and the user asks for design, planning, or a
  hard architectural judgement, say so and suggest switching to Opus.
- A short design discussion inside a coding session is fine. A full phase plan is
  not — that is Opus work.

Never silently ignore this rule to save the user a step.

### R3 — Decision boundary

You decide small technical things by yourself. You escalate anything that changes
the shape of the project. See §2 for the full table. When in doubt, ask — but ask
**once, with options and a recommendation**, not with an open question.

### R4 — UI design

If the user has given UI design ideas, follow them. If not, you are free to make
creative design choices, within the constraints in §8. Do not block on this; do
not ask "what should the UI look like?" — propose, then build.

### R5 — Sub-phases when asked

Some phases are too big for one session. If the user says "split this phase":

1. Propose a numbered breakdown (P4.1, P4.2, P4.3 …).
2. Each sub-phase must have its own objective exit criterion, must be
   independently testable, and must leave the repository in a **working, committed
   state**.
3. Get approval for the breakdown, then implement **one sub-phase only**.

Do not split a phase on your own initiative unless you first say why and get
agreement.

### R6 — The invariants are absolute

Section 1 of the implementation plan lists invariants I1–I7. You may never write
code that breaks one, and you may never propose a shortcut that breaks one. If a
requested change would break an invariant, say so plainly and stop.

The three most commonly broken in practice:

- **I1** — the sync receipt write and the effect must be in **one** database
  transaction. Not two. Not "usually one".
- **I3** — `referral.current_state` is a cache. The event log is the truth.
- **I5** — double escalation is prevented by the unique partial index, not by an
  `if` statement in Python.

### R7 — Scope is frozen

Already excluded, with reasons, and **not open for reconsideration**: native
mobile app, CRDTs, WebSockets, real patient data, multilingual UI, SMS/IVR, full
ABDM/FHIR conformance, live government-system integration, ML drop-out
prediction.

If you think one of these would help, you may say so in one sentence and then
drop it. Do not build it.

### R8 — Instrumentation is built in, not added later

Every phase from P1 onward ships with structured JSON logging (`op_id`,
`referral_id`, `device_id`, `run_id` as fields), request timing written to a
table, and a `run_id` column set from an environment variable. See §12 of the
plan. Never say "we'll add logging later".

### R9 — Evidence discipline

Every session ends with:

- Commits made (small, frequent, honest messages — including ugly work).
- `docs/decisions/ADR-NNN.md` written for any architectural decision taken.
- Screenshots into `docs/screenshots/` the first time any screen works.
- `PROGRESS.md` updated (see §3).

---

## 2. What you decide vs what the user decides

### You decide alone (do not ask)

- Function, variable, and file names; internal module organisation inside the
  layout already fixed by §2.2 of the plan.
- How to split a function, when to extract a helper, internal refactoring.
- Which specific test cases to write for a stated behaviour, and test data.
- Error message wording, log message wording, code comments.
- Pytest fixtures, Playwright selectors, Alembic migration file names.
- CSS details, spacing, colour values, component internals — once the overall
  design direction is set.
- Patch versions of libraries already chosen in the plan.
- Which of two equivalent implementations to use, when both meet the spec.

### You stop and ask the user

- **Adding or removing any dependency** not already named in the plan.
- **Any database schema change** that is not written in the plan — new table, new
  column, changed type, dropped index.
- **Any API contract change** — endpoint paths, request/response shapes, status
  values (`accepted` · `accepted_stale` · `conflict` · `rejected`).
- **Changing, skipping, reordering, or merging a phase.**
- **Anything that touches an invariant, an ADR, or the frozen scope list.**
- **Anything that changes the experiments** (E1–E6), their parameters, or the
  data the report will be built from.
- **Auth model, roles, or the org-scoping rule.**
- **UI information architecture** — which screens exist, what each role sees.
- **Deployment targets and hosting.**
- Anything where you are about to spend more than roughly an hour of work on a
  path you are not confident about.

**How to ask:** state the decision in one line, give 2–3 concrete options with the
trade-off of each in one line, give your recommendation, then stop. Do not write
code for the options before the answer comes.

---

## 3. Session protocol

### Start of session

1. Read this handoff.
2. Read `PROGRESS.md`.
3. Read the plan section for the current phase **and the one after it** — not the
   whole plan.
4. Report: current phase, what is already done, exit criteria still open, plan
   for this session, decisions needed.
5. Wait.

### During the session

- Work in small commits. Run tests before saying anything works.
- If you hit a decision from the "ask" list, stop there. Do not guess and keep
  going.
- If you discover the plan is wrong or impossible, say so immediately with
  evidence. Do not quietly work around it.

### End of session

Update `PROGRESS.md` in this shape:

```markdown
# PROGRESS

## Current phase
P4 — Offline client (Week 5). Sub-phase P4.2 of 3.

## Done
- Dexie schema + device_id persistence (commit a1b2c3d)
- Lamport counter with pull-side max merge, unit tested

## Not done / in progress
- Optimistic UI writes: cache + outbox are not yet in one Dexie transaction

## Exit criteria status
- [x] Offline create → reload → data present
- [ ] Playwright test in CI
- [ ] Real-phone airplane-mode recording

## Next concrete step
Wrap the cache write and outbox append in a single db.transaction() in
client/src/db/mutations.ts, then write the Playwright offline test.

## Open questions for the user
- None
```

**Never mark a phase complete unless its exit criteria are objectively true.**
When you claim a phase is done, give the exact command the user can run to verify
it themselves (`make test`, `docker compose up` then a described click path, etc.).
"It should work" is not a completion report.

---

## 4. Phase map

Full detail is in the plan. This is the index.

| Phase | Week | Builds | Exit criterion |
|---|---|---|---|
| P0 | 1 | Skeleton, CI, injectable clock, auth stub | Compose up; CI green; Review-0 submitted |
| P1 | 2 | **Sync core on a one-field toy model** | Ops survive process kill; duplicate push is a no-op |
| P2 | 3 | Real schema, state machine, guards, RBAC | Referral traverses all states via API with role enforcement |
| P3 | 4 | Hardening, event-replay check, timeline endpoint | Review-I demoed live, not on slides |
| P4 | 5 | PWA, offline create, outbox, optimistic UI | Create in airplane mode; syncs on reconnect |
| P5 | 6 | Escalation scheduler + SSE dashboard | Breached SLA appears live without refresh |
| P6 | 7 | Identity resolution + gold set + review queue | E3 numbers exist in draft |
| P7 | 8 | Generator, integration + property + E2E tests | Review-II submitted |
| P8 | 9 | Run E1–E6, k6 load, deploy | All experiment tables complete |
| P9 | 10 | Chapters 4–5, appendices, recorded demo | Report submitted |

Two setup decisions from §3 of the plan must exist **before P1**: the injectable
clock, and the advisory lock that serialises sequence assignment. Both get an
ADR. Do not start P1 without them.

---

## 5. The four things that must not be got wrong

If you remember nothing else from the plan, remember these. Each one fails
silently, passes ordinary tests, and is expensive to find late.

1. **Receipt and effect in one transaction.** Claim the `op_id` first with
   `INSERT … ON CONFLICT DO NOTHING`, do the work, finalise the receipt — all
   inside the same transaction, one transaction per op, not per batch. A replay
   returns the stored result and applies nothing.
2. **Never call `datetime.now()` directly, anywhere.** Always go through the
   injected `Clock`. Experiments need simulated time; a single direct call breaks
   them and you will find out in week 9.
3. **Serialise sequence assignment** with `pg_advisory_xact_lock(4711)` before
   appending an event, so sequence order equals commit order. Without it the pull
   cursor skips events, intermittently.
4. **Never fuzzy-match without blocking first.** Always scope candidates by
   village and phone prefix before scoring. Unblocked matching merges two
   different people and the error is invisible.

---

## 6. Quality bar — definition of done for any unit of work

- The code runs inside `docker compose up`, not only on the host.
- Tests exist at the right layer (unit / property / integration / E2E / fault) and
  pass in CI.
- Structured logging and timing are present for anything new that handles a
  request or an op.
- Migrations are new Alembic revisions. **Never edit a shipped migration.**
- Nothing is committed that only works with a manual step the user has to
  remember.
- `PROGRESS.md` reflects reality.

---

## 7. Communication style with the user

The user is a student running this project alone, alongside coursework, and is not
a native English speaker. So:

- Use plain, common words. Explain a term the first time you use it.
- Be direct. If something is a bad idea, say it in one sentence and say why.
- Prefer short prose to long bullet dumps when explaining.
- Do not flatter. Do not pad. Do not repeat the plan back at him.
- When you make a technical choice on your own, mention it in one line so he can
  overrule it — he has to defend this code to a panel, so he cannot be surprised
  by his own repository.
- Never hide a failure. A test that is skipped, a criterion not met, a shortcut
  taken — say it plainly in the session report.

---

## 8. UI guidance

**If a Claude Design handoff bundle is provided, follow it** for layout, colour,
spacing, type, and component appearance. Prefer the bundle over your own taste,
and do not restyle it.

**But the bundle governs appearance only, never architecture.** Where a design
implies behaviour that contradicts the implementation plan, the plan wins and you
say so. Specifically: never add a loading state where the interface should be
reading from the local cache; never introduce a screen, field, or feature that
appears in the design but is not in the plan's scope; never let a design imply a
server round-trip on the offline path. If the design shows something the
architecture cannot support, stop and tell the user which part and why, rather
than quietly building the interface the design shows.

If no design bundle is provided, design freely within these constraints:

- **Mobile-first.** ASHA and ANM users are on cheap Android phones in the field.
  Desktop layout matters only for the supervisor dashboard.
- **Offline must be visible.** The user must always be able to tell: am I online,
  how many operations are waiting, when did I last sync. A quiet failure is worse
  than an ugly banner.
- **Optimistic UI reads only from the local cache**, so the screen looks identical
  online and offline. This is the point of the architecture — do not special-case
  the online path.
- **Big touch targets, few taps per task.** Creating a referral is the most common
  action; make it the shortest path.
- **State must be obvious at a glance** — the eight referral states need clear,
  distinguishable visual treatment, and escalation must be immediately readable.
- **Low bandwidth.** No heavy image assets, no large font downloads, no animation
  that hides latency.
- Accessible contrast, readable at arm's length in daylight.
- Keep the design consistent once chosen. Do not restyle in a later phase without
  asking.

The supervisor dashboard is the demo showpiece: a breached SLA appearing live
without a page refresh is the twenty seconds the panel will remember. Design it
to make that moment obvious.

---

## 9. Kickoff checklist

**First, run `docs/SETUP_PREFLIGHT.md` and report the result.** Do not install
anything yourself; report what is missing and wait.

Then get answers to these from the user (ask them all at once):

1. **Repository and package name** — the plan says `setucare/`, the project is now
   NirantharSeva. Which name goes in the repo, the Docker services, and the UI?
2. **Python tooling** — `uv` or `venv` + `pip`? Pick one and commit the lockfile.
3. **Are UI design ideas coming?** If yes, wait for them before P4. If no, you
   design under §8.
4. **Git hosting and CI** — GitHub Actions is assumed by the plan; confirm.
5. **Anything already built** that should be kept rather than rewritten.

---

## 10. `CLAUDE.md`

`CLAUDE.md` at the repository root is loaded automatically at the start of every
session and is re-read after compaction. It already exists and holds a short form
of these rules. Keep it short — long instruction files consume context and are
followed less consistently. If a rule keeps being missed, make it shorter and
more concrete in `CLAUDE.md` rather than longer here.

Do not copy this handoff into `CLAUDE.md`.

---

## 11. First message of the first session

> Read `docs/HANDOFF_CLAUDE_CODE.md` in full, then `PROGRESS.md`, then
> `docs/SETUP_PREFLIGHT.md`.
>
> Do not write any code and do not install anything. Run the preflight checks,
> report the full result in one message, ask me the kickoff questions from §9,
> and then stop. We will start Phase 0 only when I say so.
