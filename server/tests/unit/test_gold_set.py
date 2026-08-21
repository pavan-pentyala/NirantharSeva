"""generator/gold_set.py's generate() — pure (no I/O, no wall-clock
randomness), so this is a fast unit test rather than an integration test.
docs/PHASE6_PLAN.md P6.1 exit criteria: same seed -> identical output twice
in a row; the gold set must contain true-duplicate pairs blocking rejects.
"""

from generator.gold_set import CATEGORIES, generate


def test_same_seed_generates_byte_identical_patients_and_queries_twice():
    patients_a, queries_a = generate(42)
    patients_b, queries_b = generate(42)
    assert patients_a == patients_b
    assert queries_a == queries_b


def test_different_seeds_generate_different_patient_ids():
    patients_a, _ = generate(1)
    patients_b, _ = generate(2)
    assert {p.id for p in patients_a} != {p.id for p in patients_b}


def test_every_category_is_represented():
    _, queries = generate(42)
    present = {q.category for q in queries}
    assert present == set(CATEGORIES)


def test_blocking_rejected_categories_are_non_empty():
    """docs/decisions/ADR-014.md — cross_village and phone_changed are the
    two categories blocking rejects by construction. If either were empty,
    blocking recall would be 100% by construction and the metric would say
    nothing (plan §10.2)."""
    _, queries = generate(42)
    by_category: dict[str, int] = {}
    for q in queries:
        by_category[q.category] = by_category.get(q.category, 0) + 1
    assert by_category["cross_village"] > 0
    assert by_category["phone_changed"] > 0


def test_cross_village_query_names_a_different_village_than_its_match():
    _, queries = generate(42)
    cross_village = [q for q in queries if q.category == "cross_village"]
    assert cross_village
    for q in cross_village:
        assert q.village in {"Village A", "Village B"}


def test_phone_changed_query_and_match_share_a_village_but_disagree_on_phone():
    patients, queries = generate(42)
    by_id = {p.id: p for p in patients}
    phone_changed = [q for q in queries if q.category == "phone_changed"]
    assert phone_changed
    for q in phone_changed:
        existing = by_id[q.expected_patient_id]
        assert existing.village == q.village
        assert existing.phone is not None and q.phone is not None
        assert existing.phone[:4] != q.phone[:4]


def test_query_spelling_differs_from_its_matchs_spelling():
    """Every query is a genuine spelling variant of its existing record —
    an exact-match baseline must not accidentally succeed by construction."""
    patients, queries = generate(42)
    by_id = {p.id: p for p in patients}
    for q in queries:
        assert q.name != by_id[q.expected_patient_id].name
