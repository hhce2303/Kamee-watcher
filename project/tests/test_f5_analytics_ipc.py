"""Fase 5 — Analytics IPC commands (E2E router layer).

Coverage:
  TestAnalyticsCommandsNoAdapter   — router returns empty lists when analytics=None
  TestAnalyticsCommandsWithAdapter — analytics_counts / dwell / zone_events via mock
  TestAnalyticsIpcWiring           — build_api_layer wires analytics_query correctly
  TestAnalyticsFilters             — monitor_index filter forwarded; zone_events filter
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional
from unittest.mock import MagicMock

import pytest

from app.adapters.ipc.router import IpcRouter
from app.adapters.storage.sqlite_analytics import SqliteAnalyticsAdapter
from app.adapters.storage.sqlite_event_store import SqliteEventStoreAdapter
from app.core.analytics.models import AnalyticEvent
from app.core.api.bootstrap import ApiLayer, build_api_layer
from app.core.ports.analytics_query_port import (
    AnalyticsQueryPort,
    CountByClass,
    DwellRecord,
)
from app.core.recording_service.models import MonitorInfo

# ── shared fixtures ───────────────────────────────────────────────────────────

_NOW = datetime(2026, 7, 5, 12, 0, 0, tzinfo=timezone.utc)
_SINCE = _NOW - timedelta(hours=1)
_UNTIL = _NOW


def _since_s() -> str:
    return _SINCE.isoformat()


def _until_s() -> str:
    return _UNTIL.isoformat()


def _event(
    eid: str = "e1",
    type_: str = "person",
    zone: str | None = None,
    track_id: int | None = 1,
    monitor_index: int | None = 0,
) -> AnalyticEvent:
    return AnalyticEvent(
        event_id=eid,
        type=type_,
        source="auto:yolo",
        start=_SINCE + timedelta(seconds=10),
        end=_SINCE + timedelta(seconds=15),
        monitor_index=monitor_index,
        track_id=track_id,
        zone=zone,
        confidence=0.9,
    )


# ── stub analytics port ───────────────────────────────────────────────────────

class StubAnalytics(AnalyticsQueryPort):
    def __init__(self, counts=None, dwell=None, zone_events=None):
        self._counts      = counts or []
        self._dwell       = dwell or []
        self._zone_events = zone_events or []

        self.last_count_since  = None
        self.last_count_until  = None
        self.last_count_mon    = None
        self.last_dwell_since  = None
        self.last_dwell_until  = None
        self.last_zone_name    = None
        self.last_zone_since   = None
        self.last_zone_until   = None

    def count_by_class(self, since, until, monitor_index=None):
        self.last_count_since = since
        self.last_count_until = until
        self.last_count_mon   = monitor_index
        return self._counts

    def dwell_by_track(self, since, until, monitor_index=None):
        self.last_dwell_since = since
        self.last_dwell_until = until
        return self._dwell

    def events_in_zone(self, zone_name, since, until):
        self.last_zone_name  = zone_name
        self.last_zone_since = since
        self.last_zone_until = until
        return self._zone_events


class FakeDetection:
    def get_monitors(self):
        return [MonitorInfo(name=r"\\.\DISPLAY1", width=1920, height=1080, x=0, y=0, is_primary=True, index=0)]


class FakeRecording:
    def is_recording(self): return False
    def start(self): pass
    def stop(self): pass
    def total_stored_duration_seconds(self): return 0.0
    def change_monitors(self, monitors): pass


class Cfg:
    role = "it"
    autorecord = True
    selected_monitor_fingerprints: list = []


class FakeUserConfigPort:
    def load(self): return Cfg()
    def save(self, cfg): pass


class FakeSettings:
    it_pin = "4321"


def _layer(analytics: AnalyticsQueryPort | None = None) -> ApiLayer:
    return build_api_layer(
        detection_service=FakeDetection(),
        settings=FakeSettings(),
        user_config_port=FakeUserConfigPort(),
        recording_service=FakeRecording(),
        analytics_query=analytics,
        relaunch_cb=lambda: None,
    )


# ── TestAnalyticsCommandsNoAdapter ────────────────────────────────────────────

class TestAnalyticsCommandsNoAdapter:
    """When no analytics adapter is wired, commands succeed and return empty lists."""

    def setup_method(self):
        self.router = IpcRouter(_layer(analytics=None))

    def test_counts_returns_empty(self):
        resp = self.router.handle({"id": "1", "cmd": "analytics_counts",
                                   "payload": {"since": _since_s(), "until": _until_s()}})
        assert resp["ok"] is True
        assert resp["result"] == []

    def test_dwell_returns_empty(self):
        resp = self.router.handle({"id": "2", "cmd": "analytics_dwell",
                                   "payload": {"since": _since_s(), "until": _until_s()}})
        assert resp["ok"] is True
        assert resp["result"] == []

    def test_zone_events_returns_empty(self):
        resp = self.router.handle({"id": "3", "cmd": "analytics_zone_events",
                                   "payload": {"zone_name": "entrance",
                                               "since": _since_s(), "until": _until_s()}})
        assert resp["ok"] is True
        assert resp["result"] == []


# ── TestAnalyticsCommandsWithAdapter ─────────────────────────────────────────

class TestAnalyticsCommandsWithAdapter:
    """analytics_counts / dwell / zone_events return adapter data over IPC."""

    def setup_method(self):
        self.stub = StubAnalytics(
            counts=[CountByClass(class_name="person", count=5),
                    CountByClass(class_name="car", count=2)],
            dwell=[DwellRecord(track_id=1, class_name="person",
                               total_seconds=30.0,
                               first_seen=_SINCE + timedelta(seconds=5),
                               last_seen=_SINCE + timedelta(seconds=35))],
            zone_events=[_event(eid="z1", zone="entrance")],
        )
        self.router = IpcRouter(_layer(analytics=self.stub))

    def test_counts_shape(self):
        resp = self.router.handle({"id": "1", "cmd": "analytics_counts",
                                   "payload": {"since": _since_s(), "until": _until_s()}})
        assert resp["ok"] is True
        result = resp["result"]
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["class_name"] == "person"
        assert result[0]["count"] == 5

    def test_dwell_shape(self):
        resp = self.router.handle({"id": "2", "cmd": "analytics_dwell",
                                   "payload": {"since": _since_s(), "until": _until_s()}})
        assert resp["ok"] is True
        result = resp["result"]
        assert len(result) == 1
        assert result[0]["track_id"] == 1
        assert result[0]["total_seconds"] == pytest.approx(30.0)

    def test_zone_events_shape(self):
        resp = self.router.handle({"id": "3", "cmd": "analytics_zone_events",
                                   "payload": {"zone_name": "entrance",
                                               "since": _since_s(), "until": _until_s()}})
        assert resp["ok"] is True
        result = resp["result"]
        assert len(result) == 1
        assert result[0]["event_id"] == "z1"
        assert result[0]["zone"] == "entrance"


# ── TestAnalyticsFilters ──────────────────────────────────────────────────────

class TestAnalyticsFilters:
    """Payload fields are forwarded correctly to the adapter."""

    def setup_method(self):
        self.stub = StubAnalytics()
        self.router = IpcRouter(_layer(analytics=self.stub))

    def test_monitor_index_forwarded(self):
        self.router.handle({"id": "1", "cmd": "analytics_counts",
                             "payload": {"since": _since_s(), "until": _until_s(),
                                         "monitor_index": 2}})
        assert self.stub.last_count_mon == 2

    def test_monitor_index_none_when_omitted(self):
        self.router.handle({"id": "2", "cmd": "analytics_dwell",
                             "payload": {"since": _since_s(), "until": _until_s()}})
        assert self.stub.last_dwell_since is not None

    def test_zone_name_forwarded(self):
        self.router.handle({"id": "3", "cmd": "analytics_zone_events",
                             "payload": {"zone_name": "lobby",
                                         "since": _since_s(), "until": _until_s()}})
        assert self.stub.last_zone_name == "lobby"

    def test_js_iso_z_suffix_parsed(self):
        """JS Date.toISOString() uses 'Z' suffix — must round-trip through the router."""
        since_z = "2026-07-05T11:00:00.000Z"
        until_z = "2026-07-05T12:00:00.000Z"
        resp = self.router.handle({"id": "4", "cmd": "analytics_counts",
                                   "payload": {"since": since_z, "until": until_z}})
        assert resp["ok"] is True
        # Adapter received proper datetime objects
        assert self.stub.last_count_since is not None
        assert self.stub.last_count_since.tzinfo is not None


# ── TestAnalyticsIpcWiring ────────────────────────────────────────────────────

class TestAnalyticsIpcWiring:
    """build_api_layer stores the analytics adapter on api.analytics."""

    def test_analytics_field_none_by_default(self):
        layer = _layer(analytics=None)
        assert layer.analytics is None

    def test_analytics_field_set_when_provided(self):
        stub = StubAnalytics()
        layer = _layer(analytics=stub)
        assert layer.analytics is stub


# ── TestSqliteAnalyticsRoundtrip ──────────────────────────────────────────────

class TestSqliteAnalyticsRoundtrip:
    """Full roundtrip: store AnalyticEvent in SQLite → router returns correct data."""

    def setup_method(self, method):
        self.store    = SqliteEventStoreAdapter(":memory:")
        self.adapter  = SqliteAnalyticsAdapter(self.store)
        self.router   = IpcRouter(_layer(analytics=self.adapter))

        ev = _event(eid="rt1", type_="person", zone="lobby", track_id=7)
        self.store.add(ev)

    def test_counts_roundtrip(self):
        resp = self.router.handle({"id": "1", "cmd": "analytics_counts",
                                   "payload": {"since": _since_s(), "until": _until_s()}})
        assert resp["ok"] is True
        counts = resp["result"]
        assert any(c["class_name"] == "person" and c["count"] >= 1 for c in counts)

    def test_dwell_roundtrip(self):
        resp = self.router.handle({"id": "2", "cmd": "analytics_dwell",
                                   "payload": {"since": _since_s(), "until": _until_s()}})
        assert resp["ok"] is True
        dwell = resp["result"]
        assert any(d["track_id"] == 7 for d in dwell)

    def test_zone_events_roundtrip(self):
        resp = self.router.handle({"id": "3", "cmd": "analytics_zone_events",
                                   "payload": {"zone_name": "lobby",
                                               "since": _since_s(), "until": _until_s()}})
        assert resp["ok"] is True
        events = resp["result"]
        assert len(events) == 1
        assert events[0]["event_id"] == "rt1"
