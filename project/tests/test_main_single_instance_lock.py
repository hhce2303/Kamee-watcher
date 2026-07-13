"""Single-instance mutex contention handling.

Root cause of "IT backend doesn't start, no trace in watcher.log": the
non-operator contention path used to retry, try a Tkinter dialog, and exit —
all before configure_logging() had run (that reorder is fixed in main(); see
its docstring comment). This covers what stayed inside
_acquire_single_instance_lock itself: the CRITICAL line always lands before
any exit, and a dialog that can't render degrades to a WARNING instead of
crashing silently or disappearing without a trace.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from loguru import logger

from app.main import _acquire_single_instance_lock


def _capture(level: str):
    records: list[str] = []
    sink_id = logger.add(lambda msg: records.append(msg.record["message"]), level=level)
    return records, sink_id


def _mock_contended_kernel32(monkeypatch: pytest.MonkeyPatch) -> None:
    """Simulate CreateMutexW always reporting ERROR_ALREADY_EXISTS, and make
    the 3s retry loop break after exactly one attempt (no real sleep)."""
    fake_kernel32 = MagicMock()
    fake_kernel32.CreateMutexW.return_value = 1
    fake_kernel32.GetLastError.return_value = 183  # ERROR_ALREADY_EXISTS
    monkeypatch.setattr("ctypes.windll.kernel32", fake_kernel32)
    # First call establishes the deadline; second call (the loop's own check)
    # already exceeds it, so the loop breaks after one attempt, no sleep.
    monkeypatch.setattr("app.main.time.monotonic", MagicMock(side_effect=[100.0, 200.0]))


def test_operator_silent_exits_zero_with_no_dialog(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_contended_kernel32(monkeypatch)
    tk_mock = MagicMock()
    monkeypatch.setattr("tkinter.Tk", tk_mock)

    records, sink_id = _capture("INFO")
    try:
        with pytest.raises(SystemExit) as exc_info:
            _acquire_single_instance_lock(operator_silent=True)
        assert exc_info.value.code == 0
    finally:
        logger.remove(sink_id)

    assert any("exiting quietly" in r for r in records)
    tk_mock.assert_not_called()


def test_non_operator_logs_critical_before_exiting_one(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_contended_kernel32(monkeypatch)
    monkeypatch.setattr("tkinter.Tk", MagicMock())
    monkeypatch.setattr("tkinter.messagebox.showerror", MagicMock())

    records, sink_id = _capture("CRITICAL")
    try:
        with pytest.raises(SystemExit) as exc_info:
            _acquire_single_instance_lock(operator_silent=False)
        assert exc_info.value.code == 1
    finally:
        logger.remove(sink_id)

    assert any("already running" in r for r in records)


def test_dialog_failure_degrades_to_warning_not_a_crash(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_contended_kernel32(monkeypatch)
    monkeypatch.setattr("tkinter.Tk", MagicMock(side_effect=RuntimeError("no display")))

    records, sink_id = _capture("WARNING")
    try:
        with pytest.raises(SystemExit) as exc_info:
            _acquire_single_instance_lock(operator_silent=False)
        assert exc_info.value.code == 1
    finally:
        logger.remove(sink_id)

    assert any("Could not show" in r for r in records)
