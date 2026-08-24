"""Experiment cell definitions. docs/PHASE8_PLAN.md, ADR-016, ADR-017.

Pure: builds plain, serializable Cell objects. No I/O, no database, no
clock — the same discipline generator/cohort.py holds itself to, for the
same reason (a cell's shape must be reproducible from (exp, cell_id, seed)
alone — I7).
"""

import itertools
from dataclasses import dataclass
from typing import Any

# Same base as configs/e1_dropout25.yaml, minus IN_TRANSIT — E1 sweeps that
# one stage's dropout_rate per cell (the config file's own comment: "E1's
# headline cell... IN_TRANSIT's dropout_rate is the one that matters").
_BASE_DROPOUT_RATE: dict[str, float] = {
    "CREATED": 0.10,
    "ARRIVED": 0.10,
    "TREATED": 0.05,
    "BACK_REFERRED": 0.05,
}

# Deliberately smaller than P7.1's demo-scale default (n_patients=200) —
# D31 sized that default for one cohort load's realism; Phase 8 needs ~60
# (cell, seed) pairs to finish in a working session, and each pair repeats
# the load in the stepped-clock loop below (ADR-016's "makes hard" cost).
# Called out here, and in PROGRESS.md, as a wall-clock call taken alone
# under handoff §2 — correctness of any cell does not depend on cohort
# size, only the statistical noise floor on rates computed from it does.
BASE_CONFIG: dict[str, Any] = {
    "n_patients": 20,
    "n_villages": 2,
    "n_ashas": 2,
    "n_facilities": 1,
    "name_variant_rate": 0.15,
    "duplicate_rate": 0.10,
    "connectivity_profile": "intermittent",
}

# Must match generator/cohort.py's own _BASE_TIME — every cohort's
# referrals are offset forward from that same constant regardless of seed.
# experiments/runner.py sets SIM_START to this for every cell's child
# process, and experiments/cell.py asserts the clock starts at or before
# the cohort's own earliest referral.
SIM_START = "2026-01-01T00:00:00+00:00"

DROPOUT_PCTS: list[int] = [10, 25, 40]
RESPONSE_RATES: list[float] = [0.0, 0.25, 0.5, 0.75]  # ADR-017 (D34)
SEEDS: list[int] = [42, 7, 13]

# E2 (§13.2: "SLA window {24, 48, 72, 120}h"). D37: every sla_profile row's
# max_hours is overridden uniformly to the cell's own window value, so the
# x-axis means exactly one thing. Escalation needs SOME response assumption
# to move closure at all (ADR-017's own reasoning) — since E2 sweeps the SLA
# window, not the response rate, one fixed rate applies to all 4 cells,
# rather than a second 4x multiplier on top (the "Cell counts" table fixes
# E2 at 4 cells x 3 seeds = 12 loads, not 16). 0.5 and a fixed dropout of 25%
# (matching configs/e1_dropout25.yaml's own default) were both confirmed with
# the user before this file was written, per handoff's "changes the
# experiments" rule — not decided alone.
SLA_WINDOW_HOURS: list[int] = [24, 48, 72, 120]
E2_RESPONSE_RATE = 0.5
E2_DROPOUT_PCT = 25
# E1's LOAD_STEP_HOURS=168 (weekly) is coarser than every window E2 sweeps
# (24-120h) — a referral's push-batching lag alone can exceed the window
# being tested, before the window itself ever gets a chance to matter.
# Measured directly (this session, not assumed): at 168, the 24h and 120h
# cells produced BYTE-IDENTICAL escalation sets (same referral_ids, same
# breached_state) — proof the window had zero effect. 12h keeps the lag
# under the smallest swept window.
E2_LOAD_STEP_HOURS = 12

# E6 ("full-cohort run", §13.2) deliberately uses the SAME cohort scale as
# P7.1's own default (generator/cli.py's DEFAULTS, configs/e1_dropout25.yaml)
# rather than E1/E2/E3's shrunk BASE_CONFIG — confirmed with the user, since
# it changes E6's wall-clock cost materially and is a genuine experiment
# parameter, not an implementation detail. E6 measures the unresolvable
# fraction at realistic scale; the smaller grid cohort would make it mostly
# restate E1's own off-cells under a different label.
FULL_COHORT_CONFIG: dict[str, Any] = {
    "n_patients": 200,
    "n_villages": 8,
    "n_ashas": 8,
    "n_facilities": 2,
    "name_variant_rate": 0.15,
    "duplicate_rate": 0.10,
    "connectivity_profile": "intermittent",
}
# Same per-stage shape as configs/e1_dropout25.yaml / generator/cli.py's own
# DEFAULTS — E6 is not sweeping dropout, it just needs a realistic cohort.
_DEFAULT_DROPOUT_RATE: dict[str, float] = {
    "CREATED": 0.10,
    "IN_TRANSIT": 0.25,
    "ARRIVED": 0.10,
    "TREATED": 0.05,
    "BACK_REFERRED": 0.05,
}

