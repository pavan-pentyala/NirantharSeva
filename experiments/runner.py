"""Parent orchestrator. docs/decisions/ADR-016.md, docs/PHASE8_PLAN.md.

For each (cell, seed): create a fresh database (ADR-016), spawn
`python -m experiments.cell` as its own OS process with DATABASE_URL and
the rest of that cell's env already set, capture its one printed JSON row,
append it to raw.csv, then drop the database. Cells run sequentially —
each one is its own process and its own database, so parallelising them
later costs nothing structural (ADR-016's "makes easy"), it just wasn't
needed to meet P8.1's exit criteria.

Invoked as:
    python -m experiments.runner --exp E1 --out results/e1/ \\
        [--seeds 42,7,13] [--cell <cell_id>] [--dry-run] [--keep-db]
"""

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import yaml

from app.config import get_settings
from experiments.cell import ROW_MARKER
from experiments.db_lifecycle import create_database, database_url_for, drop_database
from experiments.grid import SEEDS, SIM_START, Cell, cells_for

_COMMON_COLUMNS = [
    "exp",
    "cell_id",
    "seed",
    "run_id",
    "wall_seconds",
    "cohort_patients",
    "cohort_referrals",
    "cohort_events",
    "git_sha",
    "alembic_head",
]

# Per docs/PHASE8_PLAN.md "raw.csv columns" — one column set per experiment,
# since E2/E3/E6 don't share E1's own (escalation_on, dropped_total, ...)
# shape. E1's own extra "reconciled_count" (P8.1, not in the plan's fixed
# table) is kept as-is — already shipped and committed.
RAW_COLUMNS_BY_EXP: dict[str, list[str]] = {
    "E1": _COMMON_COLUMNS
    + [
        "escalation_on",
        "dropout_rate",
        "response_rate",
        "referrals_total",
        "referrals_closed",
        "closure_rate",
        "dropped_total",
        "escalations_raised",
        "escalations_true_positive",
        "escalations_false_positive",
        "dropped_detected",
        "detection_rate",
        "mean_hours_to_detection",
        "resumed_count",
        "resumed_and_closed",
        "reconciled_count",
    ],
    "E2": _COMMON_COLUMNS
    + [
        "sla_window_hours",
        "response_rate",
        "referrals_total",
        "referrals_closed",
        "closure_rate",
        "escalations_raised",
        "escalations_per_100_referrals",
        "escalations_false_positive",
    ],
    "E3": _COMMON_COLUMNS
    + [
        "threshold",
        "precision",
        "recall",
        "f1",
        "auto_resolution_rate",
        "blocking_recall",
        "miss_normalize",
        "miss_blocking",
        "miss_scoring",
        "miss_threshold",
    ],
    "E6": _COMMON_COLUMNS
    + [
        "referrals_total",
        "closed",
        "lost",
        "stuck_open",
        "escalated_unresolved",
        "unresolvable_fraction",
        "identity_review_pending",
    ],
}


def _sanitize(value: str) -> str:
    return "".join(c if (c.isalnum() or c == "_") else "_" for c in str(value)).lower()


def _db_name(exp: str, cell_id: str, seed: int) -> str:
    return f"ns_exp_{_sanitize(exp)}_{_sanitize(cell_id)}_s{seed}"


