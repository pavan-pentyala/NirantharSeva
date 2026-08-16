# NirantharSeva — Technical Implementation Plan


## 0\. How to use this document

Sections 1–3 are read once, at the start. Sections 4–13 are the phases; read the
phase you are in and the one after it, not the whole thing. Section 14 onward is
reference material you will come back to.

Two rules that override anything else in here:

1. **If a phase's exit criterion is not objectively true, you are still in that
phase.** Do not start the next one because the calendar says so. Tell your
guide instead — a week of slip declared early is a conversation; a week of
slip discovered at a review is a problem.
2. **Instrumentation is not a phase.** It is built into every phase. Section 12
explains what to capture. If you skip it, Week 9 becomes archaeology.

\---

## 1\. Invariants

These are the properties the system must never violate. Every design decision
below exists to protect one of them. When you are unsure whether a shortcut is
acceptable, check it against this list.

|#|Invariant|Enforced by|
|-|-|-|
|I1|An operation submitted by a client is applied **at most once**, no matter how many times it is sent.|`sync\_receipt` written in the *same transaction* as the effect|
|I2|No operation accepted by the server is ever silently lost.|Append-only `referral\_event`; outbox rows only cleared on confirmed response|
|I3|A referral's `current\_state` is always derivable by replaying its event log.|`current\_state` is a cache, never the source of truth|
|I4|A state transition can only be performed by a permitted role.|Server-side guard table, checked at apply time|
|I5|A referral is never escalated twice for the same breached state.|Unique partial index, not application logic|
|I6|A losing write in a conflict is never deleted.|It stays in `referral\_event`; `sync\_conflict` records the pair|
|I7|Every experiment result is reproducible from a seed and a config file.|Seeded generator, config captured per run|

**I1 deserves special attention.** The single most likely correctness bug in this
project is applying an effect and then crashing before recording the receipt, so
that a retry applies it a second time. The receipt write and the effect must be
in one transaction. Not two transactions. Not "usually one transaction." One.

\---

## 2\. Environment and square-zero setup

### 2.1 Toolchain

|Tool|Version|Note|
|-|-|-|
|Docker + Compose v2|current|The whole stack runs here; this is your demo path|
|Python|3.12|`uv` or `venv`+`pip`, your choice — pick one and commit the lockfile|
|Node|20 LTS|For the client|
|PostgreSQL|16|Via Compose, never installed on the host|
|Git|any|Commit from day one, including the throwaway spikes|

Do not install Postgres on your laptop. Everything through Compose, so that
"it works on my machine" and "it works at the review" are the same statement.

### 2.2 Repository layout

Create this on day one, empty. Having the shape in place stops you inventing
structure at 1 a.m. in week 6.

```
NirantharSeva/
├── docker-compose.yml
├── Makefile                    # make up / down / test / demo / experiments
├── .env.example
├── README.md
├── docs/
│   ├── IMPLEMENTATION\_PLAN.md  # this file
│   ├── decisions/              # ADR-001.md, ADR-002.md ...
│   └── mom/                    # minutes of meeting, one file per week
├── server/
│   ├── pyproject.toml
│   ├── alembic/
│   └── app/
│       ├── main.py
│       ├── config.py
│       ├── db.py
│       ├── clock.py            # ← read §3 before writing anything else
│       ├── models/             # SQLAlchemy ORM
│       ├── schemas/            # Pydantic request/response
│       ├── domain/
│       │   ├── states.py       # state machine + guards, pure functions
│       │   └── errors.py
│       ├── sync/
│       │   ├── push.py
│       │   ├── pull.py
│       │   └── conflicts.py
│       ├── scheduler/
│       │   └── escalation.py
│       ├── linkage/
│       │   ├── normalize.py
│       │   ├── blocking.py
│       │   ├── scoring.py
│       │   └── pipeline.py
│       ├── api/
│       │   ├── auth.py  sync.py  referrals.py
│       │   └── patients.py  dashboard.py  admin.py
│       └── instrumentation/
│           ├── logging.py
│           └── timing.py
│   └── tests/
│       ├── unit/  integration/  property/  fault/
├── client/
│   ├── package.json
│   ├── vite.config.ts
│   ├── src/
│   │   ├── db/                 # Dexie schema, outbox
│   │   ├── sync/               # engine, lamport clock, backoff
│   │   ├── api/
│   │   ├── pages/  components/
│   │   └── main.tsx
│   └── tests/                  # Playwright
├── generator/
│   ├── cohort.py  names.py  timeline.py  cli.py
├── experiments/
│   ├── runner.py  e1.py … e6.py  analysis.py
└── results/                    # committed; this is your Chapter 4
```

