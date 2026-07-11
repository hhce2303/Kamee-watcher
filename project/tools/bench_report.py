"""
bench_report.py — Track R2 M0 report formatter.

Reads a TELEMETRY_CSV file (proc_telemetry.py) and/or a bench_scenario.py
``run`` JSON summary and prints a markdown report: per-category/label CPU/RSS
stats, thread count for the parent process, and event MTTRs (crash/stall) and
orphan counts pulled straight from the scenario JSON.

Usage::

    python -m tools.bench_report --csv telemetry.csv --scenario results.json
    python -m tools.bench_report --csv telemetry.csv   # telemetry table only
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path


def _load_csv_rows(csv_path: Path) -> list[dict]:
    if not csv_path.exists():
        # A run shorter than PROC_TELEMETRY_INTERVAL_SECONDS (default 10s) never
        # fires a single sample, so TELEMETRY_CSV is never created — not an error.
        return []
    with open(csv_path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def summarize_telemetry(rows: list[dict]) -> dict:
    """Group CSV rows by (category, label) → {cpu_mean, cpu_max, rss_mean, rss_max, samples}."""
    groups: dict[tuple[str, str], dict[str, list[float]]] = defaultdict(lambda: {"cpu": [], "rss": []})
    for row in rows:
        key = (row["category"], row["label"])
        groups[key]["cpu"].append(float(row["cpu_pct"]))
        groups[key]["rss"].append(float(row["rss_mb"]))

    summary = {}
    for (category, label), vals in groups.items():
        summary[f"{category}/{label}"] = {
            "samples": len(vals["cpu"]),
            "cpu_mean": round(statistics.mean(vals["cpu"]), 2) if vals["cpu"] else None,
            "cpu_max": round(max(vals["cpu"]), 2) if vals["cpu"] else None,
            "rss_mean_mb": round(statistics.mean(vals["rss"]), 1) if vals["rss"] else None,
            "rss_max_mb": round(max(vals["rss"]), 1) if vals["rss"] else None,
        }
    return summary


def _render_telemetry_table(summary: dict) -> str:
    if not summary:
        return "_(no telemetry rows - TELEMETRY_CSV empty or not set)_\n"
    lines = [
        "| category/label | samples | CPU mean % | CPU max % | RSS mean MB | RSS max MB |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for key, s in sorted(summary.items()):
        lines.append(
            f"| {key} | {s['samples']} | {s['cpu_mean']} | {s['cpu_max']} | "
            f"{s['rss_mean_mb']} | {s['rss_max_mb']} |"
        )
    return "\n".join(lines) + "\n"


def _render_scenario_section(scenario: dict) -> str:
    lines = [
        f"**Pipeline:** `{scenario.get('pipeline')}`  ",
        f"**Monitors requested:** {scenario.get('monitors_requested')}  ",
        f"**Segment duration:** {scenario.get('segment_duration')}s",
        "",
        "| event | detail |",
        "|---|---|",
    ]
    for ev in scenario.get("events", []):
        kind = ev.pop("kind")
        ev.pop("ts", None)
        lines.append(f"| {kind} | {ev} |")
    return "\n".join(lines) + "\n"


def build_report(csv_path: "Path | None", scenario_path: "Path | None") -> str:
    sections = ["# Track R2 bench report", ""]
    if csv_path is not None:
        rows = _load_csv_rows(csv_path)
        sections.append("## Telemetry (proc_telemetry CSV)")
        sections.append(_render_telemetry_table(summarize_telemetry(rows)))
    if scenario_path is not None:
        scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
        sections.append("## Scenario events")
        sections.append(_render_scenario_section(scenario))
    return "\n".join(sections)


def main() -> None:
    parser = argparse.ArgumentParser(description="Track R2 M0 bench report formatter")
    parser.add_argument("--csv", type=Path, default=None, help="TELEMETRY_CSV path")
    parser.add_argument("--scenario", type=Path, default=None, help="bench_scenario.py run JSON output")
    parser.add_argument("--out", type=Path, default=None, help="write report here (default: stdout)")
    args = parser.parse_args()

    if args.csv is None and args.scenario is None:
        print("error: pass at least one of --csv / --scenario", file=sys.stderr)
        sys.exit(2)

    report = build_report(args.csv, args.scenario)
    if args.out is not None:
        args.out.write_text(report, encoding="utf-8")
        print(f"[bench_report] wrote {args.out}")
    else:
        print(report)


if __name__ == "__main__":
    main()
