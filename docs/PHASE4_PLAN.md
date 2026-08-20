# Phase 4 plan — offline client

**Status:** Planned, not started. Written 2026-08-19 (Opus, plan-only session
— no code, no migration, no client file, no dependency installed this
session).
**Source of truth for *what*:** `docs/IMPLEMENTATION_PLAN.md` §8. Forty lines,
one Dexie schema, one Lamport snippet, three exit criteria — this file
supplies the rest, the way `docs/PHASE3_PLAN.md` did for §7.
**Source of truth for *how you work*:** `docs/HANDOFF_CLAUDE_CODE.md`.
**Read before starting P4.1:** `docs/PHASE2_OBSERVATIONS.md`, ADR-006 (actor
identity), ADR-008 (the replay fold), ADR-009, ADR-010.
**Design bundle:** `docs/design_handoff_ui_screens/`, tracked in git. Governs
appearance, never architecture (handoff §8).

---

## Context

Plan §8 describes a Dexie schema, a Lamport helper, and says optimistic UI
writes cache and outbox "in one Dexie transaction." It does not name a
screen, a route, or how the client learns a patient's name. It was written
before the design bundle existed.

Reading the design bundle against the server as it stands today
(`server/app/sync/push.py`, `server/app/sync/pull.py`,
`server/app/schemas/referral.py`) found three places where the design implies
behaviour the current API cannot support — handoff §8's exact case for
stopping and naming the gap rather than building around it silently. All
three are now decided (D13–D15 below, ADR-009, ADR-010).

Phase 4 is also large enough that one session risks ending with the repo
half-working, the same reasoning that split Phase 2 into P2.1/P2.2. It splits
into three sub-phases (D16), each independently committed and testable.

---

## Decisions taken with the user

Continuing D1–D12 (`docs/PHASE2_PLAN.md`, `docs/PHASE3_PLAN.md`).

### D13 — `create_referral` carries the patient. See **ADR-009**.

The payload gains `patient_name`, `age`, `sex`, `phone`. The server resolves
an exact match on `(normalized_name, village_org_id)` or inserts a new
`patient` row, in the same transaction as the referral and its CREATED event.
Migration `0005` adds `patient.age`/`patient.sex`. Not fuzzy — that stays
Phase 6's, and this decision names the exact call site
(`_apply_create_referral`) Phase 6 will replace.

### D14 — the pull payload carries a referral snapshot. See **ADR-010**.

The referral branch of `/sync/pull` gains `patient_name`, `age`, `sex`,
`reason`, `priority`, `target_org_name` in `payload`. One stream, one cursor —
not a second bootstrap endpoint. `applyPulledEvents` on the client folds
`advanced` with the same left-to-right rule the server's `replay_steps` uses,
and only an advancing step writes `referral_cache`.

### D15 — `app_user.display_name`, login stays username + password

Migration `0005` also adds `app_user.display_name`; seed users get real names
("Sunita Kumari" for `asha_a`, and so on — kept as the login handle, since
handle and display name only needed separating for what a screen *shows*, not
for what a user *types*). Screen 7's phone-number and PIN fields are
relabelled to username and password in the build; the role grid renders but
is **display-only** — the authenticated role always comes from the server
(ADR-006), never chosen by the client. This is a stated departure from the
design bundle, not a silent one, per handoff §8's rule that the design
governs appearance but the architecture wins where the two disagree — here,
"never trust the client's claimed role" is architecture.

No ADR for D15: a display-name column and a relabelled form field are not an
architectural decision, the same reasoning `docs/PHASE3_PLAN.md`'s D9 used.
Flagged here rather than left implicit.

### D16 — Phase 4 splits into P4.1 / P4.2 / P4.3 (handoff §1, R5)

Each sub-phase ends committed, CI-green, and independently verifiable. No
sub-phase starts without the user's go-ahead, same as any phase (R1).

### Screen scope for P4.2 — decided by Claude Code, stated so it can be overruled

P4.2 builds Screens 1, 2, 3, 5, 7 (ASHA list, ASHA create, referral detail,
MO incoming, login). Screen 4 (supervisor dashboard) is Phase 5's — its whole
point is a breach appearing without a page refresh, which needs Phase 5's SSE
stream and doesn't exist yet. Screen 6 (ANM identity review) is Phase 6's — it
renders a match the identity-resolution pipeline doesn't exist to produce.
Both get a routed placeholder ("coming in Phase 5/6") in P4.2 so navigation is
complete and nothing 404s from inside the app shell.

