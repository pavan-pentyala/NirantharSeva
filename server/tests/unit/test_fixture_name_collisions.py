"""Fixture-collision guard. docs/PHASE7_PLAN.md P7.2, "Traps" #4;
docs/OBSERVATIONS.md observations 44-46.

A maintained registry of patient names used by fixtures that are reachable
by the real identity-resolution pipeline — pushed through `create_referral`
(ADR-009), or inserted directly with an explicit, real `village_org_id` —
grouped by which village they land in. Two DIFFERENT-person entries sharing
a group must never score >= `IDENTITY_REVIEW_FLOOR` against each other, or
a later test's "different person" fixture can silently resolve to an
earlier test's patient row (observations 44-46's exact failure shape) —
or, found while building this guard, silently queue a spurious
`identity_review` pair instead of cleanly creating a new patient
(`tests/integration/test_patient_resolution.py`'s "Beta" fixture did
exactly this against its own file's "Alpha", 87.8 via rapidfuzz — fixed
alongside this guard, not left for the guard to merely report).

Deliberately excludes fixtures inserted with NO `village_org_id` (NULL) —
"Test Patient", "Verifier Test Patient", "Sweep Test Patient", "Scoping
Test Patient", "Timeline Test Patient" and others across Phases 2-5, all
of which score >= REVIEW_FLOOR against each other (checked while building
this guard). `app/linkage/blocking.py` always scopes candidates by the
PUSHING ACTOR's own village, which is never null for a real user — a
NULL-village row can never be found as a candidate for anything a real
device does, so two of them scoring high against each other in a direct,
unblocked comparison is not the failure this guard exists to catch. The
only thing that WOULD make it a real risk is a test that scores every
patient in the database pairwise without blocking first — exactly the
unblocked fuzzy-match this project's own rule forbids building
(`docs/HANDOFF_CLAUDE_CODE.md` §5) — so leaving the NULL-village names
alone here is consistent with that rule, not a gap in it.

**Add an entry here** whenever a new fixture pushes a `patient_name`
through `create_referral`, or inserts a `patient` row directly with a
real (non-null) `village_org_id`, and is meant to represent a DIFFERENT
person from every other fixture. A fixture that is deliberately a
near-duplicate of another one — testing scoring behaviour itself, like
`tests/integration/test_linkage_pipeline.py`'s boundary pairs — does not
belong here; its high score against its own pair is the point, not an
accident.
"""

from app.config import get_settings
from app.linkage.normalize import normalize
from app.linkage.scoring import score

# (name, village_label) — village_label is an arbitrary string; only
# equality matters, not what it names. Two entries sharing a label are
# compared; entries in different labels never are.
REGISTRY: list[tuple[str, str]] = [
    # app/seed.py (D4) — the one district every other village-scoped
    # fixture in this suite is pushed against.
    ("Lakshmi Devi", "VILLAGE_A"),
    ("Ramesh Kumar", "VILLAGE_A"),
    ("Fatima Begum", "VILLAGE_B"),
    ("Suresh Yadav", "VILLAGE_B"),
    # tests/integration/test_linkage_pipeline.py — non-paired names only.
    # Its own near-duplicate PAIRS (Muhammad Ali/Mohammed Ali, Ibrahim
    # Khan/Ebrahim Khan, Yusuf Sheikh/Yousuf Sheikh, Chandra Shekhar/
    # Chandrashekhar) are that file's own test subject — see the module
    # docstring above.
    ("Zainab Bibi", "VILLAGE_A"),
    ("Chandra Shekhar", "VILLAGE_A"),
    ("Nobody Matches This Query String", "VILLAGE_A"),
    # tests/integration/test_patient_resolution.py
    ("Test Dedup Patient Alpha", "VILLAGE_A"),
    ("Village Split Duplicate Fixture", "VILLAGE_A"),
    (
        "Village Split Duplicate Fixture",
        "VILLAGE_B",
    ),  # same name, opposite village — the point of that test
    ("Test New Patient Gamma", "VILLAGE_A"),
    # tests/integration/test_push_idempotent.py
    ("Idempotent Test Patient", "VILLAGE_A"),
    ("Repeat Push Second Patient", "VILLAGE_A"),
    # tests/integration/test_pull_referral_payload.py
    ("Test Pull Payload Patient", "VILLAGE_A"),
    ("Transition Snapshot Person", "VILLAGE_A"),
    # tests/integration/test_dashboard.py
    ("Dashboard Test Patient A", "VILLAGE_A"),
]


def find_collisions(
    entries: list[tuple[str, str]], floor: float
) -> list[tuple[str, str, str, float]]:
    """Pure. Returns (name_a, name_b, village_label, score) for every pair
    that shares a village_label, has different names, and scores >= floor."""
    by_village: dict[str, list[str]] = {}
    for name, village in entries:
        by_village.setdefault(village, []).append(name)

    collisions: list[tuple[str, str, str, float]] = []
    for village, names in by_village.items():
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                a, b = names[i], names[j]
                if a == b:
                    continue
                s = score(normalize(a), normalize(b))
                if s >= floor:
                    collisions.append((a, b, village, s))
    return collisions


def test_no_registered_fixture_collides_with_a_different_one_in_its_own_village():
    floor = get_settings().identity_review_floor
    collisions = find_collisions(REGISTRY, floor)
    assert collisions == [], (
        f"{len(collisions)} fixture pair(s) score >= {floor} in the same village — "
        "rename one so create_referral's real pipeline (ADR-009) can't silently "
        f"merge, or spuriously queue a review for, two 'different person' fixtures: "
        f"{collisions}"
    )


def test_the_guard_fails_on_a_deliberately_introduced_collision():
    """A guard that cannot fail is not a guard (docs/PHASE7_PLAN.md P7.2
    exit criteria). Exercised against a local, throwaway pair — never
    REGISTRY itself, which must stay clean."""
    colliding_pair = [
        ("Repeat Collision Fixture Person", "VILLAGE_A"),
        ("Repeat Collision Fixture Human", "VILLAGE_A"),
    ]
    floor = get_settings().identity_review_floor
    assert find_collisions(colliding_pair, floor) != []
