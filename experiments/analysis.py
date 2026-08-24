"""Turns a raw.csv into the tables, figures, and a one-page dashboard
Chapter 4 is built from. docs/PHASE8_PLAN.md "The analysis CLI".

Reads ONLY raw.csv from --in — never a database, never cells.resolved.yaml
or manifest.json (those exist for provenance, not as analysis input). This
is what P8.2's own exit criterion actually checks: that raw.csv alone is
sufficient, with every experiment database already dropped.

Invoked as:
    python -m experiments.analysis --exp E1 --in results/e1/ --out results/e1/

Writes, per experiment: table_*.csv (plain aggregates, always regenerable),
figure_*.png (matplotlib, dev-only dependency — server/pyproject.toml's
`dev` group, same place httpx/pytest live), summary.md (a short prose
readout of the headline numbers), and dashboard.html (all of the above on
one page, self-contained except for the PNGs sitting next to it — a
one-experiment-at-a-time page, matching the CLI's own --exp scope, not a
cross-experiment index).

ADR-017 still governs E1: the closure figure/table may show the
escalation-off baseline alongside the modelled response-rate curve (both
are properties of closure), but detection metrics (detection_rate,
mean_hours_to_detection, escalation volume) get their own, separate
table/figure — "measured" and "modelled" are never blended into one figure.
"""

import argparse
import csv
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")  # headless — no display server inside the api container
import matplotlib.pyplot as plt

_STRING_COLUMNS = {"exp", "cell_id", "run_id", "git_sha", "alembic_head"}


def _coerce(key: str, value: str) -> Any:
    if value is None or value == "":
        return None
    if key in _STRING_COLUMNS:
        return value
    if value in ("True", "False"):
        return value == "True"
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def _read_raw(in_dir: Path) -> list[dict[str, Any]]:
    path = in_dir / "raw.csv"
    if not path.exists():
        raise SystemExit(f"no raw.csv in {in_dir} — run experiments.runner first")
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [{k: _coerce(k, v) for k, v in row.items()} for row in reader]


def _mean(values: list[Any]) -> float | None:
    clean = [v for v in values if v is not None]
    return statistics.mean(clean) if clean else None


def _group_mean(
    rows: list[dict[str, Any]], group_keys: list[str], value_keys: list[str]
) -> list[dict[str, Any]]:
    """One row per distinct combination of group_keys, each value_key
    averaged across every raw.csv row sharing that combination (i.e. across
    seeds — 'run every cell at three seeds and report the mean',
    docs/IMPLEMENTATION_PLAN.md §13.2)."""
    groups: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        groups[tuple(r.get(k) for k in group_keys)].append(r)
    result = []
    for key, grouped in sorted(groups.items(), key=lambda kv: [(v is None, v) for v in kv[0]]):
        entry = dict(zip(group_keys, key, strict=True))
        for vk in value_keys:
            entry[vk] = _mean([r.get(vk) for r in grouped])
        entry["n_seeds"] = len(grouped)
        result.append(entry)
    return result