# generator/cohort.py::build_referrals spreads created_device_time over
# 0-300 simulated days, hardcoded and not config-driven — frozen code
# (§13's "the code is frozen except for bug fixes"), so the stepped loop
# has to live with that spread rather than shrink it. load() has no
# "already sent" cursor (server/scripts/load_cohort.py's own docstring)
# and re-walks every referral row on every call, so its cost is driven by
# how many times it is called, not by simulated duration — sweep()'s cost,
# by contrast, is driven only by how many referrals are currently open and
# breached, so it can run on its own, finer cadence for cheap.
#
# LOAD_STEP_HOURS is not just a throughput knob: app/sync/push.py sets
# referral.state_entered_at from the injected Clock's *current* value at
# push time, not from the op's own device_time — correct for the real
# system (a referral's SLA clock starts when the server learns about it,
# same reasoning as D33's push_delay_seconds), but it means batching pushes
# this coarsely adds up to LOAD_STEP_HOURS of state_entered_at lag beyond
# what the cohort's own connectivity_profile models. That lag does not
# bias detection_rate (a breach is still eventually found, however late,
# as long as the horizon has room) but does add a roughly uniform bias to
# the absolute mean_hours_to_detection figure — comparable across cells
# since every cell uses the same LOAD_STEP_HOURS, not comparable to a
# real deployment's actual latency. Documented here and in
# docs/PHASE8_PLAN.md rather than quietly absorbed into the number.
#
# The value matters more than it looks: load() has no "already sent"
# cursor, so its cost across N checkpoints grows like N(N+1)/2, not N —
# halving LOAD_STEP_HOURS roughly QUADRUPLES total push volume. Measured
# directly (P8.1, not assumed — the same discipline D31 required of the
# generator's own load time): one off_d25 cell at LOAD_STEP_HOURS=24 took
# 590s. At 168 (weekly) the same cell took well under a minute — see
# docs/PHASE8_PLAN.md's measured-budget note. Weekly batching means up to
# 7 days of state_entered_at lag, materially more than any single
# connectivity_profile delay bucket models — accepted deliberately here,
# in the week before Review-II, so a full E1 run finishes in a session
# rather than overnight; the bias this adds to the absolute
# mean_hours_to_detection figure is called out wherever that figure is
# reported, not silently absorbed into it.
LOAD_STEP_HOURS = 168  # weekly — bounds load()'s redundant-resend cost
SWEEP_STEP_HOURS = 12  # resolves the shortest seeded SLA window (24h)
HORIZON_BUFFER_HOURS = 336  # two weeks past the last generated referral


@dataclass(frozen=True)
class Cell:
    exp: str
    cell_id: str
    escalation_on: bool
    dropout_pct: int | None = None
    response_rate: float | None = None  # None when escalation_on is False
    sla_window_hours: int | None = None  # E2 only

    def cohort_config(self) -> dict[str, Any]:
        if self.exp == "E6":
            return {**FULL_COHORT_CONFIG, "dropout_rate": dict(_DEFAULT_DROPOUT_RATE)}
        if self.exp == "E3":
            return {**BASE_CONFIG, "dropout_rate": dict(_DEFAULT_DROPOUT_RATE)}
        dropout = dict(_BASE_DROPOUT_RATE)
        dropout["IN_TRANSIT"] = self.dropout_pct / 100
        return {**BASE_CONFIG, "dropout_rate": dropout}

    def as_dict(self) -> dict[str, Any]:
        return {
            "exp": self.exp,
            "cell_id": self.cell_id,
            "escalation_on": self.escalation_on,
            "dropout_pct": self.dropout_pct,
            "response_rate": self.response_rate,
            "sla_window_hours": self.sla_window_hours,
        }


def _label(rate: float) -> str:
    return str(rate).replace(".", "")


def e1_cells() -> list[Cell]:
    """15 cells (D34/ADR-017): 3 escalation-off (one per dropout level) +
    3 dropout levels x 4 response rates escalation-on."""
    cells: list[Cell] = []
    for pct in DROPOUT_PCTS:
        cells.append(
            Cell(
                exp="E1",
                cell_id=f"off_d{pct}",
                escalation_on=False,
                dropout_pct=pct,
                response_rate=None,
            )
        )
    for pct, rate in itertools.product(DROPOUT_PCTS, RESPONSE_RATES):
        cells.append(
            Cell(
                exp="E1",
                cell_id=f"on_d{pct}_r{_label(rate)}",
                escalation_on=True,
                dropout_pct=pct,
                response_rate=rate,
            )
        )
    return cells


def e2_cells() -> list[Cell]:
    """4 cells (D37): SLA window swept, dropout and response_rate held fixed
    (E2_DROPOUT_PCT, E2_RESPONSE_RATE — both confirmed with the user)."""
    return [
        Cell(
            exp="E2",
            cell_id=f"sla{hours}",
            escalation_on=True,
            dropout_pct=E2_DROPOUT_PCT,
            response_rate=E2_RESPONSE_RATE,
            sla_window_hours=hours,
        )
        for hours in SLA_WINDOW_HOURS
    ]


def e3_cells() -> list[Cell]:
    """1 cell: identity resolution doesn't depend on escalation or dropout —
    scored offline at six thresholds from one cohort load per seed."""
    return [Cell(exp="E3", cell_id="thresholds", escalation_on=False)]


def e6_cells() -> list[Cell]:
    """1 cell: one full-cohort run (FULL_COHORT_CONFIG), escalation on with
    no response modelling — reconcile_natural_continuations still runs (it's
    a correctness fix, not part of ADR-017's swept assumption), but nothing
    calls resume_escalated_referrals."""
    return [Cell(exp="E6", cell_id="full_cohort", escalation_on=True)]


CELLS_BY_EXP = {"E1": e1_cells, "E2": e2_cells, "E3": e3_cells, "E6": e6_cells}


def cells_for(exp: str) -> list[Cell]:
    try:
        return CELLS_BY_EXP[exp]()
    except KeyError:
        raise ValueError(f"no cell grid defined for experiment {exp!r}") from None
