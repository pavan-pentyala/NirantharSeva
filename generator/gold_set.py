"""Synthetic gold set for identity resolution. docs/PHASE6_PLAN.md P6.1,
docs/IMPLEMENTATION_PLAN.md §10.2 — sliced forward from Phase 7's full
cohort generator per D23 (docs/PHASE6_PLAN.md), so Phase 7 builds the rest
of the cohort on top of this module instead of duplicating it.

Seeded and reproducible: the same --seed produces byte-identical patient
ids and an identical ground_truth_identity.json, run twice in a row.
Patient `created_at` is a fixed synthetic baseline offset by generation
index, not the injected Clock's "now" — nothing here simulates elapsed
time, these timestamps only exist to satisfy the column and to give
exact_match's ORDER BY created_at a stable tie-break, and the real
wall clock would break byte-for-byte reproducibility. This module never
calls datetime.now() or time.time() (the grep-based exit criterion covers
this file too, even though it is outside app/linkage/).

Each duplicate "person" becomes ONE row in `patient` (the "existing"
record, as if registered on an earlier referral) plus ONE query — a name/
phone/village triple that is never written to the database. This
asymmetry matters: if both spellings of a pair were inserted as patient
rows, scoring a query against the candidate set would let it find *itself*
whenever a query happened to reuse its own row's spelling, which is not
how app/sync/push.py's `_resolve_patient` (ADR-009) is ever called — a
referral always names an incoming patient against rows that already exist,
never against itself. scripts/e3_draft_sweep.py resolves each query
against the "existing" rows this module writes.

Inserts those existing rows directly into the `patient` table, scoped to
the village org units app.seed() already created ("Village A",
"Village B"). Run `python -m app.seed` first.

Deliberately includes queries whose true match blocking REJECTS
(docs/decisions/ADR-014.md): cross-village pairs, and same-village pairs
whose phone prefixes disagree. Without them, blocking recall would be
100% by construction and would say nothing (plan §10.2, "Traps" in
docs/PHASE6_PLAN.md).
"""

import argparse
import asyncio
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db import async_session_factory
from app.linkage.normalize import normalize
from generator.names import FILLER_NAMES, NAME_VARIANT_GROUPS

_BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)

# Cycled deterministically across NAME_VARIANT_GROUPS — not sampled, so the
# category mix is fixed by group index and needs no RNG to reproduce.
CATEGORIES = ["same_village_same_phone", "same_village_no_phone", "cross_village", "phone_changed"]

_PHONE_PREFIX = "9810"
_PHONE_PREFIX_CHANGED = "9920"
_PHONE_PREFIX_FILLER = "9830"


@dataclass(frozen=True)
class GeneratedPatient:
    """A row this module writes into `patient` — either an "existing"
    record for a duplicate group, or an unrelated filler used only to give
    blocking a realistic, non-trivial candidate pool."""

    id: uuid.UUID
    name: str
    village: str  # "Village A" | "Village B"
    phone: str | None
    person_id: str
    index: int


@dataclass(frozen=True)
class Query:
    """A name/phone/village triple that is never inserted into `patient`.
    `expected_patient_id` is the id of the GeneratedPatient row it should
    resolve to; `category` is why blocking accepts or rejects it."""

    name: str
    village: str
    phone: str | None
    expected_patient_id: uuid.UUID
    person_id: str
    category: str


def _phone(prefix: str, n: int) -> str:
    return f"{prefix}{n:06d}"


def _namespace(seed: int) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_DNS, f"nirantharseva.gold_set.{seed}")


def _stable_id(ns: uuid.UUID, key: str) -> uuid.UUID:
    return uuid.uuid5(ns, key)