### 2.3 Compose skeleton

Four services. Get this running and returning a health check **before** writing
any domain code — that is the Week 0 exit criterion.

```yaml
services:
  db:
    image: postgres:16
    environment: \[POSTGRES\_PASSWORD=dev, POSTGRES\_DB=NirantharSeva]
    ports: \["5432:5432"]
    healthcheck:
      test: \["CMD-SHELL", "pg\_isready -U postgres"]
      interval: 3s
    volumes: \[pgdata:/var/lib/postgresql/data]
  api:
    build: ./server
    depends\_on: {db: {condition: service\_healthy}}
    environment: \[DATABASE\_URL=..., JWT\_SECRET=dev, CLOCK\_MODE=real]
    ports: \["8000:8000"]
  scheduler:
    build: ./server
    command: python -m app.scheduler.run
    depends\_on: {db: {condition: service\_healthy}}
  client:
    build: ./client
    ports: \["5173:5173"]
volumes: {pgdata: {}}
```

Note the scheduler is a **separate service** from the API. This matters: it means
you can kill the API mid-sync without stopping escalation, and vice versa, which
is exactly what E4 needs. It also stops the scheduler running N times when you
scale the API.

### 2.4 CI from day one

GitHub Actions, one workflow, running on every push: lint, unit tests,
integration tests against a Postgres service container. Add it in Week 1 while
there is almost nothing to test. Adding CI to a large broken codebase in week 8
is a day you will not have.

\---

## 3\. Two decisions to make before writing any code

These are cheap now and expensive later. Both must be in place before Phase 1.

### 3.1 The clock must be injectable

Your SLA windows are 24 to 120 hours. Your experiments sweep across them. You
cannot run experiments in real time — E2 alone would take weeks.

So the system never calls `datetime.now()` directly. Anywhere. It asks a clock.

```python
# app/clock.py
from datetime import datetime, timedelta, timezone
from typing import Protocol

class Clock(Protocol):
    def now(self) -> datetime: ...

class RealClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)

class SimulatedClock:
    """Virtual time. Experiments advance it explicitly."""
    def \_\_init\_\_(self, start: datetime):
        self.\_now = start
    def now(self) -> datetime:
        return self.\_now
    def advance(self, \*\*kwargs) -> None:
        self.\_now += timedelta(\*\*kwargs)
```

Wire it as a FastAPI dependency; the scheduler takes it as a constructor
argument. `CLOCK\_MODE=real|simulated` selects at startup.

Retrofitting this in Week 9 means touching every module you have written.
Doing it now costs twenty minutes.

**Panel value:** this is also your answer to "how did you run a 120-hour SLA
experiment in a ten-week project?" — which is a question you will be asked.

### 3.2 Sequence assignment must be serialised

This one is subtle and it will silently corrupt your sync if you get it wrong.

`referral\_event.seq BIGSERIAL` gives you an ordering for the pull cursor. But
sequence values are allocated *before* commit, not at commit. So transaction A
can take `seq=100`, transaction B take `seq=101`, and B commit first. A client
pulling `since=99` sees 101, advances its cursor to 101, and **never sees event
100** when A commits a moment later. That event is lost to that client forever.
Worse, it is intermittent, so it will pass every test you write until it doesn't.

Fix: serialise event appends with a transaction-scoped advisory lock, so that
sequence order equals commit order.

```python
SEQ\_LOCK = 4711  # arbitrary constant, document it

async def append\_event(session, ...):
    await session.execute(text("SELECT pg\_advisory\_xact\_lock(:k)"), {"k": SEQ\_LOCK})
    # ... insert into referral\_event; lock releases at commit
```

Yes, this serialises all writes. At your scale that is irrelevant, and you can
**measure the cost in E5 and report it** — "the sequencing lock adds Xms to p95
write latency, accepted in exchange for a gap-free pull cursor" is a much better
Chapter 4 sentence than silence.

Record both of these as ADRs in `docs/decisions/`. They are the two decisions a
sharp panel member is most likely to probe.

\---

## 4\. Phase map

