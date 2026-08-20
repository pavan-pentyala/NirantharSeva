# NirantharSeva

Offline-first referral continuity system for community health workflows.
Individual MTech case-study project.

An ASHA worker in a village with no signal creates a referral on her phone.
It is saved locally, appears immediately on her screen, and sends itself
when the network comes back — exactly once, even if the app is killed
mid-send or the server dies mid-request. A doctor at the health centre
advances it with one tap. Nothing is lost, and every state change is
recoverable from an append-only event log.

**All data in this system is synthetic.** Every screen carries a
"Demonstration system — synthetic data only" marker.

## Status

**Phases 0–4 complete.** Phase 5 (escalation + live supervisor dashboard)
is planned but not built — see `PROGRESS.md` for the current state, which
is the file kept honest session to session.

Working today: offline referral creation, optimistic UI reading only from
IndexedDB, an outbox that survives tab death, conflict detection with both
sides preserved, org-scoped visibility, an event-log replay verifier, and
five real screens installable as a PWA. Screens for the supervisor
dashboard and the identity-review queue render as routed placeholders
naming the phase that builds them.

## Run it

```bash
cp .env.example .env
docker compose up --build
```

- Client: http://localhost:5173
- API health: http://localhost:8000/health

Then seed the fixture district and log in:

```bash
docker compose run --rm api python -m app.seed
```

| User | Password | Sees |
|---|---|---|
| `asha_a` | `dev` | Her own village's referrals; creates new ones |
| `mo1` | `dev` | Incoming referrals at the health centre, one-tap advance |
| `anm1` / `supervisor1` | `dev` | Placeholder screens (Phases 5–6) |

Roles and org scope always come from the server, never from what the client
claims — the login screen's role grid is display-only by design.

## Test it

Server — unit, integration, property and replay-verification, against a
separate `nirantharseva_test` database, never dev data:

```bash
# The test database is created automatically on first start; this resets it,
# which is worth doing before trusting a red run.
docker compose exec db psql -U postgres \
  -c "DROP DATABASE IF EXISTS nirantharseva_test;" -c "CREATE DATABASE nirantharseva_test;"
docker compose run --rm -e DATABASE_URL="postgresql+asyncpg://postgres:dev@db:5432/nirantharseva_test" \
  api sh -c "alembic upgrade head && python -m app.seed && pytest -q && python -m app.verify_replay"
```

Client end-to-end, including the offline/kill-resume fault tests. **Two
servers must be up:** `:5173` (dev) and `:4173` (the production build with
its real service-worker precache, which the offline-reload test needs).

```bash
docker compose exec client npm run build
docker compose exec -d client npm run preview
cd client && npx playwright test
```

Fault injection under real process death (not mocked):

```bash
bash server/tests/fault/kill_api.sh
```

`Makefile` documents shorter aliases (`make up`, `make test`), but `make`
is not installed on the reference dev machine — run the `docker compose`
commands directly, or use the Makefile as a command reference elsewhere.

## How it works

Every write is an operation with a client-generated `op_id`, queued in an
IndexedDB outbox and pushed when there is signal. The server claims the
`op_id` and applies the effect **in one transaction**, so a replayed push
returns the stored answer and applies nothing. Reads come from a local
cache built by folding a single sequence-ordered event stream, so the
interface is identical online and offline.

The five decisions most worth reading, in `docs/decisions/`:

| ADR | Decision |
|---|---|
| 001 | An injectable `Clock` — nothing calls `datetime.now()`, so a 120-hour SLA experiment can run in minutes |
| 002 | Serialised sequence assignment, so sequence order equals commit order and the pull cursor cannot skip |
| 003 | The conflict policy — what happens when two offline devices disagree |
| 005 | Org-subtree scoping as a SQL predicate, never a post-fetch filter |
| 009 / 010 | How a patient arrives with a referral, and why pulled events carry a snapshot |

## Documentation map

| File | What it is |
|---|---|
| `PROGRESS.md` | Where the project actually is. Read first. |
| `docs/IMPLEMENTATION_PLAN.md` | The full ten-week build spec |
| `docs/PHASE*_PLAN.md` | Per-phase build order, decisions, exit criteria |
| `docs/decisions/` | Architecture decision records, ADR-001 onward |
| `docs/PHASE2_OBSERVATIONS.md` | Hard-won lessons, append-only, one section per phase |
| `docs/UI_DESIGN_BRIEF.md` + `docs/design_handoff_ui_screens/` | The design brief and its seven screen references |
| `docs/screenshots/` | What each screen actually renders |
| `docs/HANDOFF_CLAUDE_CODE.md` | Operating rules for AI-assisted sessions on this repo |

## Stack

PostgreSQL 16 · FastAPI + SQLAlchemy + Alembic · APScheduler · React 18 +
TypeScript + Vite · vite-plugin-pwa · react-router-dom · Dexie.js ·
Server-Sent Events · rapidfuzz · JWT + argon2id · Docker Compose · GitHub
Actions · pytest + Hypothesis · Playwright · k6

Everything runs through Docker Compose. Nothing is installed on the host.

## Scope

Deliberately excluded, with reasons recorded: native mobile app, CRDTs,
WebSockets, real patient data, multilingual UI, SMS/IVR, full ABDM/FHIR
conformance, live government-system integration, ML drop-out prediction.
