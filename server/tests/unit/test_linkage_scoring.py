"""app/linkage/scoring.py — pure, deterministic name similarity.
docs/PHASE6_PLAN.md P6.1's "What P6.1 must prove" table: "Scoring is pure
and deterministic — a sweep that cannot be re-run is not a result."
"""

from app.linkage.normalize import normalize
from app.linkage.scoring import score


def test_identical_strings_score_100():
    assert score("lakshmi devi", "lakshmi devi") == 100.0


def test_deterministic_same_inputs_same_output_every_call():
    a, b = normalize("Lakshmi Devi"), normalize("Lakshmy Devi")
    results = {score(a, b) for _ in range(20)}
    assert len(results) == 1


def test_close_spelling_variant_scores_high():
    a, b = normalize("Lakshmi Devi"), normalize("Lakshmy Devi")
    assert score(a, b) >= 85.0


def test_unrelated_names_score_low():
    a, b = normalize("Lakshmi Devi"), normalize("Iqbal Hussain")
    assert score(a, b) < 50.0


def test_symmetric():
    a, b = normalize("Krishnan Nair"), normalize("Krishnnan Nair")
    assert score(a, b) == score(b, a)
