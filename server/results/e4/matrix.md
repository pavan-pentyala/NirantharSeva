# E4 — fault injection matrix

docs/IMPLEMENTATION_PLAN.md §13.3. All five rows already had a real test
built across Phases 1–7 (Phase 8 planning's finding 4, `docs/PHASE8_PLAN.md`
Context section) — this is evidence collection from real runs against the
live stack, not new tests written for P8.3.

Run 2026-08-24, against a freshly reset, migrated, reseeded stack
(`docker compose down -v && up -d --build`, `alembic upgrade head`,
`python -m app.seed`). Raw output: `kill_api_output.txt`,
`idempotency_output.txt`, `playwright_output.txt`.

| Fault | Mechanism | Assertion | Result |
|---|---|---|---|
| Partition mid-sync | Playwright `context.setOffline(true)` during flush | Ops remain `inflight`; land exactly once on reconnect | **PASS** — `offline-sync.spec.ts` ("offline: create three referrals, advance one, reload, data survives, then sync exactly once online"), 17.5s |
| API killed mid-push | `docker kill api` after request receipt | Client retries; receipt ledger prevents double-apply | **PASS** — `server/tests/fault/kill_api.sh`: 20-op batch, API killed 50ms after send, restarted, batch retried; `referral_event` count for the test patient is exactly 20 (not 40), all 20 retry results `accepted` |
| Client killed mid-push | `FAULT=exit_after_send` | Ops resume from `inflight` on reload; exactly once | **PASS** — `client-kill-resume.spec.ts` ("client killed mid-push resumes from inflight and lands exactly once"), 2.0s |
| Duplicate replay ×5 | Re-POST the identical batch ×5 | Identical responses; one row | **PASS** — `tests/integration/test_push_idempotent.py` (`test_same_batch_posted_five_times_creates_row_once`, `test_five_identical_pushes_result_in_one_referral_row`, plus two rejected-op-shape tests) and `tests/property/test_push_idempotency.py` (`test_arbitrary_retry_yields_the_same_state_and_one_event_row_per_op_id` — Hypothesis-generated arbitrary retry/duplication/re-interleaving patterns, not just a fixed ×5); 5/5 passed |
| Concurrent offline edit | Two Playwright contexts, both offline, same referral | One `accepted`, one `conflict`; both events in log; `sync_conflict` row present | **PASS** — `two-device-conflict.spec.ts` ("two devices offline, same referral, same transition -> one accepted, one conflict, nothing lost"), 3.1s |

## Zero lost ops, zero duplicate applications, all conflicts surfaced

The three headline claims §13.2's E4 row makes, each backed by the row
above that actually exercises it:

- **Zero lost ops** — partition (row 1) and client-kill (row 3) both prove
  an op survives a real interruption and reaches the server exactly once,
  not zero times.
- **Zero duplicate applications** — API-kill (row 2) and duplicate-replay
  (row 4) both prove a retried or re-sent op is applied at most once,
  under both a real process death and an arbitrary Hypothesis-generated
  retry pattern.
- **All conflicts surfaced** — concurrent edit (row 5) proves a genuine
  conflict is recorded in `sync_conflict`, not silently dropped or
  silently overwritten (ADR-003).

No new test was written for this sub-phase — every row above cites a test
that already existed before P8.3 started, per Phase 8 planning's own
finding that E4 was already four-fifths built.
