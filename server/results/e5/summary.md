# E5 — k6 load test, before/after `idx_referral_open`

**Setup:** fresh dev database, migrated + seeded, one P7.1-scale cohort
loaded (seed 42: 220 patients, 621 referrals, 2039 events). k6 (10 VUs,
40s) against `cohort42_mo_1` (an MO whose subtree covers ~300 of the 621
referrals — a realistic "open loops" scope, not a handful of rows) for
reads, `cohort42_asha_1` for one `create_referral` push per iteration.
378 iterations / 1514 HTTP requests per run.

**`idx_referral_open`** (`current_state, state_entered_at` partial index,
`WHERE current_state NOT IN ('CLOSED','LOST')`) already ships in the
schema since migration `0003` — this is not a new index P8.3 adds.
"Before"/"after" here means the index temporarily dropped, then recreated,
on a scratch load rather than a permanent schema change.

## EXPLAIN ANALYZE, dashboard's own open-loops query

`explain_open_loops_before.txt` (index dropped) and
`explain_open_loops_after.txt` (index present) are **the same query plan**
— `Seq Scan on referral (cost=0.00..22.23 rows=623)` either way. At 623
rows, Postgres's planner correctly decides a sequential scan beats an
index lookup; `idx_referral_open` is not being used by this query at this
table size, with or without it existing.

## Per-endpoint p50/p95, from `request_timing` (not k6's own summary — plan §12's own design, "E5 is then a query, not a re-run")

| endpoint | method | n (before) | p50 before (ms) | p95 before (ms) | n (after) | p50 after (ms) | p95 after (ms) |
|---|---|---|---|---|---|---|---|
| /dashboard | GET | 376 | 5.14 | 45.72 | 378 | 4.78 | 26.10 |
| /referrals | GET | 376 | 4.51 | 42.34 | 378 | 4.17 | 25.85 |
| /sync/pull | GET | 376 | 12.88 | 42.98 | 378 | 10.66 | 36.79 |
| /sync/push | POST | 376 | 10.30 | 49.90 | 378 | 10.43 | 56.82 |
| /auth/login | POST | 2 | 61.44 | 66.40 | 2 | 65.83 | 69.72 |

(Full table: `table_e5_latency.csv`. `k6_before_summary.json`/
`k6_after_summary.json` are k6's own cross-check summaries — same
ballpark, `http_req_duration` p95 67.46ms before vs 61.9ms after, overall
across all four endpoint types combined.)

## The honest finding

**No measurable effect from `idx_referral_open` at this data scale.** The
query plan is identical with or without the index; the p50s move by
under a millisecond either way; the p95s move a few milliseconds in
*both* directions depending on the endpoint (`/dashboard`/`/referrals`
look faster indexed, `/sync/push` looks very slightly slower indexed) —
consistent with ordinary run-to-run noise on a ~380-request sample, not a
causal effect, and consistent with the EXPLAIN plan showing the planner
never touches the index either way. A partial index on a ~600-row table
is exactly the case where Postgres's own cost model correctly prefers a
sequential scan: the whole table fits in a handful of pages, and reading
it in one pass beats random-access index lookups. `idx_referral_open`
would very likely start mattering once `referral` reaches tens or
hundreds of thousands of rows — a scale this project's own generator/demo
data never reaches (D31, P7.1) — but that is a claim about *where the
index would matter*, not a measurement this session made. Reported as-is,
the same discipline E2's flat frontier (P8.2) was reported with, rather
than picking a friendlier query or a smaller subtree to manufacture a
difference.
