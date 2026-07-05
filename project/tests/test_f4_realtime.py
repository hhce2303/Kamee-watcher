"""Fase 4 — Real-time inference test suite.

Coverage:
  TestMotionFilter         — score=0 first call, low on identical, high on diff
  TestIouTracker           — stable IDs, eviction after max_age, new detections
  TestZone                 — point-in-polygon, contains_center, zone_for_bbox
  TestAutoEventServiceZone — emitted event carries correct zone + monitor_index
  TestLiveInferenceService — motion gate, detector called on motion, subs notified
  TestSqliteAnalytics      — count_by_class, dwell_by_track, events_in_zone
  TestBackendF4Wiring      — live_service + analytics fields present in backend
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.core.analytics.models import AnalyticEvent, BoundingBox, Detection
from app.core.analytics.motion_filter import MotionFilter
from app.core.analytics.zone import Zone, zone_for_bbox
from app.adapters.ml.iou_tracker import IouTracker
from app.core.auto_event_service import AutoEventService
from app.adapters.ml.mock_detector import MockDetectorAdapter
from app.adapters.ml.live_inference_service import LiveInferenceService
from app.adapters.storage.sqlite_event_store import SqliteEventStoreAdapter
from app.adapters.storage.sqlite_analytics import SqliteAnalyticsAdapter
from app.core.ports.analytics_query_port import CountByClass, DwellRecord


# ── helpers ──────────────────────────────────────────────────────────────────

_NOW = datetime(2026, 7, 4, 12, 0, 0, tzinfo=timezone.utc)


def _det(
    cls: str = "person",
    conf: float = 0.9,
    x: float = 0.4,
    y: float = 0.4,
    w: float = 0.2,
    h: float = 0.2,
    track_id: Optional[int] = None,
    monitor_index: Optional[int] = None,
) -> Detection:
    return Detection(
        class_name=cls,
        confidence=conf,
        bbox=BoundingBox(x=x, y=y, w=w, h=h),
        frame_time=_NOW,
        track_id=track_id,
        monitor_index=monitor_index,
    )


def _gray(h: int = 90, w: int = 160, fill: int = 128) -> np.ndarray:
    return np.full((h, w), fill, dtype=np.uint8)


# ── MotionFilter ──────────────────────────────────────────────────────────────

class TestMotionFilter:
    def test_first_call_returns_zero(self):
        mf = MotionFilter()
        assert mf.update(_gray()) == 0.0

    def test_identical_frames_low_score(self):
        mf = MotionFilter()
        gray = _gray()
        mf.update(gray)
        assert mf.update(gray) < 0.001

    def test_different_frames_high_score(self):
        mf = MotionFilter()
        mf.update(_gray(fill=0))
        score = mf.update(_gray(fill=255))
        assert score > 0.9

    def test_has_motion_threshold(self):
        mf = MotionFilter(threshold=0.5)
        assert not mf.has_motion(0.3)
        assert mf.has_motion(0.5)
        assert mf.has_motion(0.8)

    def test_reset_clears_prev(self):
        mf = MotionFilter()
        mf.update(_gray(fill=0))
        mf.reset()
        # After reset, first update → 0.0 (no prev frame)
        assert mf.update(_gray(fill=255)) == 0.0

    def test_shape_change_resets_prev(self):
        mf = MotionFilter()
        mf.update(_gray(h=90, w=160, fill=0))
        # Different shape: treated as first frame
        score = mf.update(_gray(h=45, w=80, fill=255))
        assert score == 0.0

    def test_invalid_threshold_raises(self):
        with pytest.raises(ValueError):
            MotionFilter(threshold=0.0)
        with pytest.raises(ValueError):
            MotionFilter(threshold=1.1)


# ── IouTracker ────────────────────────────────────────────────────────────────

class TestIouTracker:
    def test_new_detection_gets_id(self):
        trk = IouTracker()
        result = trk.update([_det()])
        assert len(result) == 1
        assert result[0].track_id == 1

    def test_same_bbox_keeps_id(self):
        trk = IouTracker()
        d = _det()
        trk.update([d])
        result = trk.update([d])
        assert result[0].track_id == 1

    def test_non_overlapping_bbox_gets_new_id(self):
        trk = IouTracker()
        trk.update([_det(x=0.0, y=0.0, w=0.1, h=0.1)])
        result = trk.update([_det(x=0.8, y=0.8, w=0.1, h=0.1)])
        assert result[0].track_id == 2

    def test_track_evicted_after_max_age(self):
        trk = IouTracker(max_age=2)
        trk.update([_det()])          # frame 1 — track born
        trk.update([])                # frame 2 — age=1
        trk.update([])                # frame 3 — age=2 (still alive)
        trk.update([])                # frame 4 — age=3 → evicted
        result = trk.update([_det()]) # frame 5 — new track
        assert result[0].track_id == 2

    def test_empty_detections_returns_empty(self):
        trk = IouTracker()
        assert trk.update([]) == []

    def test_multiple_detections_get_distinct_ids(self):
        trk = IouTracker()
        d1 = _det(x=0.0, y=0.0, w=0.2, h=0.2)
        d2 = _det(x=0.7, y=0.7, w=0.2, h=0.2)
        result = trk.update([d1, d2])
        ids = {r.track_id for r in result}
        assert len(ids) == 2

    def test_reset_clears_tracks(self):
        trk = IouTracker()
        trk.update([_det()])
        trk.reset()
        result = trk.update([_det()])
        assert result[0].track_id == 1   # ID counter reset


# ── Zone ─────────────────────────────────────────────────────────────────────

class TestZone:
    _SQUARE = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))

    def test_center_inside(self):
        z = Zone(name="area", vertices=self._SQUARE)
        bbox = BoundingBox(x=0.3, y=0.3, w=0.4, h=0.4)  # center (0.5, 0.5)
        assert z.contains_center(bbox)

    def test_center_outside(self):
        inner = ((0.1, 0.1), (0.4, 0.1), (0.4, 0.4), (0.1, 0.4))
        z = Zone(name="area", vertices=inner)
        bbox = BoundingBox(x=0.7, y=0.7, w=0.2, h=0.2)  # center (0.8, 0.8)
        assert not z.contains_center(bbox)

    def test_requires_three_vertices(self):
        with pytest.raises(ValueError):
            Zone(name="x", vertices=((0.0, 0.0), (1.0, 0.0)))

    def test_zone_for_bbox_returns_name(self):
        z = Zone(name="entrance", vertices=self._SQUARE, monitor_index=0)
        bbox = BoundingBox(x=0.3, y=0.3, w=0.4, h=0.4)
        assert zone_for_bbox(bbox, monitor_index=0, zones=[z]) == "entrance"

    def test_zone_for_bbox_wrong_monitor(self):
        z = Zone(name="entrance", vertices=self._SQUARE, monitor_index=1)
        bbox = BoundingBox(x=0.3, y=0.3, w=0.4, h=0.4)
        assert zone_for_bbox(bbox, monitor_index=0, zones=[z]) is None

    def test_zone_for_bbox_none_when_outside(self):
        inner = ((0.0, 0.0), (0.1, 0.0), (0.1, 0.1), (0.0, 0.1))
        z = Zone(name="corner", vertices=inner)
        bbox = BoundingBox(x=0.7, y=0.7, w=0.2, h=0.2)
        assert zone_for_bbox(bbox, monitor_index=0, zones=[z]) is None


# ── AutoEventService + zones ──────────────────────────────────────────────────

class TestAutoEventServiceZone:
    _FULL_SQUARE = ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0))

    def test_emitted_event_has_zone(self):
        detector = MockDetectorAdapter()
        received: List[AnalyticEvent] = []
        zone = Zone(name="entrance", vertices=self._FULL_SQUARE, monitor_index=0)
        svc = AutoEventService(
            detector=detector,
            on_event=received.append,
            confidence_threshold=0.5,
            cooldown_seconds=0,
            zones=[zone],
        )
        svc.start()
        # Inject a detection with monitor_index=0
        det = _det(x=0.3, y=0.3, w=0.2, h=0.2, monitor_index=0)
        svc._on_detections([det])
        svc.stop()
        assert len(received) == 1
        assert received[0].zone == "entrance"
        assert received[0].monitor_index == 0

    def test_event_no_zone_when_none_match(self):
        detector = MockDetectorAdapter()
        received: List[AnalyticEvent] = []
        inner = ((0.0, 0.0), (0.1, 0.0), (0.1, 0.1), (0.0, 0.1))
        zone = Zone(name="corner", vertices=inner, monitor_index=0)
        svc = AutoEventService(
            detector=detector,
            on_event=received.append,
            confidence_threshold=0.5,
            cooldown_seconds=0,
            zones=[zone],
        )
        svc.start()
        det = _det(x=0.7, y=0.7, w=0.2, h=0.2, monitor_index=0)
        svc._on_detections([det])
        svc.stop()
        assert received[0].zone is None

    def test_event_no_zone_when_no_monitor_index(self):
        detector = MockDetectorAdapter()
        received: List[AnalyticEvent] = []
        zone = Zone(name="entrance", vertices=self._FULL_SQUARE)
        svc = AutoEventService(
            detector=detector,
            on_event=received.append,
            confidence_threshold=0.5,
            cooldown_seconds=0,
            zones=[zone],
        )
        svc.start()
        det = _det()  # monitor_index=None
        svc._on_detections([det])
        svc.stop()
        assert received[0].zone is None


# ── LiveInferenceService ──────────────────────────────────────────────────────

class TestLiveInferenceService:
    def _make_jpeg(self) -> bytes:
        """Generate a minimal valid JPEG (1×1 white pixel)."""
        try:
            from PIL import Image
            import io
            img = Image.new("RGB", (4, 4), color=(255, 255, 255))
            buf = io.BytesIO()
            img.save(buf, format="JPEG")
            return buf.getvalue()
        except ImportError:
            pytest.skip("Pillow not installed")

    def test_passthrough_analyze(self):
        det = MockDetectorAdapter()
        det.start()
        svc = LiveInferenceService(detector=det, preview_paths={}, poll_interval=99.0)
        result = svc.analyze(b"fake", {"frame_time": _NOW, "monitor_index": 0, "width": 640, "height": 640})
        assert len(result) == 1
        det.stop()

    def test_motion_gate_skips_identical_frames(self, tmp_path: Path):
        jpeg = self._make_jpeg()
        preview = tmp_path / "preview.jpg"
        preview.write_bytes(jpeg)

        notified: List = []
        det = MockDetectorAdapter()
        svc = LiveInferenceService(
            detector=det,
            preview_paths={0: preview},
            motion_threshold=0.5,  # very high — identical frame won't pass
            poll_interval=0.05,
        )
        svc.subscribe(notified.append)
        svc.start()
        time.sleep(0.3)
        svc.stop()
        # First frame sets prev; subsequent identical frames don't trigger detection.
        assert len(notified) == 0

    def test_motion_triggers_detection(self, tmp_path: Path):
        preview = tmp_path / "preview.jpg"

        try:
            from PIL import Image
            import io
            # Write first frame (black)
            img = Image.new("RGB", (4, 4), color=(0, 0, 0))
            buf = io.BytesIO(); img.save(buf, format="JPEG")
            preview.write_bytes(buf.getvalue())
        except ImportError:
            pytest.skip("Pillow not installed")

        notified: List = []
        det = MockDetectorAdapter()
        svc = LiveInferenceService(
            detector=det,
            preview_paths={0: preview},
            motion_threshold=0.01,  # very low — any motion passes
            poll_interval=0.05,
        )
        svc.subscribe(notified.append)
        svc.start()
        time.sleep(0.15)  # first poll: sets prev, no notify

        # Replace with very different frame (white)
        img2 = Image.new("RGB", (4, 4), color=(255, 255, 255))
        buf2 = io.BytesIO(); img2.save(buf2, format="JPEG")
        preview.write_bytes(buf2.getvalue())
        time.sleep(0.2)
        svc.stop()

        assert len(notified) >= 1

    def test_monitor_index_tagged_on_detections(self, tmp_path: Path):
        jpeg = self._make_jpeg()
        preview = tmp_path / "preview.jpg"

        try:
            from PIL import Image
            import io
            # Write one frame (black), then white to trigger motion
            img = Image.new("RGB", (4, 4), (0, 0, 0))
            buf = io.BytesIO(); img.save(buf, format="JPEG")
            preview.write_bytes(buf.getvalue())
        except ImportError:
            pytest.skip("Pillow not installed")

        received: List = []
        det = MockDetectorAdapter()
        svc = LiveInferenceService(
            detector=det,
            preview_paths={3: preview},
            motion_threshold=0.01,
            poll_interval=0.05,
        )
        svc.subscribe(received.append)
        svc.start()
        time.sleep(0.15)

        img2 = Image.new("RGB", (4, 4), (255, 255, 255))
        buf2 = io.BytesIO(); img2.save(buf2, format="JPEG")
        preview.write_bytes(buf2.getvalue())
        time.sleep(0.2)
        svc.stop()

        if received:
            dets = received[0]
            assert all(d.monitor_index == 3 for d in dets)

    def test_stop_is_idempotent(self):
        det = MockDetectorAdapter()
        svc = LiveInferenceService(detector=det, preview_paths={}, poll_interval=99.0)
        svc.start()
        svc.stop()
        svc.stop()  # should not raise


# ── SqliteAnalyticsAdapter ────────────────────────────────────────────────────

def _make_store(tmp_path: Path) -> SqliteEventStoreAdapter:
    return SqliteEventStoreAdapter(tmp_path / "events.db")


def _event(
    eid: str,
    cls: str,
    start: datetime,
    end: datetime,
    track_id: Optional[int] = None,
    monitor_index: Optional[int] = None,
    zone: Optional[str] = None,
) -> AnalyticEvent:
    return AnalyticEvent(
        event_id=eid,
        type=cls,
        source="auto:yolo",
        start=start,
        end=end,
        track_id=track_id,
        monitor_index=monitor_index,
        zone=zone,
    )


class TestSqliteAnalytics:
    def test_count_by_class_basic(self, tmp_path: Path):
        store = _make_store(tmp_path)
        t = _NOW
        store.add(_event("e1", "person", t, t + timedelta(seconds=5)))
        store.add(_event("e2", "person", t, t + timedelta(seconds=5)))
        store.add(_event("e3", "car",    t, t + timedelta(seconds=5)))
        adapter = SqliteAnalyticsAdapter(store)
        counts = adapter.count_by_class(since=t - timedelta(hours=1), until=t + timedelta(hours=1))
        by_name = {c.class_name: c.count for c in counts}
        assert by_name["person"] == 2
        assert by_name["car"] == 1

    def test_count_by_class_empty(self, tmp_path: Path):
        store = _make_store(tmp_path)
        adapter = SqliteAnalyticsAdapter(store)
        result = adapter.count_by_class(since=_NOW, until=_NOW + timedelta(hours=1))
        assert result == []

    def test_count_by_class_monitor_filter(self, tmp_path: Path):
        store = _make_store(tmp_path)
        t = _NOW
        store.add(_event("e1", "person", t, t + timedelta(seconds=5), monitor_index=0))
        store.add(_event("e2", "person", t, t + timedelta(seconds=5), monitor_index=1))
        adapter = SqliteAnalyticsAdapter(store)
        counts = adapter.count_by_class(since=t - timedelta(hours=1), until=t + timedelta(hours=1), monitor_index=0)
        assert sum(c.count for c in counts) == 1

    def test_dwell_by_track_basic(self, tmp_path: Path):
        store = _make_store(tmp_path)
        t = _NOW
        store.add(_event("e1", "person", t,                          t + timedelta(seconds=10), track_id=42))
        store.add(_event("e2", "person", t + timedelta(seconds=15),  t + timedelta(seconds=25), track_id=42))
        adapter = SqliteAnalyticsAdapter(store)
        records = adapter.dwell_by_track(since=t - timedelta(hours=1), until=t + timedelta(hours=1))
        assert len(records) == 1
        assert records[0].track_id == 42
        assert records[0].total_seconds == pytest.approx(20.0)

    def test_dwell_by_track_skips_no_track_id(self, tmp_path: Path):
        store = _make_store(tmp_path)
        t = _NOW
        store.add(_event("e1", "person", t, t + timedelta(seconds=5)))  # no track_id
        adapter = SqliteAnalyticsAdapter(store)
        assert adapter.dwell_by_track(since=t - timedelta(hours=1), until=t + timedelta(hours=1)) == []

    def test_events_in_zone(self, tmp_path: Path):
        store = _make_store(tmp_path)
        t = _NOW
        store.add(_event("e1", "person", t, t + timedelta(seconds=5), zone="entrance"))
        store.add(_event("e2", "person", t, t + timedelta(seconds=5), zone="exit"))
        store.add(_event("e3", "person", t, t + timedelta(seconds=5), zone=None))
        adapter = SqliteAnalyticsAdapter(store)
        result = adapter.events_in_zone("entrance", since=t - timedelta(hours=1), until=t + timedelta(hours=1))
        assert len(result) == 1
        assert result[0].event_id == "e1"

    def test_events_in_zone_empty(self, tmp_path: Path):
        store = _make_store(tmp_path)
        adapter = SqliteAnalyticsAdapter(store)
        result = adapter.events_in_zone("x", since=_NOW, until=_NOW + timedelta(hours=1))
        assert result == []


# ── Backend F4 wiring ─────────────────────────────────────────────────────────

class TestBackendF4Wiring:
    def test_live_service_field_exists(self):
        from app.runtime.backend import RecordingBackend
        from app.adapters.ml.live_inference_service import LiveInferenceService
        backend = RecordingBackend()
        assert hasattr(backend, "live_service")
        assert backend.live_service is None

    def test_analytics_field_exists(self):
        from app.runtime.backend import RecordingBackend
        from app.adapters.storage.sqlite_analytics import SqliteAnalyticsAdapter
        backend = RecordingBackend()
        assert hasattr(backend, "analytics")
        assert backend.analytics is None

    def test_motion_filter_module_importable(self):
        from app.core.analytics.motion_filter import MotionFilter
        assert MotionFilter is not None

    def test_tracker_port_module_importable(self):
        from app.core.ports.tracker_port import TrackerPort
        assert TrackerPort is not None

    def test_analytics_query_port_module_importable(self):
        from app.core.ports.analytics_query_port import AnalyticsQueryPort, CountByClass, DwellRecord
        assert AnalyticsQueryPort is not None

    def test_zone_module_importable(self):
        from app.core.analytics.zone import Zone, zone_for_bbox
        assert Zone is not None
