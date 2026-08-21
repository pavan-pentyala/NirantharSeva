"""Threshold sweep over the P6.1 draft gold set. docs/PHASE6_PLAN.md P6.1
build order #10, docs/IMPLEMENTATION_PLAN.md §10.2/§10.3.

Loads ground_truth_identity.json (generator/gold_set.py), then for every
query runs app/linkage/blocking.py's block() and app/linkage/scoring.py's
score() exactly ONCE, and classifies that same scored candidate set at
every threshold in {80, 85, 88, 90, 92, 95} — normalize.py and scoring.py
are pure precisely so this loop never re-queries the database per
threshold.

Phase 8's experiments/e3.py supersedes this at three seeds over the full
Phase 7 cohort (docs/IMPLEMENTATION_PLAN.md §11, §4 phase map) — this
script produces the P6.1 **draft** only (D23/D24, docs/PHASE6_PLAN.md).

Run as:
    docker compose run --rm api python scripts/e3_draft_sweep.py \
        --gold /app/results/e3_draft/
"""

import argparse
import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings, get_settings
from app.db import async_session_factory
from app.linkage.blocking import block
from app.linkage.normalize import normalize
from app.linkage.scoring import score
from generator.gold_set import village_org_ids

THRESHOLDS = [80, 85, 88, 90, 92, 95]


@dataclass
class QueryOutcome:
    person_id: str
    category: str
    expected_id: str
    blocking_survived: bool
    best_id: str | None
    best_score: float
    naive_id: str | None


async def _naive_exact_match(session: AsyncSession, name: str, village_org_id) -> str | None:
    """ADR-009's pre-Phase-6 rule: exact match on (name.strip().lower(),
    village_org_id). Coincides with app/linkage/normalize.py's output for
    every name in this gold set (no diacritics, single internal spaces) —
    the staleness gap migration 0007 backfills only affects rows written
    before Phase 6, and every row this evaluation reads was written by
    generator/gold_set.py using the new normalize() already."""
    result = await session.execute(
        text("SELECT id FROM patient WHERE normalized_name = :n AND village_org_id = :v"),
        {"n": name.strip().lower(), "v": village_org_id},
    )
    row = result.first()
    return str(row.id) if row is not None else None


async def _evaluate_query(session: AsyncSession, q: dict, village_ids: dict) -> QueryOutcome:
    village_org_id = village_ids[q["village"]]
    norm = normalize(q["name"])

    candidates = await block(session, village_org_id=village_org_id, phone=q["phone"])
    scored = [(c.id, score(norm, c.normalized_name)) for c in candidates]
    best_id, best_score = max(scored, key=lambda pair: pair[1], default=(None, 0.0))
    blocking_survived = any(str(c.id) == q["expected_patient_id"] for c in candidates)
    naive_id = await _naive_exact_match(session, q["name"], village_org_id)

    return QueryOutcome(
        person_id=q["person_id"],
        category=q["category"],
        expected_id=q["expected_patient_id"],
        blocking_survived=blocking_survived,
        best_id=str(best_id) if best_id is not None else None,
        best_score=best_score,
        naive_id=naive_id,
    )


def _prf(tp: int, predicted_positive: int, actual_positive: int) -> dict:
    precision = tp / predicted_positive if predicted_positive else 0.0
    recall = tp / actual_positive if actual_positive else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def _sweep(outcomes: list[QueryOutcome]) -> list[dict]:
    rows = []
    actual_positive = len(outcomes)
    for t in THRESHOLDS:
        tp = fp = 0
        for o in outcomes:
            predicted = o.best_id if (o.best_id is not None and o.best_score >= t) else None
            if predicted is None:
                continue
            if predicted == o.expected_id:
                tp += 1
            else:
                fp += 1
        row = {"threshold": t, "tp": tp, "fp": fp}
        row.update(_prf(tp, tp + fp, actual_positive))
        rows.append(row)
    return rows