|Phase|Week|Dates|Builds|Exit criterion|
|-|-|-|-|-|
|P0|1|Aug 3–9|Skeleton, CI, clock, auth stub. **Review-0**|Compose up; CI green; Review-0 submitted|
|P1|2|Aug 10–16|**Sync core on a toy model**|Ops survive process kill; duplicate push is a no-op|
|P2|3|Aug 17–23|Real schema, state machine, guards, RBAC|A referral traverses all states via API with role enforcement|
|P3|4|Aug 24–30|Hardening + writing. **Review-I**|Review-I demoed live, not on slides|
|P4|5|Aug 31–Sep 6|PWA, offline create, outbox, optimistic UI|Create in airplane mode; syncs on reconnect|
|P5|6|Sep 7–13|Escalation scheduler + SSE dashboard|Breached SLA appears live without refresh|
|P6|7|Sep 14–20|Identity resolution + gold set + review queue|E3 numbers exist in draft|
|P7|8|Sep 21–27|Generator, integration tests, report 50%. **Review-II**|Review-II submitted|
|P8|9|Sep 28–Oct 4|Run E1–E6, k6, deploy|All experiment tables complete|
|P9|10|Oct 5–11|Chapters 4–5, appendices. **Review-III**|Report submitted; demo recorded|

**Why sync first.** It is the hardest component, the one every later phase
depends on, and the only one whose failure cannot be worked around. Building it
against a one-field toy model — no patients, no roles, no referrals, one table
with one integer column — means you debug distributed-systems problems in
isolation instead of tangled with domain bugs. When it works, you throw the toy
model away and keep the engine.

\---

## 5\. Phase 1 — Sync core (Week 2)

The most important week of the project.

### 5.1 Toy model

```sql
CREATE TABLE toy(id UUID PRIMARY KEY, value INT NOT NULL, updated\_at TIMESTAMPTZ);
CREATE TABLE toy\_event(
  seq BIGSERIAL PRIMARY KEY, toy\_id UUID, old\_value INT, new\_value INT,
  op\_id UUID UNIQUE, device\_id TEXT, lamport BIGINT, device\_time TIMESTAMPTZ,
  server\_time TIMESTAMPTZ DEFAULT now());
CREATE TABLE sync\_receipt(
  op\_id UUID PRIMARY KEY, received\_at TIMESTAMPTZ DEFAULT now(),
  result TEXT NOT NULL, detail JSONB, server\_seq BIGINT);
```

That is the entire domain for this week. Resist adding to it.

### 5.2 Push contract

```
POST /sync/push
{ "device\_id": "d-1",
  "ops": \[ {"op\_id":"uuid","entity":"toy","entity\_id":"uuid",
            "operation":"set\_value","payload":{"value":42},
            "lamport":17,"device\_time":"2026-08-10T09:00:00Z"} ] }

200 { "results": \[ {"op\_id":"uuid","status":"accepted",
                    "server\_seq":1183,"detail":null} ],
      "server\_lamport": 1200 }
```

`status` is one of `accepted` · `accepted\_stale` · `conflict` · `rejected`.

### 5.3 The push handler — the core algorithm

Read this carefully; it encodes I1.

```python
async def handle\_push(session\_factory, device\_id, ops, clock):
    results = \[]
    for op in ops:                      # one transaction PER OP, not per batch
        async with session\_factory() as s, s.begin():
            # 1. Claim the op\_id. Atomic; wins the race against a concurrent retry.
            claimed = await s.execute(
                text("""INSERT INTO sync\_receipt(op\_id, result, detail)
                        VALUES (:id,'in\_progress',NULL)
                        ON CONFLICT (op\_id) DO NOTHING
                        RETURNING op\_id"""), {"id": op.op\_id})
            if claimed.first() is None:
                # Replay. Return the stored result verbatim; apply nothing.
                prior = await s.execute(
                    text("SELECT result, detail, server\_seq FROM sync\_receipt WHERE op\_id=:id"),
                    {"id": op.op\_id})
                r = prior.one()
                results.append(Result(op.op\_id, r.result, r.detail, r.server\_seq))
                continue

            # 2. Serialise sequence assignment (see §3.2)
            await s.execute(text("SELECT pg\_advisory\_xact\_lock(4711)"))

            # 3. Validate + apply. In P2 this becomes the state machine guard.
            outcome = await apply\_operation(s, op, device\_id, clock)

            # 4. Record the real result — SAME transaction as the effect.
            await s.execute(
                text("""UPDATE sync\_receipt
                        SET result=:r, detail=:d, server\_seq=:q WHERE op\_id=:id"""),
                {"r": outcome.status, "d": outcome.detail,
                 "q": outcome.server\_seq, "id": op.op\_id})
            results.append(outcome)
    return results
```

Three things to notice. One transaction per op, so a rejection does not roll back
its neighbours. The receipt is *claimed* before the work and *finalised* with the
work, so a crash anywhere leaves either nothing or everything. And a replay never
re-executes — it replays the stored answer, so the client sees an identical
response the second time.

### 5.4 Pull contract

