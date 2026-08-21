"""Hand-written Indian name-variant table. docs/DOMAIN_PRIMER.md "Names in
test and demo data", docs/IMPLEMENTATION_PLAN.md §11.1 — sliced forward
into Phase 6 per D23 (docs/PHASE6_PLAN.md), so Phase 7's full cohort
generator builds on this module rather than duplicating it.

Every spelling below is a transliteration a real record clerk has actually
written for that name. No random character noise: a random insertion,
deletion or swap invents a mistake no human makes and makes the fuzzy
matcher look better than it is — an indefensible number in Chapter 4
(§11.1, DOMAIN_PRIMER, docs/PHASE6_PLAN.md's "Traps").
"""

# Same person, different spellings of the full name. Each inner list's
# first entry is the "reference" spelling; generator/gold_set.py is free to
# draw any entry for any generated record, so the canonical form is not
# guaranteed to appear twice by construction.
NAME_VARIANT_GROUPS: list[list[str]] = [
    ["Lakshmi Devi", "Lakshmy Devi", "Laxmi Devi"],
    ["Krishnan Nair", "Krishnnan Nair"],
    ["Muhammad Ali", "Mohammed Ali", "Mohamad Ali"],
    ["Sunita Kumari", "Sunitha Kumari"],
    ["Fatima Begum", "Fathima Begum"],
    ["Rukmini Devi", "Rukmani Devi"],
    ["Ibrahim Khan", "Ebrahim Khan"],
    ["Parvati Devi", "Parvathi Devi"],
    ["Chandra Shekhar", "Chandrashekhar"],
    ["Zainab Bibi", "Zaynab Bibi"],
    ["Geeta Kumari", "Gita Kumari"],
    ["Yusuf Sheikh", "Yousuf Sheikh"],
    ["Saraswati Devi", "Sarasvati Devi"],
    ["Aisha Khatun", "Ayesha Khatun"],
    ["Ramesh Yadav", "Ramesh Yadava"],
]

# Distinct, unrelated people — no variant relationship to each other or to
# NAME_VARIANT_GROUPS. Used to fill out true negatives in the gold set:
# candidates that must NOT be scored as a match to anything above.
FILLER_NAMES: list[str] = [
    "Suresh Kumar",
    "Anita Sharma",
    "Vikram Rathore",
    "Meena Verma",
    "Arvind Tiwari",
    "Radha Singh",
    "Deepak Chauhan",
    "Kavita Joshi",
    "Naseem Akhtar",
    "Rafiq Ansari",
    "Shabana Parveen",
    "Harish Chandra",
    "Manju Bala",
    "Om Prakash",
    "Salma Bano",
    "Girish Pandey",
    "Nirmala Bai",
    "Iqbal Hussain",
    "Kamla Devi",
    "Rajendra Prasad",
]
