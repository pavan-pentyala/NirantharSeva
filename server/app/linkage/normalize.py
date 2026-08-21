"""Name normalisation for identity resolution. docs/IMPLEMENTATION_PLAN.md
§10.1.

No database imports. No framework imports — same purity discipline
app/domain/states.py promises, for the same reason: the E3 threshold sweep
re-scores a fixed candidate set six times (once per threshold in the
sweep) and must not need a database round trip to do it.
"""

import re
import unicodedata

_WHITESPACE_RUN = re.compile(r"\s+")


def normalize(raw: str) -> str:
    """NFKD-decompose, strip combining diacritics, lowercase, collapse
    whitespace. "Lakṣmī" and "Lakshmi" normalize to the same string;
    "  Ramesh   Kumar " and "Ramesh Kumar" do too."""
    decomposed = unicodedata.normalize("NFKD", raw)
    without_diacritics = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    collapsed = _WHITESPACE_RUN.sub(" ", without_diacritics.strip())
    return collapsed.lower()
