"""Name-similarity score for identity resolution. docs/IMPLEMENTATION_PLAN.md
§10.1.

No database imports — pure function over two already-normalize()d strings.
The E3 threshold sweep re-scores the same blocked candidate set at six
thresholds; it must not need six database round trips to do that, so
scoring stays a pure function of its two string arguments and nothing else.
"""

from rapidfuzz import fuzz


def score(norm_a: str, norm_b: str) -> float:
    """max(token_set_ratio, WRatio) over two normalize()d strings, 0-100.
    token_set_ratio tolerates word-order and repeated-word differences;
    WRatio catches near-identical strings token_set_ratio can over-forgive.
    Taking the max of the two is plan §10.1's own choice, not tuned here."""
    return max(fuzz.token_set_ratio(norm_a, norm_b), fuzz.WRatio(norm_a, norm_b))
