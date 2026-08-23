"""server/scripts/load_cohort.py against the real ASGI app (docs/decisions
/ADR-015.md) — a small generated cohort, replayed through the real
/sync/push, same as a real device would. Exit criteria from
docs/PHASE7_PLAN.md's P7.1 table: verify_replay clean afterward, zero
ESCALATED events before any sweep, every referral's origin_org_id is its
own generated ASHA's village.

Cleans up every row it creates. GET /org_units (tests/integration/
test_org_units.py) asserts the EXACT set of org names in the whole
database, unscoped — generator/cohort.py's own org names never collide
with the seeded ones (docs/PHASE7_PLAN.md "Traps"), but a genuinely new,
non-colliding org left behind still breaks that exact-set assertion for
any test that happens to run afterward in the same session. Same class of
cross-file pollution P6.2 hit twice (docs/PHASE2_OBSERVATIONS.md
observations 44-46) — the fix there was to stop colliding; the fix here is
to leave nothing behind at all, since this test's whole point is to
persist real rows through a real load.
"""

from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import async_session_factory
from app.verify_replay import verify_all
from generator.cli import run as generate_cohort
from scripts.load_cohort import load

_SMALL_CONFIG = """
n_patients: 12
n_villages: 2
n_ashas: 2
n_facilities: 1
dropout_rate:
  CREATED: 0.2
  IN_TRANSIT: 0.2
  ARRIVED: 0.2
  TREATED: 0.2
  BACK_REFERRED: 0.2
name_variant_rate: 0.5
duplicate_rate: 0.3
connectivity_profile: intermittent
"""


def _write_small_config(tmp_path: Path) -> Path:
    path = tmp_path / "small.yaml"
    path.write_text(_SMALL_CONFIG, encoding="utf-8")
    return path


async def _cleanup(session: AsyncSession, user_prefix: str, org_prefix: str) -> None:
    # patient_subq is keyed off village_org_id, not off referral.patient_id —
    # a subquery through `referral` would return nothing once the referral
    # rows themselves are deleted below, silently skipping the patient
    # delete and then failing on fk_patient_created_by when app_user is
    # deleted next (found by actually running this cleanup, not by
    # reasoning about FK order).
    referral_subq = (
        "SELECT r.id FROM referral r JOIN app_user u ON u.id = r.origin_user_id "
        "WHERE u.name LIKE :user_prefix"
    )
    patient_subq = (
        "SELECT id FROM patient WHERE village_org_id IN "
        "(SELECT id FROM org_unit WHERE name LIKE :org_prefix)"
    )
    params = {"user_prefix": user_prefix, "org_prefix": org_prefix}
    await session.execute(
        text(f"DELETE FROM identity_review WHERE new_patient_id IN ({patient_subq})"), params
    )
    await session.execute(
        text(f"DELETE FROM patient_alias WHERE patient_id IN ({patient_subq})"), params
    )
    await session.execute(
        text(f"DELETE FROM referral_event WHERE referral_id IN ({referral_subq})"), params
    )
    await session.execute(
        text(f"DELETE FROM sync_conflict WHERE entity_id IN ({referral_subq})"), params
    )
    await session.execute(
        text(f"DELETE FROM escalation WHERE referral_id IN ({referral_subq})"), params
    )
    await session.execute(text(f"DELETE FROM referral WHERE id IN ({referral_subq})"), params)
    await session.execute(text(f"DELETE FROM patient WHERE id IN ({patient_subq})"), params)
    await session.execute(text("DELETE FROM app_user WHERE name LIKE :user_prefix"), params)
    await session.execute(text("DELETE FROM org_unit WHERE name LIKE :org_prefix"), params)


async def test_load_cohort_replays_cleanly_through_sync_push(client, tmp_path):
    # A seed namespaced far from anything else this session's tests use
    # (generator/cohort.py names orgs/users "cohort{seed}_..."), so this
    # test can run alongside every other test in the same database.
    seed = 909001
    user_prefix, org_prefix = f"cohort{seed}_%", f"Cohort{seed}%"
    config_path = _write_small_config(tmp_path)
    out_dir = tmp_path / "cohort"
    generate_cohort(seed, config_path, out_dir)

    try:
        report = await load(out_dir, client=client)

        assert report.non_accepted == []
        assert report.referrals_pushed > 0
        assert report.transitions_pushed >= 0

        verify_report = await verify_all()
        assert verify_report.ok, verify_report.mismatches

        async with async_session_factory() as session:
            escalated = (
                await session.execute(
                    text(
                        "SELECT COUNT(*) FROM referral_event re "
                        "JOIN app_user u ON u.id = re.actor_user_id "
                        "WHERE u.name LIKE :prefix AND re.to_state = 'ESCALATED'"
                    ),
                    {"prefix": user_prefix},
                )
            ).scalar_one()
            assert escalated == 0

            rows = (
                await session.execute(
                    text(
                        "SELECT r.origin_org_id, u.org_unit_id "
                        "FROM referral r "
                        "JOIN app_user u ON u.name LIKE :prefix "
                        "  AND u.role = 'ASHA' AND u.id = r.origin_user_id"
                    ),
                    {"prefix": user_prefix},
                )
            ).all()
            assert rows, "expected at least one generated referral"
            for row in rows:
                assert row.origin_org_id == row.org_unit_id
    finally:
        async with async_session_factory() as session, session.begin():
            await _cleanup(session, user_prefix, org_prefix)


async def test_load_cohort_is_idempotent_on_a_second_run(client, tmp_path):
    seed = 909002
    user_prefix, org_prefix = f"cohort{seed}_%", f"Cohort{seed}%"
    config_path = _write_small_config(tmp_path)
    out_dir = tmp_path / "cohort2"
    generate_cohort(seed, config_path, out_dir)

    try:
        first = await load(out_dir, client=client)
        second = await load(out_dir, client=client)

        assert first.referrals_pushed == second.referrals_pushed
        assert first.transitions_pushed == second.transitions_pushed
        assert second.non_accepted == []

        async with async_session_factory() as session:
            count = (
                await session.execute(
                    text(
                        "SELECT COUNT(*) FROM referral r "
                        "JOIN app_user u ON u.id = r.origin_user_id "
                        "WHERE u.name LIKE :prefix"
                    ),
                    {"prefix": user_prefix},
                )
            ).scalar_one()
            # A second run must not create duplicate referral rows — every
            # op_id is deterministic (I1), so the replay claims each receipt
            # and applies nothing new.
            assert count == first.referrals_pushed
    finally:
        async with async_session_factory() as session, session.begin():
            await _cleanup(session, user_prefix, org_prefix)
