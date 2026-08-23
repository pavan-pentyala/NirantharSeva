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
    dropout_pct: int
    response_rate: float | None  # None when escalation_on is False

    def cohort_config(self) -> dict[str, Any]:
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


CELLS_BY_EXP = {"E1": e1_cells}


def cells_for(exp: str) -> list[Cell]:
    try:
        return CELLS_BY_EXP[exp]()
    except KeyError:
        raise ValueError(f"no cell grid defined for experiment {exp!r}") from None
