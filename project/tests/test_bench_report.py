"""
Tests for bench_report.py (Track R2 M0) — pure CSV-summarization / rendering
logic, no subprocess/psutil involved.
"""
from __future__ import annotations

from tools.bench_report import build_report, summarize_telemetry, _render_telemetry_table


def _row(category, label, cpu, rss):
    return {"ts": "0", "category": category, "label": label, "pid": "1", "cpu_pct": str(cpu), "rss_mb": str(rss)}


class TestSummarizeTelemetry:
    def test_groups_by_category_label(self):
        rows = [
            _row("recorder", "m0", 10.0, 100.0),
            _row("recorder", "m0", 20.0, 120.0),
            _row("recorder", "m1", 5.0, 80.0),
        ]
        summary = summarize_telemetry(rows)
        assert set(summary.keys()) == {"recorder/m0", "recorder/m1"}
        assert summary["recorder/m0"]["samples"] == 2
        assert summary["recorder/m0"]["cpu_mean"] == 15.0
        assert summary["recorder/m0"]["cpu_max"] == 20.0
        assert summary["recorder/m0"]["rss_mean_mb"] == 110.0
        assert summary["recorder/m1"]["samples"] == 1

    def test_empty_rows_yields_empty_summary(self):
        assert summarize_telemetry([]) == {}


class TestRenderTelemetryTable:
    def test_empty_summary_renders_placeholder(self):
        out = _render_telemetry_table({})
        assert "no telemetry rows" in out

    def test_nonempty_summary_renders_markdown_table(self):
        out = _render_telemetry_table({"recorder/m0": {
            "samples": 2, "cpu_mean": 15.0, "cpu_max": 20.0, "rss_mean_mb": 110.0, "rss_max_mb": 120.0,
        }})
        assert "| recorder/m0 |" in out
        assert out.startswith("| category/label |")


class TestBuildReport:
    def test_missing_csv_renders_placeholder_instead_of_raising(self, tmp_path):
        # A scenario run shorter than PROC_TELEMETRY_INTERVAL_SECONDS never
        # produces a TELEMETRY_CSV file at all — must not crash the report.
        missing_csv = tmp_path / "never_written.csv"
        report = build_report(missing_csv, None)
        assert "no telemetry rows" in report

    def test_csv_only(self, tmp_path):
        csv_path = tmp_path / "telemetry.csv"
        csv_path.write_text(
            "ts,category,label,pid,cpu_pct,rss_mb\n1,recorder,m0,123,10.0,100.0\n",
            encoding="utf-8",
        )
        report = build_report(csv_path, None)
        assert "## Telemetry" in report
        assert "recorder/m0" in report
        assert "## Scenario events" not in report

    def test_scenario_only(self, tmp_path):
        scenario_path = tmp_path / "results.json"
        scenario_path.write_text(
            '{"pipeline": "auto", "monitors_requested": 2, "segment_duration": 5, '
            '"events": [{"kind": "crash_injected", "ts": 1, "mttr_s": 0.4}]}',
            encoding="utf-8",
        )
        report = build_report(None, scenario_path)
        assert "## Scenario events" in report
        assert "crash_injected" in report
        assert "## Telemetry" not in report
