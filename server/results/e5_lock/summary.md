# E5 (lock) — the advisory-lock's write-latency cost

**What this measures.** `docs/IMPLEMENTATION_PLAN.md` §3 promised a
sentence: *"the sequencing lock adds Xms to p95 write latency, accepted in
exchange for a gap-free pull cursor."* P8.3's own E5 measured an index, not
the lock, and its profile (10 VUs, `sleep(1)`, three reads per write)
barely contends — concurrent `/sync/push` calls almost never overlap under
it, so the lock would measure ≈0ms whether or not it does anything. This
measurement uses a different profile, built specifically to contend:
`experiments/k6/lock.js`, **25 write-only VUs and 5 read-only VUs, no
`sleep()`, 30 seconds**, run twice against a scratch database
(`nirantharseva_lock_scratch`, never the dev database) — once with
`acquire_seq_lock` (`app/db.py`, ADR-002) active, once with it temporarily
neutralised by a local edit that was reverted immediately after the run
and confirmed absent from `git status`/`git diff` before anything else
happened. See `server/scripts/measure_lock.sh` / `teardown_lock.sh` for
the exact mechanics.

## The measured sentence

**The sequencing lock adds roughly 70ms to `POST /sync/push`'s median
latency and roughly 94ms at p95, under 25 concurrent writers with no
think time.** Locked: p50 201.7ms, p95 299.4ms (n=3108). Unlocked: p50
130.1ms, p95 205.9ms (n=4390). The same effect shows up in throughput:
the *same* 30-second window completed 3855 total iterations locked vs.
5039 unlocked — about 24% more write throughput with the lock disabled.

## The read-endpoint control

`GET /dashboard` and `GET /referrals` never call `acquire_seq_lock` — they
are the noise control, run in the same two windows, same load. Their p50s
moved by 9–12ms and, notably, in the **opposite direction**: both were
*slower* in the unlocked run, not faster (`/dashboard` 63.9ms locked vs.
75.8ms unlocked; `/referrals` 63.7ms vs. 72.9ms). This is the sentence's
real support: ordinary run-to-run noise on this sample sits in the
single-digit-to-low-teens-of-milliseconds range and doesn't even point
the same way as the write-path effect, while the write path itself moved
5–8× further, and in the direction the lock's own existence predicts.
Full table: `table_e5_lock_latency.csv`. `k6_lock_on_summary.json` /
`k6_lock_off_summary.json` are k6's own cross-check summaries.

## What this does and does not support

**Does:** demonstrates a real, attributable write-latency cost from
`acquire_seq_lock`, at a concurrency level (25 write-only VUs, no
`sleep()`) deliberately chosen to make the lock's own serialisation
visible, unlike P8.3's lighter E5 profile. Confirms the read path is
structurally unaffected — exactly what ADR-002's design predicts, since
only event-appending writers ever take this lock.

**Does not:** claim this number as *the* cost under every possible load —
it is a measurement at one specific, reported concurrency profile, on one
shared development machine (the main dev stack's `db`/`api`/`scheduler`/
`client` containers were left running, idle, alongside this measurement —
not isolated hardware), against a database holding only the small D4
fixture plus what each run itself wrote. A production deployment under
different concurrency, different hardware, or a much larger `referral`
table could see a different absolute number, though the *mechanism* —
one global advisory lock serialising every event append — would produce
the same qualitative trade-off regardless of scale: the lock is what
makes `referral_event.seq` order equal commit order (ADR-002), which is
what keeps `/sync/pull`'s cursor from silently skipping events under
concurrent writers (docs/decisions/ADR-002.md). ~70–94ms of added p50/p95
latency under real write contention is the accepted cost of that
guarantee, not a defect to fix.