---

## Two dependencies not yet named in the plan — need your yes before P4.2

`docs/IMPLEMENTATION_PLAN.md` names Dexie, React, Vite, `vite-plugin-pwa`. It
does not name a router or a live-query hook, and the handoff requires asking
before adding anything not already named (§2).

- **`react-router-dom`** — five screens plus two placeholders need routes.
  The alternative is hand-rolled state-based view switching, which is what
  `App.tsx` does today for exactly one view; five views is past where that
  stays simple.
- **`dexie-react-hooks`** (`useLiveQuery`) — `ToyPage.tsx` polls Dexie every
  500ms today, acceptable for one harness value, not for five screens each
  reading multiple tables. `useLiveQuery` subscribes instead of polling; it's
  Dexie's own companion package, same maintainer, same major version line as
  the `dexie` dependency already in `package.json`.

Both are asked again, explicitly, at the start of the P4.2 session — not
assumed from this plan alone.

---

## Build order

### P4.1 — server contract and client data layer. No new screens.

| # | Item | Notes |
|---|---|---|
| 1 | Migration `0005` | `patient.age`, `patient.sex` (nullable), `app_user.display_name` (nullable, backfilled by seed). New revision on `0004`; `0001`–`0004` untouched. |
| 2 | Patient resolution in `push.py` | Extract as its own function so ADR-009's Phase 6 seam is one call site, not scattered logic. |
| 3 | Pull payload widened | `pull.py`'s referral branch joins `patient` and `org_unit`, inside the subquery, before `LIMIT` (ADR-010). |
| 4 | `app/seed.py` | Real `display_name`s, patient `age`/`sex` for the four seeded patients. |
| 5 | Dexie `version(2)` | `referral_cache`, `patient_cache` added; `outbox` generalised off the toy-only shape it has today; `sync_meta` unchanged; `toy_cache` stays until P4.3. |
| 6 | `engine.ts` | `createOp` → `createReferral` + `transitionReferral`, each writing cache + outbox in one Dexie transaction (plan §8.3). `applyPulledEvents` gains the referral branch (D14). |
| 7 | Tests | Server: patient-resolution dedup test (ADR-009), widened-payload integration test (ADR-010). Client: the Dexie transaction is atomic (partial write on induced failure leaves neither cache nor outbox changed); `applyPulledEvents` only writes `referral_cache` on `advanced=true`, using a fixture with one conflict pair. |

**P4.1 exit criteria**
- [ ] `alembic heads` is `0005`; `0001`–`0004` are byte-identical to Phase 3's commit.
- [ ] `python -m app.verify_replay` still clean after seeding and one manual create+transition through P4.1's new push path.
- [ ] Two referrals created with identical `(patient_name, village)` via `create_referral` produce one `patient` row; two referrals with the same name in different villages produce two.
- [ ] A pulled `create_referral` event's payload contains `patient_name`, `age`, `sex`, `reason`, `priority`, `target_org_name`, all correct.
- [ ] `ruff check`, `ruff format --check`, `tsc --noEmit`, full server + client test suites, all green in CI.
- [ ] No file changed under `client/src/pages/`, `client/src/App.tsx` — P4.1 is data-layer only.

### P4.2 — the five screens

| # | Item | Notes |
|---|---|---|
| 1 | Router + live query | `react-router-dom`, `dexie-react-hooks` — pending your answer above. |
| 2 | Design tokens | One CSS file of custom properties from `Design System.dc.html` §2–§5: colour, type scale, spacing/radius, the three-shape state rule. |
| 3 | State → label lookup | One table, one place, matching the README's mapping exactly — the only place the event-log state vocabulary and the UI vocabulary meet (brief §5, README "State → label mapping"). |
| 4 | Screens 1, 2, 3, 5, 7 | Recreated in React/TS against the bundle, reading Dexie only. Screens 4, 6 as routed placeholders. |
| 5 | Sync band | Amber/grey band per brief §6, banned-words list enforced (sync, pending ops, conflict, operation, queue, offline mode, retry, payload). |
| 6 | Demo marker | "Demonstration system — synthetic data only" on every screen (brief §8). |
| 7 | Screenshots | Into `docs/screenshots/` the first time each screen renders for real (R9). |

