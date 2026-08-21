"""app/linkage/normalize.py — folds diacritics, case, whitespace.
docs/PHASE6_PLAN.md P6.1's "What P6.1 must prove" table, row 1."""

import unicodedata

from app.linkage.normalize import normalize


def test_lowercases():
    assert normalize("Lakshmi Devi") == "lakshmi devi"


def test_strips_leading_and_trailing_whitespace():
    assert normalize("  Ramesh Kumar  ") == "ramesh kumar"


def test_collapses_internal_whitespace_runs():
    assert normalize("Ramesh    Kumar") == "ramesh kumar"


def test_strips_combining_diacritics():
    # NFKD decomposes "ī" into "i" + a combining macron, and "ṣ" into "s" +
    # a combining dot below — stripping combining marks yields "laksmi",
    # not the IAST-to-English romanization "lakshmi" (that would be
    # transliteration, which NFKD does not do).
    assert normalize("Lakṣmī") == "laksmi"


def test_nfc_and_nfd_encodings_of_the_same_diacritic_normalize_the_same():
    # "e" + acute as one precomposed codepoint (NFC) vs "e" + a separate
    # combining acute accent (NFD) — two different byte sequences for the
    # same visible character, both must fold to plain "e".
    nfc = unicodedata.normalize("NFC", "é")
    nfd = unicodedata.normalize("NFD", "é")
    assert nfc != nfd  # sanity: the two inputs really are different strings
    assert normalize(nfc) == normalize(nfd) == "e"


def test_empty_string():
    assert normalize("") == ""


def test_idempotent():
    once = normalize("  Lakshmi   Devi  ")
    assert normalize(once) == once
