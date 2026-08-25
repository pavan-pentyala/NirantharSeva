# NirantharSeva

Offline-first referral continuity system for community health workflows.
Individual MTech case-study project.

An ASHA worker in a village with no signal creates a referral on her phone.
It is saved locally, appears immediately on her screen, and sends itself
when the network comes back — exactly once, even if the app is killed
mid-send or the server dies mid-request. A doctor at the health centre
advances it with one tap. A supervisor watches a breached deadline appear
on a live dashboard with no page refresh. Nothing is lost, and every state
change is recoverable from an append-only event log.

**All data in this system is synthetic.** Every screen carries a
"Demonstration system — synthetic data only" marker.

## Status

**Phases 0–8 complete.** Phase 9 (deployment-ready configuration, the demo
path, submission readiness) is in progress — see `PROGRESS.md` for the
current sub-phase, which is the file kept honest session to session.

All seven screens are real and working: offline referral creation and
listing, referral detail with a full timeline, MO incoming-referrals queue,
a live supervisor dashboard (breached SLAs appear with no reload), an
identity-review queue for possible duplicate patients, and login. Nothing
in the interface is a placeholder.

Also built: an escalation scheduler that runs as its own process, org-scoped
visibility enforced identically at every read, fuzzy patient-identity
resolution with a review queue for uncertain matches, a synthetic-cohort
generator used to run six experiments (E1–E6) end to end, a k6 load test,
and fault-injection tests that kill the real API process mid-batch.

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

| User | Password | Role | Sees |
|---|---|---|---|
| `asha_a` | `dev` | ASHA | Her own village's referrals (Village A); creates new ones |
| `asha_b` | `dev` | ASHA | Her own village's referrals (Village B) |
| `anm1` | `dev` | ANM | The identity-review queue — possible duplicate patients |
| `mo1` | `dev` | MO | Incoming referrals at the health centre, one-tap advance |
| `supervisor1` | `dev` | SUPERVISOR | The live dashboard — open referrals, overdue, act now |

Roles and org scope always come from the server, never from what the client
claims — the login screen carries no role picker by design.

## Run the demo

```bash
bash server/scripts/demo.sh
```

Resets the application database, migrates, seeds the fixture district, seeds
a small set of referrals in the specific states the demo needs (one already
overdue, one ready for the MO to advance, one pending identity-review pair),
and starts a demo-scale scheduler so a breach can appear live while someone
is watching. Prints the dashboard URL, every login, and the numbered click
path. `make demo` is a thin wrapper around the same script (`make` itself is
not installed on the reference machine — see `PROGRESS.md`). The full
walkthrough — what to say, how long each beat takes, what to fall back to if
a step misbehaves — is `docs/DEMO_SCRIPT.md`.

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

269 tests pass; `alembic heads` is `0009`.

Client end-to-end, including offline, kill-resume, and two-device-conflict
fault tests — 11 Playwright specs. **Two servers must be up:** `:5173` (dev)
and `:4173` (the production build with its real service-worker precache,
which the offline-reload test needs).

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

## Run the experiments

```bash
make experiments EXP=E1   # or E2 / E3 / E6
```

Runs one experiment's grid, then regenerates its tables, figures and an
HTML dashboard from the raw results alone (`experiments/analysis.py`). Every
committed result lives in `server/results/<experiment>/` — the repository
root's own `results/` directory was removed as a stray duplicate; this is
the one canonical location. Wall-clock cost, measured not estimated:

| Experiment | What it measures | Wall-clock |
|---|---|---|
| E1 | Escalation's effect on referral closure, swept over drop-out and response rate | ~65 min (45 cells) |
| E2 | SLA-window sensitivity | ~3.7 h (12 cells) |
| E3 | Identity-resolution precision/recall across thresholds | ~30 s (18 rows) |
| E4 | Fault injection (kill/retry, two-device conflict, idempotent replay) | a few minutes, not a grid |
| E5 | Endpoint latency, with and without an index | ~10 min, not a grid |
| E6 | Unresolvable-referral rate at full cohort scale | ~56 min (3 cells) |

## Deploy it

`docker-compose.prod.yml` is a deployment-**ready** configuration, not a
deployed instance (D43, `docs/decisions/ADR-018.md`) — local Compose above
stays the primary way to run and demo this project. It differs from
`docker-compose.yml` in every way a real deployment needs: no source bind
mounts (each image is a self-contained artifact), no `--reload` and no
Vite dev server (the client is a built bundle served by nginx, which also
reverse-proxies `/api/*` to the API — `client/nginx.conf`), the database
port is never published to the host, CORS is a required real origin
instead of `*`, and every secret has no development default — a missing
one fails `docker compose up` outright rather than silently falling back
to a published dev value.

```bash
cp .env.prod.example .env.prod   # fill in POSTGRES_PASSWORD, DATABASE_URL,
                                  # JWT_SECRET, CORS_ORIGINS — see the file
docker compose -p nirantharseva-prod -f docker-compose.prod.yml --env-file .env.prod up -d --build
curl http://localhost:8000/health          # the API directly
curl http://localhost:8080/api/health      # through the client's own reverse proxy
```