**P4.2 exit criteria**
- [ ] All five screens navigable from a fresh login, reading only from Dexie (verify by killing network mid-session — no screen blanks or spinners).
- [ ] Screen 1's three states (synced / offline-with-pending / empty) all reachable and visually distinct without a colour-only cue (three-shape rule).
- [ ] Screen 2 creates a referral for a brand-new patient name, offline, and it appears correctly in Screen 1 and Screen 3 after reconnect.
- [ ] No banned word appears in any rendered screen's copy — grep the built output.
- [ ] Screens 4 and 6 render a placeholder, not a 404 or a blank route.
- [ ] `tsc --noEmit` and `npm run build` clean in CI.

### P4.3 — PWA, toy drop, fault tests

| # | Item | Notes |
|---|---|---|
| 1 | `vite-plugin-pwa`, `injectManifest` mode | App shell precached. No API response caching (plan §8.4) — offline data lives in IndexedDB only. |
| 2 | Migration `0006` | Drops `toy`, `toy_event`. Removes `ToyPage.tsx`, `toy_cache`, the toy branches of `push.py`/`pull.py`, and D7's now-obsolete unscoped-toy-branch regression test — ADR-005's D7 exception is time-boxed to end exactly here. |
| 3 | Fault tests ported | `offline-sync.spec.ts`, `client-kill-resume.spec.ts` moved from the toy harness onto the real referral screens. Must stay green through the port — they are E4's evidence (D1), not disposable scaffolding. |
| 4 | Real-phone recording | Airplane-mode create-and-sync via add-to-home-screen (plan §8.5). Becomes the Review-III fallback clip. |

**P4.3 exit criteria**
- [ ] DevTools offline → create three referrals → advance one → reload → data present → online → all sync exactly once (plan §8.5, criterion 1).
- [ ] Both ported Playwright fault tests green in CI, against real referral screens, not the toy model.
- [ ] `alembic heads` is `0006`; `grep -rn toy_ server/app client/src` returns nothing.
- [ ] A recorded real-phone clip exists (not committed to git — large binary; note its location in `PROGRESS.md`).
- [ ] Full cold-start pass (`down -v` → `up --build` → seed → the five screens by hand) works with no manual step not in the plan.

---

## Traps for this phase, learned from Phase 2 and Phase 3

- **Grep-based exit criteria match your prose, not just your code** (observed
  twice in Phase 3, `docs/PHASE2_OBSERVATIONS.md` observation 13). P4.3's
  `grep -rn toy_` criterion above will catch a comment that mentions "toy_"
  in passing, not just leftover code — word it carefully when writing it, or
  reword the comment.
- **The offline UI must not special-case the online path** (plan §8.3, brief
  §8). Do not add a loading spinner "just for the online case" anywhere —
  every screen reads Dexie, period, and Dexie is populated by the same fold
  whether the last pull was a second ago or an hour ago.
- **`replay_steps`'s advancement rule must stay defined exactly once under
  `app/`** (ADR-008's own exit criterion, still true). `applyPulledEvents`'s
  client-side fold is a *second* implementation of the same rule, in
  TypeScript, and cannot be checked by the same grep — its test (P4.1 item 7)
  is what stands in for that guarantee on the client side. Do not let it
  drift from `replay_steps`'s definition without updating both.
- **The `patient` table's new nullable columns.** `age`/`sex` are `NULL` for
  every patient created before migration `0005`. Any screen displaying age
  must handle `None`/`null` — do not assume every patient row has one.

---

## Verify Phase 4 yourself, once built

```bash
docker compose down -v && docker compose up -d --build
docker compose run --rm api sh -c "alembic upgrade head && python -m app.seed"
```

`alembic heads` should print `0006` once P4.3 lands (`0005` after P4.1/P4.2
alone). Then, per sub-phase, run that sub-phase's exit-criteria commands
above — each is written to be runnable without guessing at intermediate
state.

---

## Not in this plan

Screen 4 (supervisor live dashboard) and Screen 6 (ANM identity review) —
Phase 5 and Phase 6 respectively, per the screen-scope decision above. The
service worker's push-notification path — not in plan §8 at all, not raised
by the design bundle, not built. Any change to the auth model beyond D15's
column addition — role selection, session length, phone-based login — stays
out per handoff §2's "auth model, roles" line.
