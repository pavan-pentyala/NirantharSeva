"""Full-database replay verification of I3. See docs/decisions/ADR-007.md.

I3 says a referral's current_state is always derivable by replaying its
event log. The property test in tests/property/test_referral_replay.py
samples random walks over referrals it created itself; this is the only
place that checks I3 as stated — for every referral in the database —
rather than for a sampled subset.

Run as `python -m app.verify_replay` (docker compose run --rm api python
-m app.verify_replay). Top-level in app/ with an if __name__ == "__main__"
block, mirroring app/seed.py — the only import path that works on a dev
laptop, in CI's server job, and in CI's e2e job.

verify_all() returns a report and neither prints nor exits — the
__main__ block below does both, so a pytest integration test can call the
identical function without spawning a subprocess. app/seed.py already has
to satisfy the same split, serving both the CLI and the test fixtures.

The scan runs inside a REPEATABLE READ transaction, so a cache updated
mid-scan cannot produce a phantom mismatch, and it deliberately does not
take the advisory lock app/db.py's acquire_seq_lock takes before an event
append (docs/decisions/ADR-002.md) — that lock serialises appends; a
read-only full scan holding it would stall every concurrent push behind
itself.
"""

import asyncio
import itertools
import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import async_session_factory
from app.domain.states import State, replay_state
from app.sync.event_log import triple

# One bulk query, not N+1. app/sync/event_log.py's fetch_triples() is a
# different access pattern — one referral at a time, hitting
# idx_event_referral. Building this scan out of it in a loop is two round
# trips against the current fixture and thousands against Phase 7's
# generated cohort, which is what Phase 8 runs this against.
_SCAN_QUERY = """
SELECT r.id AS referral_id, r.current_state,
       e.from_state, e.to_state, e.lamport, e.op_id
FROM referral r
LEFT JOIN referral_event e ON e.referral_id = r.id
ORDER BY r.id, e.seq
"""


@dataclass(frozen=True)
class Mismatch:
    referral_id: uuid.UUID
    cached_state: str
    replayed_state: str | None
    reason: str  # "zero_events" | "cache_diverged_from_log"


@dataclass(frozen=True)
class VerifyReport:
    referrals_checked: int
    events_checked: int
    mismatches: list[Mismatch]

    @property
    def ok(self) -> bool:
        return not self.mismatches


async def verify_all(
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> VerifyReport:
    session_factory = session_factory or async_session_factory
    mismatches: list[Mismatch] = []
    referrals_checked = 0
    events_checked = 0

    async with session_factory() as session, session.begin():
        # Must be the first statement in the transaction (Postgres
        # requirement) — see the module docstring for why REPEATABLE READ
        # and not the advisory lock.
        await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
        result = await session.execute(text(_SCAN_QUERY))
        rows = result.all()

        # ORDER BY r.id, e.seq in the query above is what makes this
        # groupby legal — groupby only groups consecutive runs.
        for referral_id, group in itertools.groupby(rows, key=lambda row: row.referral_id):
            referrals_checked += 1
            group_rows = list(group)
            cached_state = State(group_rows[0].current_state)
            # LEFT JOIN produces one all-NULL event row for a referral
            # with no events — op_id is never NULL for a real event.
            events = [row for row in group_rows if row.op_id is not None]
            events_checked += len(events)

            if not events:
                # A cache asserting a state the log cannot derive is
                # precisely what I3 forbids — reported, not skipped.
                mismatches.append(
                    Mismatch(
                        referral_id=referral_id,
                        cached_state=cached_state.value,
                        replayed_state=None,
                        reason="zero_events",
                    )
                )
                continue

            replayed_state, _, _ = replay_state([triple(row) for row in events])
            if replayed_state != cached_state:
                mismatches.append(
                    Mismatch(
                        referral_id=referral_id,
                        cached_state=cached_state.value,
                        replayed_state=replayed_state.value if replayed_state else None,
                        reason="cache_diverged_from_log",
                    )
                )

    return VerifyReport(
        referrals_checked=referrals_checked,
        events_checked=events_checked,
        mismatches=mismatches,
    )


def _print_report(report: VerifyReport) -> None:
    print(f"checked {report.referrals_checked} referrals, {report.events_checked} events")
    if report.ok:
        print("I3 holds: every current_state matches its replayed event log")
        return
    print(f"I3 VIOLATED: {len(report.mismatches)} referral(s) diverged")
    for m in report.mismatches:
        print(
            f"  referral {m.referral_id}: cached={m.cached_state} "
            f"replayed={m.replayed_state} reason={m.reason}"
        )


if __name__ == "__main__":
    _report = asyncio.run(verify_all())
    _print_report(_report)
    raise SystemExit(0 if _report.ok else 1)