def generate(seed: int) -> tuple[list[GeneratedPatient], list[Query]]:
    """Pure — no I/O and no randomness beyond `seed` shaping the id
    namespace; the category assigned to each name-variant group is a fixed
    round-robin over group index, not a seeded shuffle. Safe to call twice
    and diff."""
    ns = _namespace(seed)
    patients: list[GeneratedPatient] = []
    queries: list[Query] = []
    index = 0

    for group_i, spellings in enumerate(NAME_VARIANT_GROUPS):
        category = CATEGORIES[group_i % len(CATEGORIES)]
        person_id = f"person:{group_i}"
        existing_spelling, query_spelling = spellings[0], spellings[1 % len(spellings)]

        if category == "cross_village":
            existing_village, query_village = "Village A", "Village B"
        else:
            existing_village = query_village = "Village A" if group_i % 2 == 0 else "Village B"

        if category == "same_village_same_phone":
            existing_phone: str | None = _phone(_PHONE_PREFIX, group_i)
            query_phone: str | None = existing_phone
        elif category == "phone_changed":
            existing_phone = _phone(_PHONE_PREFIX, group_i)
            query_phone = _phone(_PHONE_PREFIX_CHANGED, group_i)
        elif category == "cross_village":
            existing_phone = _phone(_PHONE_PREFIX, group_i)
            query_phone = existing_phone
        else:  # same_village_no_phone — the design's own "No number given" case
            existing_phone = _phone(_PHONE_PREFIX, group_i)
            query_phone = None

        existing_id = _stable_id(ns, f"existing:{group_i}")
        patients.append(
            GeneratedPatient(
                id=existing_id,
                name=existing_spelling,
                village=existing_village,
                phone=existing_phone,
                person_id=person_id,
                index=index,
            )
        )
        index += 1

        queries.append(
            Query(
                name=query_spelling,
                village=query_village,
                phone=query_phone,
                expected_patient_id=existing_id,
                person_id=person_id,
                category=category,
            )
        )

    for filler_i, name in enumerate(FILLER_NAMES):
        pid = _stable_id(ns, f"filler:{filler_i}")
        patients.append(
            GeneratedPatient(
                id=pid,
                name=name,
                village="Village A" if filler_i % 2 == 0 else "Village B",
                phone=_phone(_PHONE_PREFIX_FILLER, filler_i),
                person_id=f"filler:{filler_i}",
                index=index,
            )
        )
        index += 1

    return patients, queries


async def village_org_ids(session: AsyncSession) -> dict[str, uuid.UUID]:
    result = await session.execute(text("SELECT id, name FROM org_unit WHERE type = 'VILLAGE'"))
    mapping = {row.name: row.id for row in result.all()}
    missing = {"Village A", "Village B"} - mapping.keys()
    if missing:
        raise RuntimeError(
            f"gold_set needs village org units {sorted(missing)} — run `python -m app.seed` first"
        )
    return mapping


async def write_to_db(
    patients: list[GeneratedPatient], session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with session_factory() as s, s.begin():
        village_ids = await village_org_ids(s)
        for p in patients:
            created_at = _BASE_TIME + timedelta(seconds=p.index)
            await s.execute(
                text(
                    """INSERT INTO patient
                         (id, name, normalized_name, phone, village_org_id, created_at)
                       VALUES
                         (:id, :name, :normalized_name, :phone, :village_org_id, :created_at)
                       ON CONFLICT (id) DO NOTHING"""
                ),
                {
                    "id": p.id,
                    "name": p.name,
                    "normalized_name": normalize(p.name),
                    "phone": p.phone,
                    "village_org_id": village_ids[p.village],
                    "created_at": created_at,
                },
            )


def build_ground_truth(seed: int, patients: list[GeneratedPatient], queries: list[Query]) -> dict:
    return {
        "seed": seed,
        "patients": [
            {
                "id": str(p.id),
                "name": p.name,
                "village": p.village,
                "phone": p.phone,
                "person_id": p.person_id,
            }
            for p in patients
        ],
        "queries": [
            {
                "name": q.name,
                "village": q.village,
                "phone": q.phone,
                "expected_patient_id": str(q.expected_patient_id),
                "person_id": q.person_id,
                "category": q.category,
            }
            for q in queries
        ],
    }


def write_ground_truth(ground_truth: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "ground_truth_identity.json"
    path.write_text(json.dumps(ground_truth, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


async def _main(seed: int, out: Path) -> None:
    patients, queries = generate(seed)
    await write_to_db(patients, async_session_factory)
    ground_truth = build_ground_truth(seed, patients, queries)
    path = write_ground_truth(ground_truth, out)
    by_category: dict[str, int] = {}
    for q in queries:
        by_category[q.category] = by_category.get(q.category, 0) + 1
    print(
        f"gold set: {len(patients)} patients, {len(queries)} duplicate queries "
        f"{by_category} -> {path}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(_main(args.seed, args.out))


if __name__ == "__main__":
    main()