def _naive_baseline(outcomes: list[QueryOutcome]) -> dict:
    tp = sum(1 for o in outcomes if o.naive_id == o.expected_id)
    predicted_positive = sum(1 for o in outcomes if o.naive_id is not None)
    result = {"tp": tp, "predicted_positive": predicted_positive}
    result.update(_prf(tp, predicted_positive, len(outcomes)))
    return result


def _failure_taxonomy(outcomes: list[QueryOutcome], settings: Settings) -> dict[str, int]:
    """Attributes every miss, at the OPERATIONAL review floor (not the
    swept grid), to the stage that let it through. "normalize" is included
    for completeness even when this gold set exercises no case that lands
    there — an honestly empty bucket, not a fabricated one; see
    generator/names.py's docstring on why no random noise is used to force
    one."""
    taxonomy = {"blocking": 0, "scoring": 0, "threshold": 0, "normalize": 0}
    for o in outcomes:
        found = o.best_id == o.expected_id and o.best_score >= settings.identity_review_floor
        if found:
            continue
        if not o.blocking_survived:
            taxonomy["blocking"] += 1
        elif o.best_id != o.expected_id:
            taxonomy["scoring"] += 1
        else:
            taxonomy["threshold"] += 1
    return taxonomy


async def evaluate(gold: dict, session_factory: async_sessionmaker[AsyncSession]) -> dict:
    settings = get_settings()
    async with session_factory() as session:
        village_ids = await village_org_ids(session)
        outcomes = [await _evaluate_query(session, q, village_ids) for q in gold["queries"]]

    blocking_recall = (
        sum(o.blocking_survived for o in outcomes) / len(outcomes) if outcomes else 0.0
    )
    auto_resolved = sum(
        1
        for o in outcomes
        if o.best_id is not None and o.best_score >= settings.identity_auto_accept
    )
    auto_resolution_rate = auto_resolved / len(outcomes) if outcomes else 0.0

    return {
        "seed": gold["seed"],
        "n_queries": len(outcomes),
        "operational_thresholds": {
            "auto_accept": settings.identity_auto_accept,
            "review_floor": settings.identity_review_floor,
        },
        "blocking_recall": blocking_recall,
        "auto_resolution_rate": auto_resolution_rate,
        "failure_taxonomy": _failure_taxonomy(outcomes, settings),
        "naive_exact_match_baseline": _naive_baseline(outcomes),
        "threshold_sweep": _sweep(outcomes),
    }


def _print_report(report: dict) -> None:
    print(f"seed={report['seed']}  n_queries={report['n_queries']}")
    print(f"blocking_recall={report['blocking_recall']:.3f}")
    print(f"auto_resolution_rate={report['auto_resolution_rate']:.3f}")
    print(f"failure_taxonomy={report['failure_taxonomy']}")
    nb = report["naive_exact_match_baseline"]
    print(
        f"naive_exact_match_baseline: precision={nb['precision']:.3f} "
        f"recall={nb['recall']:.3f} f1={nb['f1']:.3f}"
    )
    print(f"{'threshold':>9} {'precision':>9} {'recall':>7} {'f1':>7} {'tp':>4} {'fp':>4}")
    for row in report["threshold_sweep"]:
        print(
            f"{row['threshold']:>9} {row['precision']:>9.3f} {row['recall']:>7.3f} "
            f"{row['f1']:>7.3f} {row['tp']:>4} {row['fp']:>4}"
        )


async def _main(gold_dir: Path, out_dir: Path) -> None:
    gold = json.loads((gold_dir / "ground_truth_identity.json").read_text(encoding="utf-8"))
    report = await evaluate(gold, async_session_factory)

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "e3_draft_sweep.json"
    out_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    _print_report(report)
    print(f"-> {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--gold", type=Path, required=True, help="dir with ground_truth_identity.json"
    )
    parser.add_argument("--out", type=Path, default=None, help="defaults to --gold")
    args = parser.parse_args()
    asyncio.run(_main(args.gold, args.out or args.gold))


if __name__ == "__main__":
    main()
