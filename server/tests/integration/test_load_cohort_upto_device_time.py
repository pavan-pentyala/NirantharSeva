"""server/scripts/load_cohort.py's `upto_device_time` parameter, its first
real caller (docs/PHASE8_PLAN.md's own "Traps": P7.1 built the parameter
and tested only `None`). Phase 8's stepped-clock runner calls `load()`
repeatedly with an advancing cutoff, relying on this boundary being exact —
an off-by-one here (`<` vs `<=`) would silently shift which events land in
which experiment step, moving every E1 time-to-detection number without
failing anything.

Uses the same small-cohort generation pattern as
tests/integration/test_load_cohort.py.
"""

from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import text

from app.db import async_session_factory
from generator.cli import run as generate_cohort
from scripts.load_cohort import load

_SMALL_CONFIG = """
n_patients: 6
n_villages: 1
n_ashas: 1
n_facilities: 1
dropout_rate:
  CREATED: 0.0
  IN_TRANSIT: 0.0
  ARRIVED: 0.0
  TREATED: 0.0
  BACK_REFERRED: 0.0
name_variant_rate: 0.0
duplicate_rate: 0.0
connectivity_profile: always_online
"""


def _write_config(tmp_path: Path) -> Path:
    path = tmp_path / "boundary.yaml"
    path.write_text(_SMALL_CONFIG, encoding="utf-8")
    return path


async def _cleanup(user_prefix: str, org_prefix: str) -> None:
    """Same shape as tests/integration/test_load_cohort.py's own cleanup —
    a cohort org/user left behind breaks tests/integration/
    test_org_units.py's exact-set assertion for any test that happens to
    run afterward in the same session (docs/OBSERVATIONS.md 44-46,
    PROGRESS.md's "Known problems")."""
    async with async_session_factory() as session, session.begin():
        referral_subq = (
            "SELECT r.id FROM referral r JOIN app_user u ON u.id = r.origin_user_id "
            "WHERE u.name LIKE :user_prefix"
        )
        params = {"user_prefix": user_prefix, "org_prefix": org_prefix}
        await session.execute(
            text(f"DELETE FROM referral_event WHERE referral_id IN ({referral_subq})"), params
        )
        await session.execute(
            text(f"DELETE FROM sync_conflict WHERE entity_id IN ({referral_subq})"), params
        )
        await session.execute(text(f"DELETE FROM referral WHERE id IN ({referral_subq})"), params)
        await session.execute(
            text(
                "DELETE FROM patient WHERE village_org_id IN "
                "(SELECT id FROM org_unit WHERE name LIKE :org_prefix)"
            ),
            params,
        )
        await session.execute(text("DELETE FROM app_user WHERE name LIKE :user_prefix"), params)
        await session.execute(text("DELETE FROM org_unit WHERE name LIKE :org_prefix"), params)


@pytest.fixture
async def boundary_cohort(tmp_path):
    """seed -> (cohort_dir, cohort). Namespaced far from anything else this
    session's tests use (generator/cohort.py names orgs/users
    "cohort{seed}_..."/"Cohort{seed}..."), and cleaned up afterward
    regardless of test outcome."""
    seeds_used: list[int] = []

    def _generate(seed: int):
        seeds_used.append(seed)
        seed_dir = tmp_path / str(seed)
        seed_dir.mkdir(parents=True)
        config_path = _write_config(seed_dir)
        out_dir = seed_dir / "cohort"
        cohort = generate_cohort(seed, config_path, out_dir)
        return out_dir, cohort

    yield _generate

    for seed in seeds_used:
        await _cleanup(f"cohort{seed}_%", f"Cohort{seed}%")


async def test_upto_device_time_none_pushes_everything(client, boundary_cohort):
    """P7.1's own exit criterion, re-asserted here as the baseline the
    boundary tests below are compared against."""
    out_dir, cohort = boundary_cohort(909101)

    report = await load(out_dir, upto_device_time=None, client=client)
    assert report.non_accepted == []
    assert report.referrals_pushed > 0
    assert report.referrals_skipped == 0
    assert report.transitions_skipped == 0


async def test_upto_device_time_before_every_referral_pushes_nothing(client, boundary_cohort):
    out_dir, cohort = boundary_cohort(909102)

    earliest_created = min(r.created_device_time for r in cohort.referrals)
    cutoff = earliest_created - timedelta(seconds=1)

    report = await load(out_dir, upto_device_time=cutoff, client=client)
    assert report.referrals_pushed == 0
    assert report.referrals_skipped == len(cohort.referrals)
    assert report.non_accepted == []


async def test_upto_device_time_is_inclusive_at_the_exact_boundary(client, boundary_cohort):
    """The boundary itself: a cutoff exactly equal to a referral's own
    created_device_time must push that referral (`>` in load_cohort.py's
    comparison, not `>=` — the referral is included, not excluded)."""
    out_dir, cohort = boundary_cohort(909103)

    one_referral = min(cohort.referrals, key=lambda r: r.created_device_time)

    report = await load(out_dir, upto_device_time=one_referral.created_device_time, client=client)
    assert report.referrals_pushed >= 1
    assert report.non_accepted == []


async def test_upto_device_time_advancing_in_two_calls_matches_one_call_with_none(
    client, boundary_cohort
):
    """The actual usage pattern P8.1's stepped loop relies on: several
    calls with an advancing cutoff must reach the exact same end state as
    one call with no cutoff at all — idempotent short-circuiting (I1) is
    what makes the second call's re-sent ops harmless, and this is the
    property that guarantees it, not just an assumption about it."""
    out_dir, cohort = boundary_cohort(909104)

    times = sorted(r.created_device_time for r in cohort.referrals)
    midpoint = times[len(times) // 2]

    first = await load(out_dir, upto_device_time=midpoint, client=client)
    second = await load(out_dir, upto_device_time=None, client=client)

    # The second call re-sends every referral already pushed by the first
    # (load() has no local "already sent" cursor — see load_cohort.py's own
    # module docstring) — so its own referrals_pushed count covers the
    # full cohort, and none of those re-sends may be non_accepted.
    assert first.referrals_pushed > 0
    assert first.referrals_pushed < len(cohort.referrals)
    assert second.referrals_pushed == len(cohort.referrals)
    assert second.non_accepted == []


async def test_upto_device_time_skips_only_events_after_the_cutoff_not_the_whole_referral(
    client, boundary_cohort
):
    """A referral pushed (created before cutoff) but whose transitions run
    past the cutoff must have the create pushed and later transitions
    withheld — not the whole referral skipped. Needs a referral with real
    transitions, so this config allows the ordinary path to run without
    dropout."""
    out_dir, cohort = boundary_cohort(909105)

    referral = cohort.referrals[0]
    # Cutoff after creation but before the walk's dwell time could possibly
    # advance it to IN_TRANSIT (generator/timeline.py's dwell is 1-36h).
    cutoff = referral.created_device_time + timedelta(minutes=1)

    report = await load(out_dir, upto_device_time=cutoff, client=client)
    assert report.referrals_pushed >= 1
    assert report.transitions_skipped >= 1
    assert report.non_accepted == []