def _run_cell_subprocess(
    base_database_url: str, exp: str, cell: Cell, seed: int, keep_db: bool
) -> list[dict[str, Any]]:
    db_name = _db_name(exp, cell.cell_id, seed)
    print(f"[{exp}/{cell.cell_id}/seed={seed}] creating database {db_name}", file=sys.stderr)
    _run_async(create_database, base_database_url, db_name)

    env = {
        **os.environ,
        "DATABASE_URL": database_url_for(base_database_url, db_name),
        "CLOCK_MODE": "simulated",
        "SIM_START": SIM_START,
        "SLA_SCALE": "1.0",
        "RUN_ID": f"{exp.lower()}_{cell.cell_id}_s{seed}",
    }

    started = time.monotonic()
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "experiments.cell",
            "--exp",
            exp,
            "--cell-id",
            cell.cell_id,
            "--seed",
            str(seed),
        ],
        cwd="/app",
        env=env,
        capture_output=True,
        text=True,
    )
    elapsed = time.monotonic() - started

    if not keep_db:
        _run_async(drop_database, base_database_url, db_name)

    if result.returncode != 0:
        print(result.stdout, file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        raise RuntimeError(
            f"cell {exp}/{cell.cell_id}/seed={seed} failed (exit {result.returncode}) — "
            f"no row written. See its stderr above."
        )

    # Only lines carrying experiments.cell's own ROW_MARKER prefix are a
    # cell's row(s) — everything else on this stdout (alembic's migration
    # chatter, and app/instrumentation/logging.py's own structured JSON
    # request logs, which are ALSO valid JSON and outnumber the real rows by
    # a hundred to one during a cohort load) is not. E1 prints one row, E3
    # prints six (docs/PHASE8_PLAN.md's "Cell counts" table) — "the last
    # line" and "any line that parses as JSON" are both wrong once more than
    # one experiment is in play; see experiments/cell.py's own comment.
    rows: list[dict[str, Any]] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line.startswith(ROW_MARKER):
            continue
        rows.append(json.loads(line[len(ROW_MARKER) :]))
    if not rows:
        print(result.stdout, file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        raise RuntimeError(f"cell {exp}/{cell.cell_id}/seed={seed} printed no JSON row")

    print(
        f"[{exp}/{cell.cell_id}/seed={seed}] done in {elapsed:.1f}s "
        f"({len(rows)} row(s), cell reported {rows[0].get('wall_seconds')}s)",
        file=sys.stderr,
    )
    return rows


def _run_async(fn, *args) -> None:
    import asyncio

    asyncio.run(fn(*args))


def _write_raw_csv(rows: list[dict[str, Any]], out_dir: Path, columns: list[str]) -> None:
    path = out_dir / "raw.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k) for k in columns})


def _write_cells_resolved(exp: str, cells: list[Cell], seeds: list[int], out_dir: Path) -> None:
    payload = {
        "exp": exp,
        "seeds": seeds,
        "sim_start": SIM_START,
        "cells": [{**cell.as_dict(), "cohort_config": cell.cohort_config()} for cell in cells],
    }
    (out_dir / "cells.resolved.yaml").write_text(
        yaml.safe_dump(payload, sort_keys=False, default_flow_style=False), encoding="utf-8"
    )


def _write_manifest(
    exp: str, rows: list[dict[str, Any]], total_wall_seconds: float, out_dir: Path
) -> None:
    alembic_heads = {row.get("alembic_head") for row in rows}
    git_shas = {row.get("git_sha") for row in rows}
    payload = {
        "exp": exp,
        "cells_run": len(rows),
        "alembic_head": next(iter(alembic_heads))
        if len(alembic_heads) == 1
        else sorted(alembic_heads),
        "git_sha": next(iter(git_shas)) if len(git_shas) == 1 else sorted(git_shas),
        "total_wall_seconds": round(total_wall_seconds, 1),
        "per_cell_wall_seconds": {
            f"{row['cell_id']}_s{row['seed']}": row["wall_seconds"] for row in rows
        },
        "harness_version": 1,
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _identity_check(rows: list[dict[str, Any]]) -> list[str]:
    """ADR-017's free validity check: escalation-on at response_rate=0 must
    close referrals at exactly the same rate as escalation-off, for the
    same dropout level and seed. A disagreement means state is leaking
    between cells (ADR-016's whole reason for existing), not a real effect
    — raising an alert nobody acts on cannot close a loop."""
    by_key: dict[tuple[str, int], dict[str, float]] = {}
    for row in rows:
        key = (str(row["dropout_rate"]), row["seed"])
        by_key.setdefault(key, {})
        if not row["escalation_on"]:
            by_key[key]["off"] = row["closure_rate"]
        elif row["response_rate"] == 0.0:
            by_key[key]["on_r0"] = row["closure_rate"]

    failures = []
    for key, pair in sorted(by_key.items()):
        if "off" not in pair or "on_r0" not in pair:
            continue
        if pair["off"] != pair["on_r0"]:
            failures.append(
                f"dropout={key[0]} seed={key[1]}: escalation-off closure_rate={pair['off']} "
                f"!= escalation-on r=0 closure_rate={pair['on_r0']}"
            )
    return failures


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exp", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--seeds", type=str, default=None, help="comma-separated, default: all of grid.SEEDS"
    )
    parser.add_argument("--cell", type=str, default=None, help="run only this cell_id")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--keep-db", action="store_true")
    args = parser.parse_args()

    seeds = [int(s) for s in args.seeds.split(",")] if args.seeds else SEEDS
    cells = cells_for(args.exp)
    if args.cell:
        cells = [c for c in cells if c.cell_id == args.cell]
        if not cells:
            raise SystemExit(f"no cell {args.cell!r} in {args.exp}'s grid")

    plan = [(cell, seed) for cell in cells for seed in seeds]
    print(
        f"{args.exp}: {len(cells)} cells x {len(seeds)} seeds = {len(plan)} runs", file=sys.stderr
    )
    for cell, seed in plan:
        print(f"  {cell.cell_id} seed={seed}", file=sys.stderr)

    if args.dry_run:
        return

    args.out.mkdir(parents=True, exist_ok=True)
    base_database_url = get_settings().database_url
    columns = RAW_COLUMNS_BY_EXP[args.exp]

    started = time.monotonic()
    rows: list[dict[str, Any]] = []
    cell_rows: list[dict[str, Any]] = []  # one entry per (cell, seed) — for manifest wall_seconds
    for cell, seed in plan:
        new_rows = _run_cell_subprocess(base_database_url, args.exp, cell, seed, args.keep_db)
        rows.extend(new_rows)
        cell_rows.append(new_rows[0])
        _write_raw_csv(rows, args.out, columns)  # written after every cell, not just at the end

    total_wall_seconds = time.monotonic() - started
    _write_cells_resolved(args.exp, cells, seeds, args.out)
    _write_manifest(args.exp, cell_rows, total_wall_seconds, args.out)

    if args.exp == "E1":
        failures = _identity_check(rows)
        if failures:
            print("IDENTITY CHECK FAILED (ADR-017's r=0 check):", file=sys.stderr)
            for f in failures:
                print(f"  {f}", file=sys.stderr)
            raise SystemExit(1)
        print(
            "Identity check passed: escalation-on at r=0 matches escalation-off "
            "everywhere it applies.",
            file=sys.stderr,
        )
    print(
        f"{len(rows)} rows written to {args.out / 'raw.csv'} in {total_wall_seconds:.1f}s",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
