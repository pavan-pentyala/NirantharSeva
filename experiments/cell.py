"""Child process entry point for one (exp, cell, seed). docs/decisions/
ADR-016.md, ADR-017.md, docs/PHASE8_PLAN.md.

Spawned by experiments/runner.py with DATABASE_URL, CLOCK_MODE=simulated,
SIM_START, RUN_ID, and SLA_SCALE=1.0 already set as env vars *before this
interpreter started* — app.* modules bind to this cell's own database and
its own SimulatedClock singleton at import time (app/db.py, app/clock.py),
which is why a cell needs its own process rather than sharing one with any
other cell (ADR-016's whole reason for existing).

Prints exactly one JSON line to stdout on success: the raw.csv row for this
(cell, seed). Any exception is left to propagate — a nonzero exit and no
printed line is the signal experiments/runner.py treats as a hard failure,
never a silently-missing row.

Invoked as:
    python -m experiments.cell --exp E1 --cell-id on_d25_r050 --seed 42
"""

import argparse
import asyncio
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import yaml

from experiments.grid import (
    HORIZON_BUFFER_HOURS,
    LOAD_STEP_HOURS,
    SWEEP_STEP_HOURS,
    Cell,
    cells_for,
)


def _run_migrations() -> None:
    """Shells out to the real alembic CLI, the same command every other
    entry point in this repo uses — not the Python API, and not run from
    experiments/runner.py, since each cell's own fresh database needs its
    own migration pass."""
    subprocess.run(["alembic", "upgrade", "head"], cwd="/app", check=True)


def _find_cell(exp: str, cell_id: str) -> Cell:
    for cell in cells_for(exp):
        if cell.cell_id == cell_id:
            return cell
    raise ValueError(f"unknown cell {cell_id!r} for experiment {exp!r}")


def _write_yaml_config(config: dict[str, Any], seed: int, path: Path) -> None:
    payload = {"seed": seed, **config}
    path.write_text(yaml.safe_dump(payload, sort_keys=True), encoding="utf-8")