```
GET /sync/pull?since=1183\&limit=500
200 { "events": \[...ordered by seq...], "cursor": 1204, "has\_more": false }
```

Client applies events in order, then sets
`lamport = max(local\_lamport, max(e.lamport for e in events))` and advances the
cursor. Because of §3.2, a gap-free scan of `seq` is safe.

### 5.5 Client outbox and flush loop

```ts
// Dexie
db.version(1).stores({
  outbox: 'op\_id, status, lamport, next\_retry\_at',
  toy\_cache: 'id',
  sync\_meta: 'key'
});

let flushing = false;

export async function flush() {
  if (flushing || !navigator.onLine) return;
  flushing = true;
  let batch: Op\[] = \[];
  try {
    batch = await db.outbox
      .where('status').anyOf('pending', 'inflight')
      .filter(o => !o.next\_retry\_at || o.next\_retry\_at <= Date.now())
      .sortBy('lamport');                       // device order preserved
    if (!batch.length) return;

    await db.outbox.bulkUpdate(batch.map(o =>
      ({ key: o.op\_id, changes: { status: 'inflight' } })));

    const res = await api.push({ device\_id: deviceId, ops: batch });
    await applyResults(res.results);            // see below
  } catch (e) {
    await scheduleBackoff(batch);               // stays 'inflight'; safe to retry
  } finally {
    flushing = false;
  }
}
```

`applyResults` — for `accepted` and `accepted\_stale`, mark the op `synced`. For
`conflict` or `rejected`, mark it accordingly **and re-pull that entity from the
server, overwriting local cache**. Do not hand-write inverse operations to undo
optimistic updates; server truth plus overwrite is simpler and cannot drift.

Trigger `flush()` on: the `online` event, a 15-second timer, after every local
mutation, and on `visibilitychange`. The single-flight guard is what stops these
four triggers stampeding.

### 5.6 Exit criteria — all must be demonstrable

* \[ ] Create 50 ops offline; reconnect; all 50 land exactly once.
* \[ ] `docker kill` the API mid-batch; retry; final state identical, no duplicates.
* \[ ] Kill the *client* mid-push (DevTools → close tab); reload; ops resume from
`inflight` and land exactly once.
* \[ ] POST the same batch five times; rows created once; all five responses identical.
* \[ ] Property test (Hypothesis): for any permutation of a valid op set, the final
server state is the same. **This test is worth a paragraph in Chapter 4.**

Write these as automated tests, not manual checks. They become E4.

\---

## 6\. Phase 2 — Domain, state machine, RBAC (Week 3)

Now throw away `toy` and keep the engine.

### 6.1 Schema

```sql
CREATE TYPE referral\_state AS ENUM
  ('CREATED','IN\_TRANSIT','ARRIVED','TREATED','BACK\_REFERRED','CLOSED','ESCALATED','LOST');
CREATE TYPE user\_role AS ENUM ('ASHA','ANM','MO','SUPERVISOR');

CREATE TABLE org\_unit(id UUID PRIMARY KEY, name TEXT, type TEXT, parent\_id UUID REFERENCES org\_unit(id));
CREATE TABLE app\_user(id UUID PRIMARY KEY, name TEXT, role user\_role,
                      org\_unit\_id UUID REFERENCES org\_unit(id), password\_hash TEXT);

CREATE TABLE patient(id UUID PRIMARY KEY, name TEXT, normalized\_name TEXT,
                     phone TEXT, village\_org\_id UUID, created\_by UUID, created\_at TIMESTAMPTZ);
CREATE TABLE patient\_alias(id UUID PRIMARY KEY, patient\_id UUID, raw\_name TEXT,
                           match\_method TEXT, match\_score NUMERIC, confirmed\_by UUID);

CREATE TABLE sla\_profile(id UUID PRIMARY KEY, name TEXT, state referral\_state,
                         max\_hours INT, escalate\_to\_role user\_role, version INT, active BOOL);

CREATE TABLE referral(
  id UUID PRIMARY KEY, patient\_id UUID, origin\_user\_id UUID, origin\_org\_id UUID,
  target\_org\_id UUID, reason TEXT, priority TEXT,
  current\_state referral\_state NOT NULL,        -- derived cache (I3)
  state\_entered\_at TIMESTAMPTZ NOT NULL,
  sla\_profile\_id UUID, created\_device\_time TIMESTAMPTZ, created\_server\_time TIMESTAMPTZ);

CREATE TABLE referral\_event(
  seq BIGSERIAL PRIMARY KEY, id UUID, referral\_id UUID NOT NULL,
  from\_state referral\_state, to\_state referral\_state NOT NULL,
  actor\_user\_id UUID, actor\_role user\_role,
  device\_time TIMESTAMPTZ, server\_time TIMESTAMPTZ DEFAULT now(),
  lamport BIGINT, op\_id UUID UNIQUE, device\_id TEXT, payload JSONB);

CREATE TABLE escalation(
  id UUID PRIMARY KEY, referral\_id UUID, breached\_state referral\_state,
  triggered\_at TIMESTAMPTZ, escalated\_to\_user\_id UUID,
  sla\_profile\_version INT, resolved\_at TIMESTAMPTZ);

CREATE TABLE sync\_conflict(
  id UUID PRIMARY KEY, entity\_type TEXT, entity\_id UUID, field TEXT,
  winning\_op\_id UUID, losing\_op\_id UUID, detected\_at TIMESTAMPTZ,
  resolved\_by UUID, resolved\_at TIMESTAMPTZ);

-- I5: double escalation is structurally impossible, not merely avoided
CREATE UNIQUE INDEX uq\_escalation\_open ON escalation(referral\_id, breached\_state)
  WHERE resolved\_at IS NULL;

CREATE INDEX idx\_referral\_open ON referral(current\_state, state\_entered\_at)
  WHERE current\_state NOT IN ('CLOSED','LOST');
CREATE INDEX idx\_event\_referral ON referral\_event(referral\_id, seq);
CREATE INDEX idx\_patient\_norm ON patient(village\_org\_id, normalized\_name);
```