**Always pass `-p nirantharseva-prod`** (or any name other than the
directory's default) if the dev stack might also be running — Compose
derives its project name from the current directory by default, and both
files live in this one; without a distinct `-p`, bringing the prod
config up **recreates the dev stack's own containers under the same
names**, discarding them (a real mistake made and recovered from while
building this — the named `pgdata` volume survived, since it's addressed
by name, but every dev container had to be brought back with a plain
`docker compose up -d` afterward). Tear down with the same flags plus
`-v`, so the scratch `pgdata_prod` volume doesn't linger:

```bash
docker compose -p nirantharseva-prod -f docker-compose.prod.yml --env-file .env.prod down -v
```

**What "deployment-ready" means here, precisely** (ADR-018's own
standard): the config has been brought up and verified to actually serve
— not just written. It has not been checked under load, over a real
network, behind a real TLS-terminating proxy, or against a managed
Postgres. No hosting account or live URL exists for this project, and none
of its other deliverables depend on one.

## The advisory lock's write-latency cost

`docs/IMPLEMENTATION_PLAN.md` §3 asks for one measured sentence:
`server/results/e5_lock/summary.md` has it. Under a write-heavy, no-sleep
k6 profile built specifically to contend (`experiments/k6/lock.js`, 25
write VUs + 5 read VUs, 30s, run twice against a scratch database — once
with the sequencing lock active, once temporarily neutralised), the lock
adds roughly 70ms to `POST /sync/push`'s median latency and roughly 94ms
at p95, while two read endpoints that never touch the lock moved by only
9–12ms, in the *opposite* direction — the control that makes the write-path
number trustworthy rather than noise. Accepted in exchange for
`referral_event.seq` order always matching commit order, which is what
keeps `/sync/pull`'s cursor from silently skipping events under concurrent
writers (ADR-002).

## How it works

Every write is an operation with a client-generated `op_id`, queued in an
IndexedDB outbox and pushed when there is signal. The server claims the
`op_id` and applies the effect **in one transaction**, so a replayed push
returns the stored answer and applies nothing. Reads come from a local
cache built by folding a single sequence-ordered event stream, so the
interface is identical online and offline. A separate scheduler process
sweeps for breached SLAs and pushes live updates to the dashboard over
Server-Sent Events.

The decisions most worth reading, in `docs/decisions/`:

| ADR | Decision |
|---|---|
| 001 | The clock is injected, never called directly |
| 002 | Event appends are serialised with a transaction-scoped advisory lock |
| 003 | Conflict resolution records both writes and never picks a clinical winner |
| 004 | One generic pull envelope with a typed payload, one shared event sequence |
| 005 | Visibility is the org subtree, applied identically at every read site |
| 006 | The server derives org identity; a device never asserts its own |
| 007 | I3 is verified by a full-database replay scan, run as a CLI |
| 008 | The timeline returns every event, tagged by whether it advanced the state |
| 009 | The patient arrives inline with the referral |
| 010 | The pull payload carries a referral snapshot, not just its transition |
| 011 | Escalations cross the process boundary by Postgres LISTEN/NOTIFY |
| 012 | The dashboard stream authenticates by query-string token |
| 013 | The identity merge decision is a plain REST call, not a sync operation |
| 014 | Blocking is by village always; phone narrows only when both records have one |
| 015 | A generated cohort is loaded by replaying it through `/sync/push` |
| 016 | One database and one OS process per experiment cell |
| 017 | E1 reports measured detection and modelled recovery as two separate results |
| 018 | Deployment-ready configuration, not a deployed instance |

## Documentation map

| File | What it is |
|---|---|
| `PROGRESS.md` | Where the project actually is. Read first. |
| `docs/IMPLEMENTATION_PLAN.md` | The full ten-week build spec |
| `docs/HANDOFF_CLAUDE_CODE.md` | Operating rules for AI-assisted sessions on this repo |
| `docs/PHASE*_PLAN.md` | Per-phase build order, decisions, exit criteria |
| `docs/decisions/` | Architecture decision records, ADR-001 through ADR-018 |
| `docs/OBSERVATIONS.md` | Hard-won lessons, append-only, one section per phase |
| `docs/Observations_for_report.md` | Raw material for the written report — results, framing, limitations |
| `docs/DEMO_SCRIPT.md` | The click path for the live demo, and what to fall back to |
| `docs/UI_DESIGN_BRIEF.md` + `docs/design_handoff_ui_screens/` | The design brief and its seven screen references |
| `docs/screenshots/` | What each screen actually renders |
| `server/results/` | Every experiment's raw data, tables, figures and dashboard (E1–E6), plus `e5_lock/`'s advisory-lock measurement |

The written report itself is deliberately not in this repository — it is
being built separately, after Phase 9.

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
