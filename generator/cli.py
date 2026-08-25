"""§11.1's CLI contract, verbatim. docs/PHASE7_PLAN.md P7.1 build order #5.

    python -m generator.cli --seed 42 --config configs/e1_dropout25.yaml --out data/run_001/

Writes the seven files docs/PHASE7_PLAN.md's contract table names:
patients.csv, district.csv, users.csv, referrals.csv, events.csv,
ground_truth_identity.json, config.resolved.yaml (I7 — the run is
reproducible from --out alone).

No call to the real-time clock anywhere in this module or the ones it
calls (generator/cohort.py, generator/timeline.py) — CI's
clock-discipline grep now covers this directory (build order #8).
"""

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import yaml

from generator.cohort import Cohort, build_cohort
from generator.timeline import EventRow, build_events

DEFAULTS: dict[str, Any] = {
    "n_patients": 200,
    "n_villages": 8,
    "n_ashas": 8,
    "n_facilities": 2,
    "dropout_rate": {
        "CREATED": 0.10,
        "IN_TRANSIT": 0.25,
        "ARRIVED": 0.10,
        "TREATED": 0.05,
        "BACK_REFERRED": 0.05,
    },
    "name_variant_rate": 0.15,
    "duplicate_rate": 0.10,
    "connectivity_profile": "intermittent",
}


def resolve_config(config_path: Path, seed_override: int | None) -> tuple[int, dict[str, Any]]:
    """Deep-merges the YAML file over DEFAULTS (dropout_rate merges
    key-by-key, everything else is a plain override) and decides the seed:
    --seed wins over the file's own `seed:` key, which wins over none."""
    raw: dict[str, Any] = {}
    if config_path.exists():
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        raw = loaded or {}

    resolved: dict[str, Any] = dict(DEFAULTS)
    for key, value in raw.items():
        if key == "seed":
            continue
        if key == "dropout_rate" and isinstance(value, dict):
            resolved["dropout_rate"] = {**DEFAULTS["dropout_rate"], **value}
        else:
            resolved[key] = value

    seed = seed_override if seed_override is not None else raw.get("seed", 42)
    return seed, resolved


def _write_district_csv(cohort: Cohort, out_dir: Path) -> None:
    with (out_dir / "district.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["org_id", "name", "type", "parent_id"])
        for row in cohort.district.org_units:
            writer.writerow([row.org_id, row.name, row.type, row.parent_id or ""])


def _write_users_csv(cohort: Cohort, out_dir: Path) -> None:
    with (out_dir / "users.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["user_id", "name", "role", "org_id"])
        for row in cohort.district.users:
            writer.writerow([row.user_id, row.name, row.role, row.org_id])


def _write_patients_csv(cohort: Cohort, out_dir: Path) -> None:
    village_name = cohort.district.village_name
    with (out_dir / "patients.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["record_id", "person_id", "name", "age", "sex", "phone", "village"])
        for p in cohort.patients:
            writer.writerow(
                [
                    p.record_id,
                    p.person_id,
                    p.name,
                    p.age,
                    p.sex,
                    p.phone or "",
                    village_name[p.village_index],
                ]
            )


def _write_referrals_csv(cohort: Cohort, out_dir: Path) -> None:
    with (out_dir / "referrals.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "referral_id",
                "patient_record_id",
                "origin_user",
                "target_org",
                "reason",
                "priority",
                "created_device_time",
            ]
        )
        for r in cohort.referrals:
            writer.writerow(
                [
                    r.referral_id,
                    r.patient_record_id,
                    r.origin_user,
                    r.target_org,
                    r.reason,
                    r.priority,
                    r.created_device_time.isoformat(),
                ]
            )


def _write_events_csv(events: list[EventRow], out_dir: Path) -> None:
    with (out_dir / "events.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "referral_id",
                "step",
                "from_state",
                "to_state",
                "actor_role",
                "device_time",
                "push_delay_seconds",
            ]
        )
        for e in events:
            writer.writerow(
                [
                    e.referral_id,
                    e.step,
                    e.from_state,
                    e.to_state,
                    e.actor_role,
                    e.device_time.isoformat(),
                    e.push_delay_seconds,
                ]
            )


def _write_ground_truth(cohort: Cohort, out_dir: Path) -> None:
    payload = {
        "seed": cohort.ground_truth.seed,
        "patients": cohort.ground_truth.patients,
        "queries": cohort.ground_truth.queries,
    }
    (out_dir / "ground_truth_identity.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _write_resolved_config(seed: int, config: dict[str, Any], out_dir: Path) -> None:
    payload = {"seed": seed, **config}
    (out_dir / "config.resolved.yaml").write_text(
        yaml.safe_dump(payload, sort_keys=True, default_flow_style=False), encoding="utf-8"
    )


def run(seed: int, config_path: Path, out_dir: Path) -> Cohort:
    resolved_seed, config = resolve_config(config_path, seed)
    cohort = build_cohort(resolved_seed, config)
    events = build_events(resolved_seed, config, cohort)

    out_dir.mkdir(parents=True, exist_ok=True)
    _write_district_csv(cohort, out_dir)
    _write_users_csv(cohort, out_dir)
    _write_patients_csv(cohort, out_dir)
    _write_referrals_csv(cohort, out_dir)
    _write_events_csv(events, out_dir)
    _write_ground_truth(cohort, out_dir)
    _write_resolved_config(resolved_seed, config, out_dir)

    print(
        f"seed={resolved_seed} patients={len(cohort.patients)} "
        f"referrals={len(cohort.referrals)} events={len(events)} "
        f"redraws={cohort.redraws} -> {out_dir}"
    )
    return cohort


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    run(args.seed, args.config, args.out)


if __name__ == "__main__":
    main()
