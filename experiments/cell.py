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
import uuid
from pathlib import Path
from typing import Any

import yaml

from experiments.grid import (
    E2_LOAD_STEP_HOURS,
    HORIZON_BUFFER_HOURS,
    LOAD_STEP_HOURS,
    SWEEP_STEP_HOURS,
    Cell,
    cells_for,
)

# E3's threshold sweep (docs/PHASE8_PLAN.md "raw.csv columns") — same six
# points scripts/e3_draft_sweep.py uses for the P6.1 draft.
E3_THRESHOLDS = [80, 85, 88, 90, 92, 95]

# Prefixes a cell's own printed row(s) so experiments/runner.py can tell them
# apart from app/instrumentation/logging.py's own structured JSON log lines,
# which land on this same stdout (see main()'s own comment on why "the last
# line" / "any line that parses as JSON" are both wrong).
ROW_MARKER = "CELL_ROW "


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


def _prf(tp: int, predicted_positive: int, actual_positive: int) -> tuple[float, float, float]:
    precision = tp / predicted_positive if predicted_positive else 0.0
    recall = tp / actual_positive if actual_positive else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return precision, recall, f1


async def _run_e2_cell(cell: Cell, seed: int) -> list[dict[str, Any]]:
    """E2: SLA window swept (D37), dropout and response_rate held fixed
    (grid.py's E2_DROPOUT_PCT/E2_RESPONSE_RATE, both confirmed with the
    user). Same load/sweep/resume stepped-clock shape as _run_cell (E1),
    parametrized by cell.sla_window_hours instead of dropout_pct — kept as
    a separate function rather than folded into _run_cell so E1's already
    -verified path is never touched by this session's changes."""
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
    if settings.sla_scale != 1.0:
        raise RuntimeError(
            f"D39: SLA_SCALE must be 1.0 in every experiment process, got {settings.sla_scale}"
        )
    if settings.clock_mode != "simulated":
        raise RuntimeError("experiment cells require CLOCK_MODE=simulated")

    started = time.monotonic()

    _run_migrations()
    await seed_fixture()

    # D37 — applied after seed() runs, before the load loop starts. Uniform,
    # not proportional: every escalatable state takes the same window.
    async with async_session_factory() as s, s.begin():
        await s.execute(
            text("UPDATE sla_profile SET max_hours = :hours"), {"hours": cell.sla_window_hours}
        )

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        config_path = tmp_path / "config.yaml"
        _write_yaml_config(cell.cohort_config(), seed, config_path)
        cohort_dir = tmp_path / "cohort"

        resolved_seed, resolved_config = resolve_config(config_path, seed)
        cohort = generate_cohort(seed, config_path, cohort_dir)
        events = build_events(resolved_seed, resolved_config, cohort)

        reached_closed = {e.referral_id for e in events if e.to_state == "CLOSED"}
        all_referral_ids = [r.referral_id for r in cohort.referrals]
        dropped_ids = {rid for rid in all_referral_ids if rid not in reached_closed}
        referral_by_id = {str(r.referral_id): r for r in cohort.referrals}
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

        async def maybe_sweep_and_resume(client: httpx.AsyncClient) -> None:
            newly = await sweep(async_session_factory, clock)
            if not newly:
                return
            cohort_ids = [rid for rid in newly if str(rid) in referral_by_id]
            if not cohort_ids:
                return
            await resume_escalated_referrals(
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

        transport = ASGITransport(app=fastapi_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://cell") as client:
            elapsed_hours = 0
            while clock.now() <= horizon:
                # E2_LOAD_STEP_HOURS, not the shared LOAD_STEP_HOURS — see
                # grid.py's own comment. E1/E6 tolerate a coarse (168h,
                # weekly) push-batching cadence because neither sweeps the
                # SLA window itself; E2 measured, on this session's own
                # 24h-vs-120h test, byte-identical escalation sets at 168h
                # (push-batching lag exceeded even the widest window, so the
                # window had no chance to matter). A cadence at or below the
                # narrowest swept window (24h) is required for this
                # experiment's x-axis to mean anything.
                if elapsed_hours % E2_LOAD_STEP_HOURS == 0:
                    await load(
                        cohort_dir,
                        upto_device_time=clock.now(),
                        client=client,
                        session_factory=async_session_factory,
                    )
                await maybe_sweep_and_resume(client)
                clock.advance(hours=SWEEP_STEP_HOURS)
                elapsed_hours += SWEEP_STEP_HOURS

            await load(
                cohort_dir,
                upto_device_time=None,
                client=client,
                session_factory=async_session_factory,
            )
            await maybe_sweep_and_resume(client)

            # Same bug-fix as E1's own cell (see _run_cell's own comment) —
            # unconditional, not part of D34's swept assumption.
            await reconcile_natural_continuations(
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
                    text("SELECT referral_id FROM escalation WHERE referral_id = ANY(:ids)"),
                    {"ids": all_referral_ids},
                )
            ).all()

    false_positives = [row for row in escalation_rows if row.referral_id not in dropped_ids]
    total = len(all_referral_ids)

    return [
        {
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
            "sla_window_hours": cell.sla_window_hours,
            "response_rate": cell.response_rate,
            "referrals_total": total,
            "referrals_closed": int(closed_count),
            "closure_rate": (int(closed_count) / total) if total else None,
            "escalations_raised": len(escalation_rows),
            "escalations_per_100_referrals": (
                (len(escalation_rows) / total * 100) if total else None
            ),
            "escalations_false_positive": len(false_positives),
        }
    ]


def _filter_referrals_and_events_csv(cohort_dir: Path, skip_record_ids: set[str]) -> None:
    """Drops every referral belonging to a "query" (second-occurrence
    duplicate) patient record, and every event for it, before load() reads
    the directory — so only "canonical" records ever become real `patient`
    rows, the same asymmetry generator/gold_set.py's own docstring explains
    (a query scored against a candidate set that already contains itself
    would trivially "find itself", which is not how a real referral names
    an incoming patient against rows that already exist)."""
    import csv

    referrals_path = cohort_dir / "referrals.csv"
    with referrals_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        kept_referrals = [row for row in reader if row["patient_record_id"] not in skip_record_ids]
    with referrals_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(kept_referrals)

    kept_referral_ids = {row["referral_id"] for row in kept_referrals}
    events_path = cohort_dir / "events.csv"
    with events_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        kept_events = [row for row in reader if row["referral_id"] in kept_referral_ids]
    with events_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(kept_events)


async def _run_e3_cell(cell: Cell, seed: int) -> list[dict[str, Any]]:
    """E3 at cohort scale: reuses scripts/e3_draft_sweep.py's own approach —
    block()+score() run ONCE per query, classified at six thresholds without
    re-querying — against the real generator cohort's own duplicates
    (generator/cohort.py's Cohort.ground_truth) rather than gold_set.py's
    separate synthetic set (which stays P6.1's own draft). No clock
    stepping and no sweep: identity resolution doesn't depend on either.
    Returns one row per threshold (six), not one row per (cell, seed) —
    docs/PHASE8_PLAN.md's "Cell counts" table already prices this in (1
    cell x 3 seeds = 3 cohort loads, 18 raw.csv rows)."""
    import httpx
    from httpx import ASGITransport
    from sqlalchemy import text

    from app.config import get_settings
    from app.db import async_session_factory
    from app.linkage.blocking import block
    from app.linkage.normalize import normalize
    from app.linkage.scoring import score
    from app.main import app as fastapi_app
    from app.seed import seed as seed_fixture
    from app.verify_replay import verify_all
    from generator.cli import resolve_config
    from generator.cli import run as generate_cohort
    from generator.timeline import build_events
    from scripts.load_cohort import load

    settings = get_settings()
    if settings.sla_scale != 1.0:
        raise RuntimeError(
            f"D39: SLA_SCALE must be 1.0 in every experiment process, got {settings.sla_scale}"
        )
    if settings.clock_mode != "simulated":
        raise RuntimeError("experiment cells require CLOCK_MODE=simulated")

    started = time.monotonic()
    _run_migrations()
    await seed_fixture()

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        config_path = tmp_path / "config.yaml"
        _write_yaml_config(cell.cohort_config(), seed, config_path)
        cohort_dir = tmp_path / "cohort"

        resolved_seed, resolved_config = resolve_config(config_path, seed)
        cohort = generate_cohort(seed, config_path, cohort_dir)
        events = build_events(resolved_seed, resolved_config, cohort)

        query_record_ids = {q["record_id"] for q in cohort.ground_truth.queries}
        _filter_referrals_and_events_csv(cohort_dir, query_record_ids)

        record_id_to_referral_ids: dict[str, list[uuid.UUID]] = {}
        for r in cohort.referrals:
            key = str(r.patient_record_id)
            if key in query_record_ids:
                continue
            record_id_to_referral_ids.setdefault(key, []).append(r.referral_id)

        transport = ASGITransport(app=fastapi_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://cell") as client:
            await load(
                cohort_dir,
                upto_device_time=None,
                client=client,
                session_factory=async_session_factory,
            )

        verify_report = await verify_all()
        if not verify_report.ok:
            raise RuntimeError(
                f"I3 violated inside cell {cell.cell_id}/{seed}: {verify_report.mismatches}"
            )

        kept_referral_ids = [rid for ids in record_id_to_referral_ids.values() for rid in ids]
        patient_by_record_id = {str(p.record_id): p for p in cohort.patients}
        village_org_id = cohort.district.village_org_id

        async with async_session_factory() as session:
            rows = (
                await session.execute(
                    text("SELECT id, patient_id FROM referral WHERE id = ANY(:ids)"),
                    {"ids": kept_referral_ids},
                )
            ).all()
            patient_id_by_referral = {row.id: row.patient_id for row in rows}
            record_id_to_patient_id = {
                record_id: patient_id_by_referral[referral_ids[0]]
                for record_id, referral_ids in record_id_to_referral_ids.items()
            }

            # (blocking_survived, best_candidate_id, best_score, expected_patient_id)
            outcomes: list[tuple[bool, uuid.UUID | None, float, uuid.UUID]] = []
            for q in cohort.ground_truth.queries:
                query_patient = patient_by_record_id[q["record_id"]]
                expected_patient_id = record_id_to_patient_id[q["expected_record_id"]]
                norm = normalize(q["name"])
                candidates = await block(
                    session,
                    village_org_id=village_org_id[q["village_index"]],
                    phone=query_patient.phone,
                )
                scored = [(c.id, score(norm, c.normalized_name)) for c in candidates]
                best_id, best_score = max(scored, key=lambda pair: pair[1], default=(None, 0.0))
                blocking_survived = any(c.id == expected_patient_id for c in candidates)
                outcomes.append((blocking_survived, best_id, best_score, expected_patient_id))

    n = len(outcomes)
    blocking_recall = (sum(1 for o in outcomes if o[0]) / n) if n else 0.0
    auto_resolved = sum(
        1 for o in outcomes if o[1] is not None and o[2] >= settings.identity_auto_accept
    )
    auto_resolution_rate = (auto_resolved / n) if n else 0.0

    # Taxonomy at the OPERATIONAL review floor, not the swept grid — same
    # choice scripts/e3_draft_sweep.py's own _failure_taxonomy makes, and
    # for the same reason: it answers "why does the floor miss this one",
    # independent of which threshold Chapter 4 ends up favouring.
    miss_blocking = miss_scoring = miss_threshold = 0
    for blocking_survived, best_id, best_score, expected_id in outcomes:
        found = best_id == expected_id and best_score >= settings.identity_review_floor
        if found:
            continue
        if not blocking_survived:
            miss_blocking += 1
        elif best_id != expected_id:
            miss_scoring += 1
        else:
            miss_threshold += 1

    common = {
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
        "blocking_recall": blocking_recall,
        "auto_resolution_rate": auto_resolution_rate,
        # Always 0 on this cohort: generator/cohort.py's duplicate names
        # come from NAME_VARIANT_GROUPS, which normalize() already handles
        # cleanly by construction — an honestly empty bucket, not a
        # fabricated one, same as scripts/e3_draft_sweep.py's own draft.
        "miss_normalize": 0,
        "miss_blocking": miss_blocking,
        "miss_scoring": miss_scoring,
        "miss_threshold": miss_threshold,
    }

    result_rows: list[dict[str, Any]] = []
    for t in E3_THRESHOLDS:
        tp = fp = 0
        for _blocking_survived, best_id, best_score, expected_id in outcomes:
            predicted = best_id if (best_id is not None and best_score >= t) else None
            if predicted is None:
                continue
            if predicted == expected_id:
                tp += 1
            else:
                fp += 1
        precision, recall, f1 = _prf(tp, tp + fp, n)
        result_rows.append(
            {**common, "threshold": t, "precision": precision, "recall": recall, "f1": f1}
        )
    return result_rows


async def _run_e6_cell(cell: Cell, seed: int) -> list[dict[str, Any]]:
    """E6: one full-cohort run (grid.py's FULL_COHORT_CONFIG, confirmed with
    the user), escalation on, but NO response modelling — nothing calls
    resume_escalated_referrals, so escalated_unresolved measures exactly
    what the code does with no assumption layered on top (§13.2: "fraction
    the system cannot resolve or close"). reconcile_natural_continuations
    still runs — it is the P8.1 bug fix for a loader artefact, not part of
    ADR-017's swept assumption, and applies whenever a cohort referral gets
    escalated mid-replay, response modelling or not."""
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
    from experiments.resume import reconcile_natural_continuations
    from generator.cli import resolve_config
    from generator.cli import run as generate_cohort
    from generator.timeline import build_events
    from scripts.load_cohort import load

    settings = get_settings()
    if settings.sla_scale != 1.0:
        raise RuntimeError(
            f"D39: SLA_SCALE must be 1.0 in every experiment process, got {settings.sla_scale}"
        )
    if settings.clock_mode != "simulated":
        raise RuntimeError("experiment cells require CLOCK_MODE=simulated")

    started = time.monotonic()
    _run_migrations()
    await seed_fixture()

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        config_path = tmp_path / "config.yaml"
        _write_yaml_config(cell.cohort_config(), seed, config_path)
        cohort_dir = tmp_path / "cohort"

        resolved_seed, resolved_config = resolve_config(config_path, seed)
        cohort = generate_cohort(seed, config_path, cohort_dir)
        events = build_events(resolved_seed, resolved_config, cohort)

        all_referral_ids = [r.referral_id for r in cohort.referrals]
        referral_by_id = {str(r.referral_id): r for r in cohort.referrals}
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
                await sweep(async_session_factory, clock)
                clock.advance(hours=SWEEP_STEP_HOURS)
                elapsed_hours += SWEEP_STEP_HOURS

            await load(
                cohort_dir,
                upto_device_time=None,
                client=client,
                session_factory=async_session_factory,
            )
            await sweep(async_session_factory, clock)

            await reconcile_natural_continuations(
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
            state_counts = (
                await session.execute(
                    text(
                        "SELECT current_state, COUNT(*) AS n FROM referral "
                        "WHERE id = ANY(:ids) GROUP BY current_state"
                    ),
                    {"ids": all_referral_ids},
                )
            ).all()
            pending_reviews = (
                await session.execute(
                    text("SELECT COUNT(*) FROM identity_review WHERE status = 'pending'")
                )
            ).scalar_one()

    by_state = {row.current_state: row.n for row in state_counts}
    total = len(all_referral_ids)
    closed = by_state.get("CLOSED", 0)
    lost = by_state.get("LOST", 0)  # always 0 today — nothing in this codebase writes LOST
    escalated_unresolved = by_state.get("ESCALATED", 0)
    stuck_open = total - closed - lost - escalated_unresolved

    return [
        {
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
            "referrals_total": total,
            "closed": int(closed),
            "lost": int(lost),
            "stuck_open": int(stuck_open),
            "escalated_unresolved": int(escalated_unresolved),
            "unresolvable_fraction": ((total - closed) / total) if total else None,
            "identity_review_pending": int(pending_reviews),
        }
    ]


_CELL_RUNNERS = {"E2": _run_e2_cell, "E3": _run_e3_cell, "E6": _run_e6_cell}


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
    if args.exp == "E1":
        # Untouched since P8.1 — kept as its own path rather than folded
        # into _CELL_RUNNERS's uniform list-of-rows shape, so this session's
        # additions cannot change E1's already-verified output.
        row = asyncio.run(_run_cell(cell, args.seed))
        rows = [row]
    else:
        rows = asyncio.run(_CELL_RUNNERS[args.exp](cell, args.seed))
    for row in rows:
        # app/instrumentation/logging.py's own structured logger also writes
        # JSON lines to this same stdout (every /sync/push, every login) —
        # P8.1's "print exactly one JSON line" only ever worked because that
        # one line came last. E3 prints six, so runner.py can no longer just
        # take "the last line" or "every line that happens to parse as
        # JSON" (it tried the latter first; the app's own request logs are
        # valid JSON too, and made it collect 200+ spurious rows). This
        # prefix is the actual, load-bearing distinguisher.
        print(f"{ROW_MARKER}{json.dumps(row)}", flush=True)


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