async def _run_cell(cell: Cell, seed: int) -> dict[str, Any]:
    # Imported only now, inside the child process, after DATABASE_URL /
    # CLOCK_MODE / SIM_START / SLA_SCALE are already set — see module
    # docstring. Importing any app.* module earlier (e.g. at parent import
    # time) would bind the wrong database (ADR-016).
    from datetime import timedelta

    import httpx
    from httpx import ASGITransport
    from sqlalchemy import text

    from app.clock import get_clock
    from app.config import get_settings
    from app.db import async_session_factory
    from app.domain.escalation import sweep
    from app.main import app as fastapi_app
    from app.seed import seed as seed_fixture
    from app.verify_replay import verify_all
    from experiments.resume import reconcile_natural_continuations, resume_escalated_referrals
    from generator.cli import resolve_config
    from generator.cli import run as generate_cohort
    from generator.timeline import build_events
    from scripts.load_cohort import load

    settings = get_settings()
    # D39 — asserted, not trusted: a fractional SLA_SCALE that silently
    # truncated to something other than 1.0 (observation 37's failure mode)
    # would make E2's window axis and E1's time-to-detection mean nothing.
    if settings.sla_scale != 1.0:
        raise RuntimeError(
            f"D39: SLA_SCALE must be 1.0 in every experiment process, got {settings.sla_scale}"
        )
    if settings.clock_mode != "simulated":
        raise RuntimeError("experiment cells require CLOCK_MODE=simulated")

    started = time.monotonic()

    _run_migrations()
    await seed_fixture()  # sla_profile rows — nothing escalates without them

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        config_path = tmp_path / "config.yaml"
        _write_yaml_config(cell.cohort_config(), seed, config_path)
        cohort_dir = tmp_path / "cohort"

        resolved_seed, resolved_config = resolve_config(config_path, seed)
        cohort = generate_cohort(seed, config_path, cohort_dir)
        events = build_events(resolved_seed, resolved_config, cohort)

        # Ground truth from the generator itself (no DB query needed): a
        # referral "dropped" iff its walk never reached CLOSED — including
        # zero events at all (dropped at CREATED). generator/timeline.py
        # never emits ESCALATED, so this is unambiguous.
        reached_closed = {e.referral_id for e in events if e.to_state == "CLOSED"}
        all_referral_ids = [r.referral_id for r in cohort.referrals]
        dropped_ids = {rid for rid in all_referral_ids if rid not in reached_closed}
        referral_by_id = {str(r.referral_id): r for r in cohort.referrals}

        # generator/timeline.py's build_events walks one referral's whole
        # sequence (step 1, 2, 3, ...) before moving to the next, so each
        # bucket below already comes out in ascending step order — no
        # secondary sort needed.
        events_by_referral: dict[str, list] = {}
        for e in events:
            events_by_referral.setdefault(str(e.referral_id), []).append(e)

        clock = get_clock()
        earliest = min(r.created_device_time for r in cohort.referrals)
        if clock.now() > earliest:
            raise RuntimeError(
                f"SIM_START ({clock.now()}) is after the cohort's earliest "
                f"referral ({earliest}) — the clock must start at or before it"
            )
        latest_event_time = max((e.device_time for e in events), default=earliest)
        horizon = max(latest_event_time, earliest) + timedelta(hours=HORIZON_BUFFER_HOURS)

        resumed_count = 0
        resumed_and_closed = 0

        async def maybe_sweep_and_resume(client: httpx.AsyncClient) -> None:
            nonlocal resumed_count, resumed_and_closed
            if not cell.escalation_on:
                return
            newly = await sweep(async_session_factory, clock)
            if not (newly and cell.response_rate):
                return
            # sweep() scans EVERY open referral in this cell's database,
            # not just the generated cohort — app/seed.py's own D4 fixture
            # (called above for its sla_profile rows) also writes two
            # referrals, and they breach their SLA over the same simulated
            # horizon like anything else left unattended. They have no
            # entry in referral_by_id (built from cohort.referrals alone),
            # so they must be filtered out here before any lookup into it
            # — found by running a resume-enabled cell for real, not by
            # reasoning about what sweep() returns.
            cohort_ids = [rid for rid in newly if str(rid) in referral_by_id]
            if not cohort_ids:
                return
            outcome = await resume_escalated_referrals(
                client=client,
                session_factory=async_session_factory,
                clock=clock,
                cell_seed=seed,
                cell_id=cell.cell_id,
                response_rate=cell.response_rate,
                escalated_referral_ids=cohort_ids,
                referral_by_id=referral_by_id,
                district=cohort.district,
            )
            resumed_count += outcome.resumed_count
            resumed_and_closed += outcome.resumed_and_closed_count

        transport = ASGITransport(app=fastapi_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://cell") as client:
            elapsed_hours = 0
            while clock.now() <= horizon:
                if elapsed_hours % LOAD_STEP_HOURS == 0:
                    await load(
                        cohort_dir,
                        upto_device_time=clock.now(),
                        client=client,
                        session_factory=async_session_factory,
                    )
                await maybe_sweep_and_resume(client)
                clock.advance(hours=SWEEP_STEP_HOURS)
                elapsed_hours += SWEEP_STEP_HOURS

            # Final catch-up: everything the cohort ever generates, no
            # cutoff, then one last sweep — the loop above stops at
            # `horizon`, which is built with a buffer past the latest
            # generated event, but the very last sweep still needs to run
            # *after* that final load.
            await load(
                cohort_dir,
                upto_device_time=None,
                client=client,
                session_factory=async_session_factory,
            )
            await maybe_sweep_and_resume(client)

            # Escalation flags a referral; it does not stop the ASHA/MO
            # doing the work she was always going to do. Run once, after
            # the horizon's final sweep, for every referral still
            # ESCALATED with more of its own generated walk left — see
            # experiments/resume.py's reconcile_natural_continuations for
            # why this is unconditional (no response_rate draw) and
            # separate from ADR-017's resume above. Found via the r=0
            # identity check itself: every escalation-on cell was closing
            # roughly half of what escalation-off closed, at every dropout
            # level and seed, before this existed.
            reconciled_count = await reconcile_natural_continuations(
                client=client,
                session_factory=async_session_factory,
                cell_seed=seed,
                cell_id=cell.cell_id,
                cohort_referral_ids=all_referral_ids,
                events_by_referral=events_by_referral,
                referral_by_id=referral_by_id,
                district=cohort.district,
            )

        verify_report = await verify_all()
        if not verify_report.ok:
            raise RuntimeError(
                f"I3 violated inside cell {cell.cell_id}/{seed}: {verify_report.mismatches}"
            )

        async with async_session_factory() as session:
            closed_count = (
                await session.execute(
                    text(
                        "SELECT COUNT(*) FROM referral "
                        "WHERE id = ANY(:ids) AND current_state = 'CLOSED'"
                    ),
                    {"ids": all_referral_ids},
                )
            ).scalar_one()

            escalation_rows = (
                await session.execute(
                    text(
                        """
                        SELECT e.referral_id, e.triggered_at, e.breached_state,
                               (SELECT MAX(re.server_time) FROM referral_event re
                                WHERE re.referral_id = e.referral_id
                                  AND re.to_state = e.breached_state
                                  AND re.server_time <= e.triggered_at) AS entered_at
                        FROM escalation e
                        WHERE e.referral_id = ANY(:ids)
                        """
                    ),
                    {"ids": all_referral_ids},
                )
            ).all()

    escalated_ids = {row.referral_id for row in escalation_rows}
    detected_dropped = escalated_ids & dropped_ids
    false_positives = [row for row in escalation_rows if row.referral_id not in dropped_ids]
    hours_to_detection = [
        (row.triggered_at - row.entered_at).total_seconds() / 3600
        for row in escalation_rows
        if row.entered_at is not None and row.referral_id in dropped_ids
    ]

    return {
        "exp": cell.exp,
        "cell_id": cell.cell_id,
        "seed": seed,
        "run_id": f"{cell.exp.lower()}_{cell.cell_id}_s{seed}",
        "wall_seconds": round(time.monotonic() - started, 3),
        "cohort_patients": len(cohort.patients),
        "cohort_referrals": len(cohort.referrals),
        "cohort_events": len(events),
        "git_sha": _git_sha(),
        "alembic_head": _alembic_head(),
        "escalation_on": cell.escalation_on,
        "dropout_rate": cell.dropout_pct / 100,
        "response_rate": cell.response_rate,
        "referrals_total": len(all_referral_ids),
        "referrals_closed": int(closed_count),
        "closure_rate": (int(closed_count) / len(all_referral_ids)) if all_referral_ids else None,
        "dropped_total": len(dropped_ids),
        "escalations_raised": len(escalation_rows),
        "escalations_true_positive": len(escalation_rows) - len(false_positives),
        "escalations_false_positive": len(false_positives),
        "dropped_detected": len(detected_dropped),
        "detection_rate": (len(detected_dropped) / len(dropped_ids)) if dropped_ids else None,
        "mean_hours_to_detection": (
            sum(hours_to_detection) / len(hours_to_detection) if hours_to_detection else None
        ),
        "resumed_count": resumed_count,
        "resumed_and_closed": resumed_and_closed,
        "reconciled_count": reconciled_count,
    }


def _git_sha() -> str:
    """Best-effort provenance only — .git isn't mounted into the api
    container (docker-compose.yml mounts server/, generator/, experiments/,
    configs/, data/, none of them the repo root), so `git` may not even be
    on PATH here. Never worth failing a whole cell over."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd="/app", capture_output=True, text=True, check=False
        )
    except OSError:
        return "unknown"
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _alembic_head() -> str:
    result = subprocess.run(
        ["alembic", "heads"], cwd="/app", capture_output=True, text=True, check=True
    )
    return result.stdout.strip().split()[0] if result.stdout.strip() else "unknown"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exp", required=True)
    parser.add_argument("--cell-id", required=True)
    parser.add_argument("--seed", type=int, required=True)
    args = parser.parse_args()

    cell = _find_cell(args.exp, args.cell_id)
    row = asyncio.run(_run_cell(cell, args.seed))
    print(json.dumps(row), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 -- deliberate: print to stderr, exit nonzero, no JSON line
        response = getattr(exc, "response", None)
        if response is not None:
            print(f"cell failed: {exc} -- response body: {response.text}", file=sys.stderr)
        else:
            print(f"cell failed: {exc}", file=sys.stderr)
        raise