def _write_table(rows: list[dict[str, Any]], columns: list[str], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({c: row.get(c) for c in columns})


def _table_html(rows: list[dict[str, Any]], columns: list[str]) -> str:
    def fmt(v: Any) -> str:
        if v is None:
            return ""
        if isinstance(v, float):
            return f"{v:.3f}"
        return str(v)

    head = "".join(f"<th>{c}</th>" for c in columns)
    body = "".join(
        "<tr>" + "".join(f"<td>{fmt(row.get(c))}</td>" for c in columns) + "</tr>" for row in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


_DASHBOARD_CSS = """
body { font-family: system-ui, sans-serif; margin: 2rem auto; max-width: 960px; color: #1a1a1a; }
h1 { font-size: 1.4rem; } h2 { font-size: 1.1rem; margin-top: 2.5rem; }
table { border-collapse: collapse; margin: 0.75rem 0 1.5rem; font-size: 0.9rem; }
th, td { border: 1px solid #ccc; padding: 0.3rem 0.6rem; text-align: right; }
th:first-child, td:first-child { text-align: left; }
img { max-width: 100%; margin: 0.5rem 0 1.5rem; }
"""


def _write_dashboard(exp: str, sections: list[tuple[str, str, str | None]], out_dir: Path) -> None:
    """sections: (heading, table_html, figure_filename_or_None), in order."""
    body = [f"<h1>{exp} — results</h1>"]
    for heading, table_html, figure in sections:
        body.append(f"<h2>{heading}</h2>")
        if figure:
            body.append(f'<img src="{figure}" alt="{heading}">')
        body.append(table_html)
    html = (
        f"<!doctype html><html><head><meta charset='utf-8'><title>{exp} dashboard</title>"
        f"<style>{_DASHBOARD_CSS}</style></head><body>{''.join(body)}</body></html>\n"
    )
    (out_dir / "dashboard.html").write_text(html, encoding="utf-8")


def _analyze_e1(rows: list[dict[str, Any]], out_dir: Path) -> None:
    closure = _group_mean(
        rows, ["escalation_on", "dropout_rate", "response_rate"], ["closure_rate"]
    )
    closure_cols = ["escalation_on", "dropout_rate", "response_rate", "closure_rate", "n_seeds"]
    _write_table(closure, closure_cols, out_dir / "table_e1_closure.csv")

    detection_rows = [r for r in rows if r.get("escalation_on")]
    detection = _group_mean(
        detection_rows,
        ["dropout_rate"],
        [
            "detection_rate",
            "mean_hours_to_detection",
            "escalations_raised",
            "escalations_false_positive",
            "dropped_total",
        ],
    )
    detection_cols = [
        "dropout_rate",
        "detection_rate",
        "mean_hours_to_detection",
        "escalations_raised",
        "escalations_false_positive",
        "dropped_total",
        "n_seeds",
    ]
    _write_table(detection, detection_cols, out_dir / "table_e1_detection.csv")

    dropouts = sorted({r["dropout_rate"] for r in closure})
    fig, ax = plt.subplots(figsize=(6, 4))
    for d in dropouts:
        on_points = sorted(
            (r["response_rate"], r["closure_rate"])
            for r in closure
            if r["escalation_on"] and r["dropout_rate"] == d and r["response_rate"] is not None
        )
        off = next(
            (
                r["closure_rate"]
                for r in closure
                if not r["escalation_on"] and r["dropout_rate"] == d
            ),
            None,
        )
        if on_points:
            xs, ys = zip(*on_points, strict=True)
            line = ax.plot(xs, ys, marker="o", label=f"dropout={d:.0%}")[0]
            if off is not None:
                ax.axhline(off, color=line.get_color(), linestyle="--", alpha=0.5)
    ax.set_xlabel("escalation_response_rate (modelled assumption)")
    ax.set_ylabel("closure_rate")
    ax.set_title("E1 — loop closure: measured (off, dashed) vs modelled (on, solid)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / "figure_e1_closure.png", dpi=120)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(9, 4))
    xs = [r["dropout_rate"] for r in detection]
    axes[0].bar([f"{x:.0%}" for x in xs], [r["detection_rate"] for r in detection])
    axes[0].set_title("detection_rate by dropout")
    axes[1].bar([f"{x:.0%}" for x in xs], [r["mean_hours_to_detection"] for r in detection])
    axes[1].set_title("mean_hours_to_detection by dropout")
    fig.suptitle("E1 — measured detection (independent of the response-rate assumption)")
    fig.tight_layout()
    fig.savefig(out_dir / "figure_e1_detection.png", dpi=120)
    plt.close(fig)

    _write_dashboard(
        "E1",
        [
            (
                "Closure — measured (escalation off) vs modelled (escalation on, swept r)",
                _table_html(closure, closure_cols),
                "figure_e1_closure.png",
            ),
            (
                "Detection — measured, independent of the response-rate assumption",
                _table_html(detection, detection_cols),
                "figure_e1_detection.png",
            ),
        ],
        out_dir,
    )

    lines = ["# E1 — escalation {on, off} x dropout {10, 25, 40}%\n"]
    lines.append(
        "Closure is reported two ways (ADR-017): the escalation-off arm is a measured\n"
        "closure rate; the escalation-on arm is modelled as a function of an assumed\n"
        "`escalation_response_rate`, swept over {0, 0.25, 0.5, 0.75}. The two are never\n"
        "combined into one number.\n"
    )
    for d in dropouts:
        off = next(
            (
                r["closure_rate"]
                for r in closure
                if not r["escalation_on"] and r["dropout_rate"] == d
            ),
            None,
        )
        if off is not None:
            lines.append(f"\n- dropout={d:.0%}: escalation-off closure_rate={off:.3f}")
    (out_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _analyze_e2(rows: list[dict[str, Any]], out_dir: Path) -> None:
    table = _group_mean(
        rows,
        ["sla_window_hours"],
        [
            "closure_rate",
            "escalations_raised",
            "escalations_per_100_referrals",
            "escalations_false_positive",
        ],
    )
    cols = [
        "sla_window_hours",
        "closure_rate",
        "escalations_raised",
        "escalations_per_100_referrals",
        "escalations_false_positive",
        "n_seeds",
    ]
    _write_table(table, cols, out_dir / "table_e2_frontier.csv")

    xs = [r["sla_window_hours"] for r in table]
    fig, ax1 = plt.subplots(figsize=(6, 4))
    ax1.plot(
        xs, [r["closure_rate"] for r in table], marker="o", color="tab:blue", label="closure_rate"
    )
    ax1.set_xlabel("sla_window_hours")
    ax1.set_ylabel("closure_rate", color="tab:blue")
    ax2 = ax1.twinx()
    ax2.plot(
        xs,
        [r["escalations_per_100_referrals"] for r in table],
        marker="s",
        color="tab:red",
        label="escalations_per_100_referrals",
    )
    ax2.set_ylabel("escalations_per_100_referrals", color="tab:red")
    ax1.set_title("E2 — alert-fatigue frontier (response_rate fixed, see manifest)")
    fig.tight_layout()
    fig.savefig(out_dir / "figure_e2_frontier.png", dpi=120)
    plt.close(fig)

    _write_dashboard(
        "E2",
        [
            (
                "SLA window vs closure and escalation volume",
                _table_html(table, cols),
                "figure_e2_frontier.png",
            )
        ],
        out_dir,
    )
    (out_dir / "summary.md").write_text(
        "# E2 — SLA window {24, 48, 72, 120}h\n\n"
        "Escalation response_rate is held fixed across all four cells (grid.py's own\n"
        "E2_RESPONSE_RATE) so the x-axis means only the SLA window, not a second swept\n"
        "assumption.\n\n" + _markdown_table(table, cols),
        encoding="utf-8",
    )


def _analyze_e3(rows: list[dict[str, Any]], out_dir: Path) -> None:
    thresholds = _group_mean(rows, ["threshold"], ["precision", "recall", "f1"])
    threshold_cols = ["threshold", "precision", "recall", "f1", "n_seeds"]
    _write_table(thresholds, threshold_cols, out_dir / "table_e3_thresholds.csv")

    summary_cols = [
        "blocking_recall",
        "auto_resolution_rate",
        "miss_normalize",
        "miss_blocking",
        "miss_scoring",
        "miss_threshold",
    ]
    summary = [{c: _mean([r.get(c) for r in rows]) for c in summary_cols}]
    summary[0]["n_rows"] = len(rows)
    _write_table(summary, [*summary_cols, "n_rows"], out_dir / "table_e3_summary.csv")

    xs = [r["threshold"] for r in thresholds]
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(xs, [r["precision"] for r in thresholds], marker="o", label="precision")
    ax.plot(xs, [r["recall"] for r in thresholds], marker="s", label="recall")
    ax.plot(xs, [r["f1"] for r in thresholds], marker="^", label="f1")
    ax.set_xlabel("threshold")
    ax.set_title("E3 — precision/recall/F1 vs threshold (cohort scale)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / "figure_e3_prf.png", dpi=120)
    plt.close(fig)

    _write_dashboard(
        "E3",
        [
            (
                "Precision/recall/F1 vs threshold",
                _table_html(thresholds, threshold_cols),
                "figure_e3_prf.png",
            ),
            (
                "Blocking recall, auto-resolution rate, failure taxonomy",
                _table_html(summary, summary_cols),
                None,
            ),
        ],
        out_dir,
    )
    (out_dir / "summary.md").write_text(
        "# E3 — identity resolution threshold sweep, cohort scale\n\n"
        "Reuses scripts/e3_draft_sweep.py's own approach (block()+score() once per\n"
        "query, classified at six thresholds) against the generator cohort's own\n"
        "duplicates, not gold_set.py's separate synthetic set — see experiments/cell.py.\n\n"
        + _markdown_table(summary, summary_cols)
        + "\n"
        + _markdown_table(thresholds, threshold_cols),
        encoding="utf-8",
    )


def _analyze_e6(rows: list[dict[str, Any]], out_dir: Path) -> None:
    cols = [
        "referrals_total",
        "closed",
        "lost",
        "stuck_open",
        "escalated_unresolved",
        "unresolvable_fraction",
        "identity_review_pending",
    ]
    summary = [{c: _mean([r.get(c) for r in rows]) for c in cols}]
    summary[0]["n_seeds"] = len(rows)
    _write_table(summary, [*cols, "n_seeds"], out_dir / "table_e6_summary.csv")

    s = summary[0]
    labels = ["closed", "escalated_unresolved", "stuck_open", "lost"]
    values = [s[label] or 0 for label in labels]
    fig, ax = plt.subplots(figsize=(5, 4))
    ax.bar(labels, values, color=["tab:green", "tab:orange", "tab:gray", "tab:red"])
    ax.set_ylabel("referrals (mean across seeds)")
    ax.set_title("E6 — where full-cohort referrals end up")
    fig.tight_layout()
    fig.savefig(out_dir / "figure_e6_breakdown.png", dpi=120)
    plt.close(fig)

    _write_dashboard(
        "E6",
        [("Full-cohort outcome breakdown", _table_html(summary, cols), "figure_e6_breakdown.png")],
        out_dir,
    )
    (out_dir / "summary.md").write_text(
        "# E6 — full-cohort run\n\n"
        f"unresolvable_fraction = {s['unresolvable_fraction']:.3f} "
        f"(1 - closure_rate; `lost` is always 0 today — nothing in this codebase\n"
        "writes the LOST state, see experiments/cell.py's own comment).\n\n"
        + _markdown_table(summary, cols),
        encoding="utf-8",
    )


def _markdown_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    def fmt(v: Any) -> str:
        if v is None:
            return ""
        return f"{v:.3f}" if isinstance(v, float) else str(v)

    header = "| " + " | ".join(columns) + " |"
    sep = "|" + "|".join(["---"] * len(columns)) + "|"
    body = "\n".join("| " + " | ".join(fmt(row.get(c)) for c in columns) + " |" for row in rows)
    return f"{header}\n{sep}\n{body}\n"


_ANALYZERS = {"E1": _analyze_e1, "E2": _analyze_e2, "E3": _analyze_e3, "E6": _analyze_e6}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exp", required=True, choices=sorted(_ANALYZERS))
    parser.add_argument("--in", dest="in_dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    rows = _read_raw(args.in_dir)
    args.out.mkdir(parents=True, exist_ok=True)
    _ANALYZERS[args.exp](rows, args.out)
    print(f"{args.exp}: {len(rows)} raw.csv rows -> tables/figures/dashboard.html in {args.out}")


if __name__ == "__main__":
    main()
