"""Scheduler entrypoint. Runs as its own Compose service, separate from the
API, so it can be killed independently — plan §2.3 and experiment E4 depend
on that separation.

Calls app/domain/escalation.py's sweep() every SWEEP_INTERVAL_SECONDS (300
production, 10 demo — docs/PHASE5_PLAN.md build order #6). A sweep failure
is logged and never kills the loop; the next tick tries again.

SimulatedClock is per-process and in-memory (docs/PHASE5_PLAN.md "Traps"):
this process and the api container each build their own, so advancing one
does not move the other. A real live demo therefore uses real clock time
plus SLA_SCALE, not simulated time — simulated time is for experiment runs,
where one process drives both.
"""

import asyncio

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.clock import get_clock
from app.config import get_settings
from app.db import async_session_factory
from app.domain.escalation import sweep
from app.instrumentation.logging import configure_logging, get_logger

configure_logging()
logger = get_logger("scheduler")


async def _run_sweep() -> None:
    clock = get_clock()
    try:
        escalated = await sweep(async_session_factory, clock)
        if escalated:
            logger.info(f"sweep escalated {len(escalated)} referral(s)")
    except Exception:
        logger.exception("sweep failed")


async def main() -> None:
    settings = get_settings()
    clock = get_clock()
    logger.info(
        f"scheduler started, clock_mode={settings.clock_mode}, "
        f"now={clock.now().isoformat()}, sweep_interval_seconds={settings.sweep_interval_seconds}"
    )

    scheduler = AsyncIOScheduler()
    scheduler.add_job(_run_sweep, "interval", seconds=settings.sweep_interval_seconds)
    scheduler.start()

    try:
        await asyncio.Event().wait()
    finally:
        scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