Alembic migration from the start. Never edit a shipped migration; add a new one.

### 6.2 State machine as pure functions

Keep this module free of database and framework imports. It is the piece you will
unit-test hardest and quote in Chapter 3.

```python
# app/domain/states.py
TRANSITIONS: dict\[State, set\[State]] = {
    State.CREATED:       {State.IN\_TRANSIT, State.ESCALATED},
    State.IN\_TRANSIT:    {State.ARRIVED, State.ESCALATED},
    State.ARRIVED:       {State.TREATED, State.ESCALATED},
    State.TREATED:       {State.BACK\_REFERRED, State.ESCALATED},
    State.BACK\_REFERRED: {State.CLOSED, State.ESCALATED},
    State.ESCALATED:     {State.IN\_TRANSIT, State.ARRIVED, State.TREATED,
                          State.BACK\_REFERRED, State.CLOSED, State.LOST},
    State.CLOSED:        set(),
    State.LOST:          set(),
}

GUARDS: dict\[State, set\[Role]] = {
    State.CREATED:       {Role.ASHA, Role.ANM},
    State.IN\_TRANSIT:    {Role.ASHA, Role.ANM},
    State.ARRIVED:       {Role.MO},
    State.TREATED:       {Role.MO},
    State.BACK\_REFERRED: {Role.MO},
    State.CLOSED:        {Role.ASHA},
    State.ESCALATED:     {Role.SYSTEM},
    State.LOST:          {Role.SYSTEM},
}

def is\_legal(frm: State, to: State) -> bool: return to in TRANSITIONS\[frm]
def may(role: Role, to: State) -> bool:      return role in GUARDS\[to]
```

`ESCALATED` returning to the ordinary path is what makes escalation a supervisory
signal rather than a parallel workflow. Preserve `breached\_state` on the
escalation row so the referral resumes rather than restarts.

### 6.3 Conflict rules — the decision table

When an op arrives, compare its `from\_state` to the referral's `current\_state`:

|Condition|Outcome|Log?|`current\_state` changes?|
|-|-|-|-|
|Role not permitted for `to\_state`|`rejected`|no|no|
|Transition not in `TRANSITIONS`|`rejected`|no|no|
|`from\_state == current\_state`|`accepted`|yes|yes|
|`from\_state != current\_state`, incoming `lamport` **<** current|`accepted\_stale` — a late event|yes|no|
|`from\_state != current\_state`, incoming `lamport` **>** current|`conflict`|yes|no, and a `sync\_conflict` row is written|

The middle rows are the interesting ones and the reason your log is append-only.
A late event is still history and still belongs in the record even though it
cannot move the state. A genuine conflict is two devices that each acted
reasonably on stale information; the system records both, changes nothing, and
asks a human. That is the behaviour you defend in Chapter 3.

### 6.4 Auth and scoping

JWT with argon2id. Claims: `sub`, `role`, `org\_unit\_id`. Visibility is by org
subtree, via a recursive CTE:

```sql
WITH RECURSIVE subtree AS (
  SELECT id FROM org\_unit WHERE id = :root
  UNION ALL SELECT o.id FROM org\_unit o JOIN subtree s ON o.parent\_id = s.id)
SELECT ... WHERE origin\_org\_id IN (SELECT id FROM subtree)
```

