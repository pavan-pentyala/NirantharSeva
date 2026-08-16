"""Scheduler entrypoint. Runs as its own Compose service, separate from the
API, so it can be killed independently — plan §2.3 and experiment E4 depend
on that separation.

Phase 0: proves the container starts and takes a Clock. The escalation sweep
itself is Phase 5 (plan §9).
"""

import time

from app.clock import get_clock
from app.instrumentation.logging import configure_logging, get_logger

configure_logging()
logger = get_logger("scheduler")


def main() -> None:
    clock = get_clock()
    logger.info(f"scheduler started, clock_mode={clock.now().isoformat()}")
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
