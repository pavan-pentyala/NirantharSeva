"""generator/cohort.py + generator/timeline.py — pure (no I/O, no
wall-clock randomness), so this is a fast unit test rather than an
integration test. docs/PHASE7_PLAN.md P7.1 exit criteria: same seed ->
byte-identical output; a different seed -> different output; every
referral's target_org is an ancestor of its own origin village; zero
ESCALATED events by construction; no unintended same-village name
collision above the review floor.
"""

from app.config import get_settings
from app.linkage.normalize import normalize
from app.linkage.scoring import score
from generator.cli import DEFAULTS
from generator.cohort import build_cohort
from generator.timeline import build_events


def _config(**overrides):
    config = {**DEFAULTS, **overrides}
    if "dropout_rate" in overrides:
        config["dropout_rate"] = {**DEFAULTS["dropout_rate"], **overrides["dropout_rate"]}
    return config


def test_same_seed_produces_byte_identical_cohort_twice():
    config = _config(n_patients=40, n_villages=4, n_facilities=2)
    a = build_cohort(42, config)
    b = build_cohort(42, config)
    assert a.district == b.district
    assert a.patients == b.patients
    assert a.referrals == b.referrals
    events_a = build_events(42, config, a)
    events_b = build_events(42, config, b)
    assert events_a == events_b


def test_different_seed_produces_different_cohort():
    config = _config(n_patients=40, n_villages=4, n_facilities=2)
    a = build_cohort(1, config)
    b = build_cohort(2, config)
    assert {p.record_id for p in a.patients} != {p.record_id for p in b.patients}


def test_every_villages_target_org_is_its_own_ancestor_phc():
    """ADR-005 at generator scale — the executable form of session
    instruction #7. A village's target must be reached by ordinary subtree
    ascent (village -> sub-centre -> PHC), never a facility outside its
    own branch."""
    config = _config(n_patients=40, n_villages=6, n_facilities=3)
    cohort = build_cohort(42, config)
    district = cohort.district

    org_by_id = {row.org_id: row for row in district.org_units}
    for village_index, village_org_id in enumerate(district.village_org_id):
        ancestors: set = set()
        current = village_org_id
        while current is not None:
            ancestors.add(current)
            current = org_by_id[current].parent_id
        assert district.village_target_org[village_index] in ancestors


def test_generator_never_emits_an_escalated_event():
    config = _config(
        n_patients=60,
        n_villages=4,
        n_facilities=2,
        dropout_rate={
            "CREATED": 0.0,
            "IN_TRANSIT": 0.0,
            "ARRIVED": 0.0,
            "TREATED": 0.0,
            "BACK_REFERRED": 0.0,
        },
    )
    cohort = build_cohort(42, config)
    events = build_events(42, config, cohort)
    assert events  # zero dropout, so every referral should have events
    assert all(e.to_state != "ESCALATED" for e in events)
    assert all(e.from_state != "ESCALATED" for e in events)


def test_dropout_rate_zero_means_every_referral_reaches_closed():
    config = _config(
        n_patients=30,
        n_villages=3,
        n_facilities=1,
        dropout_rate={
            "CREATED": 0.0,
            "IN_TRANSIT": 0.0,
            "ARRIVED": 0.0,
            "TREATED": 0.0,
            "BACK_REFERRED": 0.0,
        },
    )
    cohort = build_cohort(42, config)
    events = build_events(42, config, cohort)
    by_referral: dict = {}
    for e in events:
        by_referral.setdefault(e.referral_id, []).append(e)
    assert len(by_referral) == len(cohort.referrals)
    for _referral_id, rows in by_referral.items():
        rows.sort(key=lambda e: e.step)
        assert rows[-1].to_state == "CLOSED"


def test_dropout_rate_one_means_no_referral_leaves_created():
    config = _config(
        n_patients=20,
        n_villages=2,
        n_facilities=1,
        dropout_rate={
            "CREATED": 1.0,
            "IN_TRANSIT": 0.0,
            "ARRIVED": 0.0,
            "TREATED": 0.0,
            "BACK_REFERRED": 0.0,
        },
    )
    cohort = build_cohort(42, config)
    events = build_events(42, config, cohort)
    assert events == []


def test_duplicate_pairs_are_the_only_same_village_pairs_above_review_floor():
    """Instruction #9's guard, checked directly against the generator's own
    output rather than trusted — the redraw mechanism inside
    generator/cohort.py must actually have run and worked."""
    config = _config(n_patients=200, n_villages=8, n_facilities=2, duplicate_rate=0.10)
    cohort = build_cohort(42, config)
    review_floor = get_settings().identity_review_floor

    by_village: dict[int, list] = {}
    for p in cohort.patients:
        by_village.setdefault(p.village_index, []).append(p)

    duplicate_pairs = {
        frozenset({q["record_id"], q["expected_record_id"]}) for q in cohort.ground_truth.queries
    }

    offenders = []
    for records in by_village.values():
        for i in range(len(records)):
            for j in range(i + 1, len(records)):
                a, b = records[i], records[j]
                if a.person_id == b.person_id:
                    continue
                s = score(normalize(a.name), normalize(b.name))
                if s >= review_floor:
                    pair = frozenset({str(a.record_id), str(b.record_id)})
                    if pair not in duplicate_pairs:
                        offenders.append((a.name, b.name, s))
    assert offenders == []


def test_duplicate_pairs_do_score_above_review_floor():
    """The guard above is not vacuous: real duplicate pairs must exist and
    must score high, or the check above would pass by having nothing to
    check (docs/PHASE7_PLAN.md "a guard that cannot fail is not a guard")."""
    config = _config(n_patients=200, n_villages=8, n_facilities=2, duplicate_rate=0.10)
    cohort = build_cohort(42, config)
    assert cohort.ground_truth.queries
    by_id = {str(p.record_id): p for p in cohort.patients}
    for q in cohort.ground_truth.queries:
        a = by_id[q["record_id"]]
        b = by_id[q["expected_record_id"]]
        s = score(normalize(a.name), normalize(b.name))
        assert s >= get_settings().identity_review_floor


def test_config_resolution_fills_in_defaults_and_lets_seed_override_win():
    from pathlib import Path

    from generator.cli import resolve_config

    seed, config = resolve_config(Path("configs/e1_dropout25.yaml"), seed_override=99)
    assert seed == 99
    assert config["n_patients"] == 200
    assert config["dropout_rate"]["IN_TRANSIT"] == 0.25
