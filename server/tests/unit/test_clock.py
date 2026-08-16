from datetime import UTC, datetime

from app.clock import RealClock, SimulatedClock, build_clock
from app.config import Settings


def test_simulated_clock_advance():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    clock = SimulatedClock(start)
    assert clock.now() == start

    clock.advance(hours=24)
    assert clock.now() == datetime(2026, 1, 2, tzinfo=UTC)

    clock.advance(days=1, hours=2)
    assert clock.now() == datetime(2026, 1, 3, 2, tzinfo=UTC)


def test_simulated_clock_does_not_move_on_its_own():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    clock = SimulatedClock(start)
    first = clock.now()
    second = clock.now()
    assert first == second == start


def test_build_clock_real_mode():
    settings = Settings(clock_mode="real")
    clock = build_clock(settings)
    assert isinstance(clock, RealClock)


def test_build_clock_simulated_mode_uses_sim_start():
    settings = Settings(clock_mode="simulated", sim_start="2026-06-01T00:00:00+00:00")
    clock = build_clock(settings)
    assert isinstance(clock, SimulatedClock)
    assert clock.now() == datetime(2026, 6, 1, tzinfo=UTC)


def test_build_clock_simulated_mode_without_sim_start_falls_back_to_real_time():
    settings = Settings(clock_mode="simulated", sim_start=None)
    before = datetime.now(UTC)
    clock = build_clock(settings)
    after = datetime.now(UTC)
    assert before <= clock.now() <= after
