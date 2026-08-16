"""The injectable clock. See docs/decisions/ADR-001.md.

No module in this codebase calls datetime.now(), datetime.utcnow(), or
time.time() directly. Everything that needs the current time takes a Clock.
CI enforces this with a grep (see .github/workflows/ci.yml) because a single
missed call breaks experiment reproducibility silently.
"""

from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Protocol

from app.config import Settings, get_settings


class Clock(Protocol):
    def now(self) -> datetime: ...


class RealClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class SimulatedClock:
    """Virtual time. Experiments and the scheduler advance it explicitly."""

    def __init__(self, start: datetime):
        self._now = start

    def now(self) -> datetime:
        return self._now

    def advance(self, **kwargs) -> None:
        self._now += timedelta(**kwargs)


def build_clock(settings: Settings) -> Clock:
    if settings.clock_mode == "simulated":
        start = (
            datetime.fromisoformat(settings.sim_start) if settings.sim_start else datetime.now(UTC)
        )
        return SimulatedClock(start)
    return RealClock()


@lru_cache
def _cached_clock() -> Clock:
    return build_clock(get_settings())


def get_clock() -> Clock:
    """FastAPI dependency. Cached so the API and any request share one
    SimulatedClock instance — otherwise advancing it in a test would only
    move one throwaway copy."""
    return _cached_clock()
