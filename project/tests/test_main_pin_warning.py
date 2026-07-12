"""Weak IT_PIN startup warning — visibility only, not a behavior change.

Removing the "1234" default outright would make unlock_it() compare against
None forever (a silent, permanent lockout); that tradeoff is deferred pending
an explicit decision (see TODOS.md). This only covers the loud startup warning.
"""
from __future__ import annotations

from types import SimpleNamespace

from loguru import logger

from app.main import _warn_if_default_it_pin


def _capture_warnings():
    records: list[str] = []
    sink_id = logger.add(lambda msg: records.append(msg.record["message"]), level="WARNING")
    return records, sink_id


def test_warns_when_pin_is_still_default() -> None:
    records, sink_id = _capture_warnings()
    try:
        _warn_if_default_it_pin(SimpleNamespace(it_pin="1234"))
    finally:
        logger.remove(sink_id)
    assert any("IT_PIN" in r for r in records)


def test_no_warning_when_pin_was_changed() -> None:
    records, sink_id = _capture_warnings()
    try:
        _warn_if_default_it_pin(SimpleNamespace(it_pin="8420"))
    finally:
        logger.remove(sink_id)
    assert records == []