Apply the same scoping to `/sync/pull`. A pull that ignores scope is a data leak,
and it is easy to miss because the UI looks correct.

### 6.5 Exit criteria

* \[ ] A referral traverses CREATED → … → CLOSED through the API.
* \[ ] Every guard violation returns `rejected` and writes no event.
* \[ ] All five conflict-table rows have a passing test.
* \[ ] An ASHA in village A cannot see, via API or pull, a referral from village B.

\---

## 7\. Phase 3 — Hardening and Review-I (Week 4)

This is a writing week; treat the spare capacity as buffer, not as new features.

Use it for: replaying the full event log to verify I3 (`current\_state` recomputed
from events matches the stored cache, for every referral); adding the timeline
endpoint; and rehearsing the demo. **Review-I must be a live demo, not slides.**
Rehearse it end to end at least twice, on a cold `docker compose up`.

\---

## 8\. Phase 4 — Offline client (Week 5)

### 8.1 Dexie schema

```ts
db.version(1).stores({
  outbox:         'op\_id, status, lamport, entity\_id, next\_retry\_at',
  referral\_cache: 'id, patient\_id, current\_state, state\_entered\_at',
  patient\_cache:  'id, village\_org\_id, normalized\_name',
  sync\_meta:      'key'   // server\_cursor, lamport, device\_id, last\_sync\_at
});
```

`device\_id` is generated once on first run and persisted. It identifies the
device across reinstalls of the tab, and it is what makes two-device conflict
tests meaningful.

### 8.2 Lamport clock on the client

```ts
export async function nextLamport(): Promise<number> {
  const row = await db.sync\_meta.get('lamport');
  const next = (row?.value ?? 0) + 1;
  await db.sync\_meta.put({ key: 'lamport', value: next });
  return next;
}
// on pull: lamport = max(local, max(pulled.lamport))
```

### 8.3 Optimistic UI

Local mutation writes to `referral\_cache` and appends to `outbox` in **one Dexie
transaction**. If the transaction fails, neither happens. The UI reads only from
cache, so it is identical online and offline — which is the point.

### 8.4 Service worker

Use `vite-plugin-pwa` in `injectManifest` mode. Precache the app shell. Do **not**
try to cache API responses — your offline data lives in IndexedDB, not in the
HTTP cache, and mixing the two produces stale reads that are miserable to debug.

### 8.5 Exit criteria

* \[ ] DevTools offline → create three referrals → advance one → reload the page →
data still present → go online → all sync, exactly once.
* \[ ] Playwright test doing the above headlessly, in CI.
* \[ ] Airplane-mode demo on a real phone via add-to-home-screen. Record it now
while it is fresh; this clip is your Review-III fallback.

\---

## 9\. Phase 5 — Escalation and live dashboard (Week 6)

### 9.1 Sweep

```python
async def sweep(session, clock: Clock) -> list\[UUID]:
    now = clock.now()
    rows = await session.execute(text("""
        SELECT r.id, r.current\_state, s.escalate\_to\_role, s.version
        FROM referral r
        JOIN sla\_profile s
          ON s.state = r.current\_state AND s.active
        WHERE r.current\_state NOT IN ('CLOSED','LOST','ESCALATED')
          AND r.state\_entered\_at + make\_interval(hours => s.max\_hours) < :now
    """), {"now": now})
    escalated = \[]
    for r in rows:
        res = await session.execute(text("""
            INSERT INTO escalation(id, referral\_id, breached\_state, triggered\_at,
                                   sla\_profile\_version)
            VALUES (gen\_random\_uuid(), :rid, :st, :now, :ver)
            ON CONFLICT DO NOTHING RETURNING id"""), {...})
        if res.first():                    # I5 enforced by the index, not by this check
            await append\_system\_event(session, r.id, r.current\_state, State.ESCALATED, clock)
            escalated.append(r.id)
    return escalated
```

Interval is 5 minutes in production config, **10 seconds in demo config**, so a
breach is visible during a review without waiting. Make it an env var.

### 9.2 SSE

```python
@router.get("/dashboard/stream")
async def stream(user=Depends(current\_user)):
    async def gen():
        async for ev in escalation\_bus.subscribe(scope=user.org\_subtree):
            yield f"data: {json.dumps(ev)}\\n\\n"
    return StreamingResponse(gen(), media\_type="text/event-stream")
```

Client uses `EventSource`, which reconnects automatically. Send a heartbeat
comment every 20 seconds or intermediate proxies will close the connection.

