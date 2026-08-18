# NirantharSeva

Offline-first referral continuity system for community health workflows.
Individual MTech case-study project, graded by panel review. Deliverables are a
working demo, experiment results, and a written report.

## Read before doing anything

1. `docs/HANDOFF_CLAUDE_CODE.md` — the operating rules. Read it in full.
2. `PROGRESS.md` — where the last session stopped.
3. The current phase section of `docs/IMPLEMENTATION_PLAN.md`, and the one after
   it. Not the whole plan.

Do not write code before doing this.

## Hard rules

- **One phase at a time**, only when the user explicitly says to start it. When
  the phase is done, stop and report. Do not continue into the next phase.
- **Sonnet writes code. Opus does design and planning.** If the wrong model is
  active for the work being asked, say so and ask the user to switch.
- **Small technical choices: decide yourself.** Names, tests, refactoring, CSS
  details, helper functions.
- **Ask the user before:** adding a dependency, changing the schema, changing an
  API contract, changing scope, skipping or reordering a phase, changing auth or
  roles, changing anything the experiments depend on, deciding which screens
  exist.
- **Never claim a phase is complete** unless its exit criteria are objectively
  true. Give the user a command to verify it themselves.

## Correctness rules that fail silently — never break these

- Never call `datetime.now()`. Always use the injected `Clock`.
- The sync receipt write and its effect go in **one** transaction, one
  transaction per operation.
- `SELECT pg_advisory_xact_lock(4711)` before every event append.
- Never fuzzy-match patients without blocking by village and phone prefix first.
- `referral.current_state` is a cache. The event log is the truth.
- Never edit a shipped Alembic migration. Add a new one.

## Frozen scope — do not build these

Native mobile app, CRDTs, WebSockets, real patient data, multilingual UI,
SMS/IVR, full ABDM/FHIR conformance, live government-system integration, ML
drop-out prediction. All excluded deliberately, with reasons.

## Stack

PostgreSQL 16 · FastAPI + SQLAlchemy + Alembic · APScheduler · React 18 +
TypeScript + Vite · vite-plugin-pwa · Dexie.js · Server-Sent Events · rapidfuzz ·
JWT + argon2id · Docker Compose · GitHub Actions · pytest + Hypothesis ·
Playwright · k6

Everything runs through Docker Compose. Nothing is installed on the host.

## Commands

```
make up      # start the stack
make down    # stop it
make test    # unit + integration tests
make demo    # reset db, seed cohort, print the demo script
make experiments
```

## End of every session

Update `PROGRESS.md`: what is done, what is not, the exact next step, open
questions. Commit. Screenshot any screen that worked for the first time into
`docs/screenshots/`.

## Talking to the user

He is a student working alone, and not a native English speaker. Use plain words.
Be direct. If something is a bad idea, say it in one sentence with the reason.
Do not flatter, do not pad, do not repeat the plan back at him. Tell him about
every choice you made on your own — he has to defend this repository to a panel.

## Commits

- Do not add "Co-Authored-By: Claude" or any Claude/Anthropic attribution line
  to commit messages.
- No "Generated with Claude Code" footer either.