### 9.3 Exit criterion

* \[ ] With demo config, create a referral, wait, and watch it appear on the
supervisor dashboard **without a page refresh**. This is your single most
persuasive twenty seconds of demo — practise it.

\---

## 10\. Phase 6 — Identity resolution (Week 7)

### 10.1 Pipeline

```python
def resolve(raw\_name, phone, village\_id, session) -> Resolution:
    norm = normalize(raw\_name)                      # NFKD, strip diacritics,
                                                    # lowercase, collapse whitespace
    if hit := exact\_match(norm, village\_id): return Resolution(hit, 'exact', 100.0)
    if hit := alias\_lookup(norm, village\_id): return Resolution(hit, 'alias', 100.0)

    candidates = block(village\_id=village\_id, phone\_prefix=phone\[:4])  # ALWAYS block first
    scored = \[(c, max(fuzz.token\_set\_ratio(norm, c.normalized\_name),
                      fuzz.WRatio(norm, c.normalized\_name))) for c in candidates]
    best, score = max(scored, key=lambda t: t\[1], default=(None, 0))

    if score >= AUTO\_ACCEPT:  return Resolution(best, 'fuzzy\_auto', score)
    if score >= REVIEW\_FLOOR: return Resolution(best, 'review\_queue', score)
    return Resolution(None, 'new\_patient', score)
```

Defaults: `AUTO\_ACCEPT = 92`, `REVIEW\_FLOOR = 80`. E3 sweeps both.

**Never fuzzy-match unblocked.** Unscoped matching across the whole patient table
produces silent cross-village merges — two different people become one, and the
error is invisible until someone is treated on the wrong history.

### 10.2 The gold set is free — but only if you build the generator right

This is the key insight of the whole evaluation. Because the synthetic generator
*creates* the name variants, it knows ground truth. It emits
`ground\_truth\_identity.json` mapping every generated record to its true person.
Precision, recall and F1 are then computed exactly, not estimated.

Also measure **blocking recall** — the fraction of true matches that survive
blocking at all. Blocking caps your achievable recall, and a threshold sweep that
ignores this reports a ceiling it cannot explain. Reporting it is the difference
between an evaluation and a table of numbers.

### 10.3 Exit criteria

* \[ ] Threshold sweep over {80, 85, 88, 90, 92, 95} produces precision/recall/F1.
* \[ ] Naive exact-match baseline reported alongside the full pipeline.
* \[ ] Failure taxonomy: for each error, which stage let it through.
* \[ ] Review queue visible and actionable in the ANM/supervisor UI.

\---

## 11\. Phase 7 — Generator and integration tests (Week 8)

### 11.1 Generator contract

```
python -m generator.cli --seed 42 --config configs/e1\_dropout25.yaml --out data/run\_001/
```

Emits: `patients.csv`, `referrals.csv`, `events.csv`,
`ground\_truth\_identity.json`, and `config.resolved.yaml` (the fully expanded
config including the seed). **Every run is reproducible from that directory
alone** — this is I7, and it is what makes your Chapter 4 defensible.

Parameters: `n\_patients`, `n\_ashas`, `n\_facilities`, per-stage `dropout\_rate`,
`name\_variant\_rate`, `duplicate\_rate`, `connectivity\_profile`.

Name variants must be realistic Indian transliterations —
Lakshmi/Lakshmy/Laxmi, Krishnan/Krishnnan, Muhammad/Mohammed/Mohamad. Build the
variant rules by hand from a small table; do not use random character noise,
which produces errors no human would make and makes your fuzzy matcher look
better than it is.

### 11.2 Test layers

|Layer|Tool|Covers|
|-|-|-|
|Unit|pytest|State machine, guards, normalisation, scoring, lamport|
|Property|Hypothesis|Op-permutation invariance; idempotency under arbitrary retry|
|Integration|pytest + real Postgres|Push/pull, RBAC scoping, escalation sweep|
|E2E|Playwright|Offline create, reconnect sync, two-device conflict|
|Fault|scripted|§13|

\---

## 12\. Instrumentation — build this in from Phase 1

Not a phase. A habit. Without it, Week 9 fails.

* **Structured JSON logging** from day one, with `op\_id`, `referral\_id`,
`device\_id`, `run\_id` as fields, not embedded in message strings.
* **Timing middleware** on every request, writing `endpoint`, `method`,
`status`, `duration\_ms` to a table. E5 is then a query, not a re-run.
* **`run\_id` on every experimental row.** Add a nullable `run\_id` column to
`referral` and `referral\_event`. Set it from an env var. This is how you run
eighteen E1 cells without eighteen databases.
* **Screenshots as you go.** Every time a screen first works, screenshot it into
`docs/screenshots/`. Chapter 4 needs them and recreating UI states in week 10
is miserable.
* **Commit the `results/` directory.** Every experiment output, versioned.

\---

## 13\. Phase 8 — Experiments (Week 9)

By now the code is frozen except for bug fixes. This week is execution.

### 13.1 Harness

```
python -m experiments.runner --exp E1 --out results/e1/
```

Per cell: fresh database (`docker compose down -v \&\& up`), load cohort, install
`SimulatedClock`, run the timeline, advance the clock in steps, invoke the sweep
at each step, collect metrics, write one row to `results/e1/raw.csv`.
`analysis.py` turns raw CSVs into the tables and figures you paste into Chapter 4.

### 13.2 Experiment specifications

|ID|Design|Reported|
|-|-|-|
|E1|escalation {on, off} × dropout {10, 25, 40}%|Loop closure rate. **Headline.**|
|E2|SLA window {24, 48, 72, 120}h|Closure rate vs escalation volume — the alert-fatigue frontier|
|E3|threshold {80, 85, 88, 90, 92, 95}|Precision, recall, F1, auto-resolution rate, blocking recall, failure taxonomy|
|E4|fault injection, see below|Zero lost ops, zero duplicate applications, all conflicts surfaced|
|E5|k6 load, before/after indexing|p50/p95 per endpoint, `EXPLAIN ANALYZE` for the open-loops query|
|E6|full-cohort run|Fraction of cases the system cannot resolve or close|

Run every cell at **three seeds** and report the mean. A single-seed result on
synthetic data is not a result, and a panel member who has run a simulation will
ask.

### 13.3 E4 fault injection — make it deterministic

Do not rely on manually pulling a network cable. Build fault hooks into the
client, driven by an env var, so the tests are scriptable and repeatable:

|Fault|Mechanism|Assertion|
|-|-|-|
|Partition mid-sync|Playwright `context.setOffline(true)` during flush|Ops remain `inflight`; land exactly once on reconnect|
|API killed mid-push|`docker kill api` after request receipt|Client retries; receipt ledger prevents double-apply|
|Client killed mid-push|`FAULT=exit\_after\_send`|Ops resume from `inflight` on reload; exactly once|
|Duplicate replay|Re-POST the identical batch ×5|Identical responses; one row|
|Concurrent offline edit|Two Playwright contexts, both offline, same referral|One `accepted`, one `conflict`; both events in log; `sync\_conflict` row present|

\---

## 14\. Phase 9 — Deployment, demo, report (Week 10)

**Primary demo path is local `docker compose up`.** Free-tier hosts cold-start,
and a spinner during a graded review is a bad minute. Deployed URL is secondary;
the recorded two-minute clip is your third fallback. Have all three.

`make demo` should: reset the database, seed a small cohort, open the dashboard,
and print the scripted scenario steps to the terminal so you do not have to
remember them while being watched.

Appendix A is code — export the FastAPI-generated OpenAPI spec as part of it, it
is free and it looks thorough. Confirm with your guide whether Appendix B (paper
submission) is mandatory for this course before spending time on it.

\---

## 15\. Failure modes, ranked by likelihood

1. **Sync overruns week 2.** The dominant risk. Mitigation is already in the
plan: toy model, one field, no domain. If it is not done by Aug 16, cut the
two-device conflict case from scope, keep single-device durability, and tell
your guide that week — not in September.
2. **Clock not injectable.** You discover in week 9 that experiments need weeks
of wall time. §3.1 exists to prevent this. Do it in week 1.
3. **Pull cursor gaps.** §3.2. Intermittent, passes tests, corrupts results.
4. **Unblocked fuzzy matching.** Silent cross-village merges that inflate your
E3 numbers and are hard to detect after the fact.
5. **Receipt written outside the effect transaction.** Breaks I1 and produces
duplicates only under crash conditions — that is, only in E4, which is the one
experiment where it is fatal.
6. **No instrumentation until week 9.** Then E5 has no data and you re-run
everything you have already run.
7. **Scope creep into a native app or CRDTs.** Both are already excluded with
reasons in the pitch. Revisiting a settled exclusion in week 6 costs a week.

\---

## 16\. Weekly discipline

Every week, without exception: meet the guide, write the MoM the same day into
`docs/mom/`, and submit the bundle monthly. Commit daily even when the work is
ugly — the commit history is evidence of individual work, which matters for an
individual project.

Every Friday, ask one question: *is this week's exit criterion objectively true?*
If not, that is the first sentence of Monday's conversation with your guide.

