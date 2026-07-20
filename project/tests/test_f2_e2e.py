"""
Integration test — Fase 2 (R-AI): detect → AnalyticEvent → EventStore + sidecar + clip.

Proves the full pipeline end-to-end without FFmpeg or a real model:
    MockDetectorAdapter
        → AutoEventService (threshold + cooldown)
            → _on_auto_event callback (mirrors app.runtime.backend's wiring)
                → EventStorePort.add()             (marker)
                → build-coalescing gate            (skips redundant overlapping builds)
                → ClipBuilder.snapshot_event()      (same call as manual events)
                → EventService.schedule_clip_build() (retry + logging, same as manual events)
                → write_sidecar()                   (JSON sidecar next to clip)
"""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional
from unittest.mock import MagicMock, patch

import pytest

from app.adapters.ml.mock_detector import MockDetectorAdapter
from app.adapters.storage.sqlite_event_store import SqliteEventStoreAdapter
from app.core.analytics.models import AnalyticEvent
from app.core.analytics.sidecar import read_sidecar, sidecar_path, write_sidecar
from app.core.auto_event_service import AutoEventService
from app.core.event_service import EventService
from app.core.recording_service.models import EventContext, MonitorInfo

_T0 = datetime(2026, 6, 22, 12, 0, 0, tzinfo=timezone.utc)
_META = {"frame_time": _T0, "monitor_index": 0, "width": 1920, "height": 1080}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fake_monitor() -> MonitorInfo:
    return MonitorInfo(index=0, name=r"\\.\DISPLAY1", width=1920, height=1080,
                       x=0, y=0, is_primary=True, fingerprint="FP0")


def _fake_ctx(triggered_at: datetime) -> EventContext:
    return EventContext(
        event_id=triggered_at.strftime("%H%M%S"),
        triggered_at=triggered_at,
        window_start=triggered_at - timedelta(seconds=120),
        window_end=triggered_at + timedelta(seconds=120),
        monitors=(_fake_monitor(),),
    )


class _AutoEventRouter:
    """Mirrors app.runtime.backend._on_auto_event: persists the marker, coalesces
    redundant clip-build scheduling, and routes the actual build through
    EventService.schedule_clip_build() so it gets the same retry/logging as a
    manual event instead of a bespoke unhandled Timer."""

    def __init__(
        self,
        store: SqliteEventStoreAdapter,
        clip_builder: MagicMock,
        event_service: EventService,
        min_build_interval: timedelta = timedelta(0),
    ) -> None:
        self._store = store
        self._clip_builder = clip_builder
        self._event_service = event_service
        self._min_build_interval = min_build_interval
        self._lock = threading.Lock()
        self._last_build_at: Optional[datetime] = None

    def __call__(self, event: AnalyticEvent) -> None:
        self._store.add(event)

        with self._lock:
            if (
                self._last_build_at is not None
                and event.start - self._last_build_at < self._min_build_interval
            ):
                return
            self._last_build_at = event.start

        ctx = self._clip_builder.snapshot_event(event.start)

        def _persist(_ctx: EventContext, output: Path) -> None:
            updated = event.model_copy(update={"clip_path": output})
            self._store.add(updated)
            try:
                write_sidecar(output, [updated])
            except OSError:
                pass

        self._event_service.schedule_clip_build(ctx, on_built=_persist)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def store(tmp_path: Path) -> SqliteEventStoreAdapter:
    return SqliteEventStoreAdapter(tmp_path / "events.db")


@pytest.fixture()
def clip_path(tmp_path: Path) -> Path:
    p = tmp_path / "clips" / "auto_event.mp4"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"FAKE_MP4")
    return p


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestF2Pipeline:
    """End-to-end: mock detection → AnalyticEvent → store + sidecar + clip trigger."""

    def test_detection_persists_analytic_event(self, store: SqliteEventStoreAdapter) -> None:
        """A mock detection above threshold must produce an AnalyticEvent in the store."""
        detector = MockDetectorAdapter(confidence=0.9)
        received: List[AnalyticEvent] = []

        def _on_event(ev: AnalyticEvent) -> None:
            store.add(ev)
            received.append(ev)

        svc = AutoEventService(detector, _on_event, confidence_threshold=0.6, cooldown_seconds=0)
        svc.start()
        detector.analyze(b"fake_frame", _META)

        assert len(received) == 1
        assert received[0].source == "auto:yolo"
        assert received[0].type == "person"
        assert received[0].confidence == pytest.approx(0.9)

        # Verify the store has it
        stored = store.query()
        assert len(stored) == 1
        assert stored[0].event_id == received[0].event_id

    def test_below_threshold_nothing_stored(self, store: SqliteEventStoreAdapter) -> None:
        """Detections below threshold must NOT produce an event or store entry."""
        detector = MockDetectorAdapter(confidence=0.3)

        def _on_event(ev: AnalyticEvent) -> None:
            store.add(ev)

        svc = AutoEventService(detector, _on_event, confidence_threshold=0.6, cooldown_seconds=0)
        svc.start()
        detector.analyze(b"fake_frame", _META)

        assert store.query() == []

    def test_clip_build_triggered_with_snapshot(
        self, store: SqliteEventStoreAdapter, tmp_path: Path
    ) -> None:
        """on_auto_event must call snapshot_event() then schedule build() via EventService."""
        detector = MockDetectorAdapter(confidence=0.9)

        # Stub ClipBuilder: snapshot_event() returns a context, build() returns a fake path.
        fake_clip = tmp_path / "clips" / "event_000000.mp4"
        fake_clip.parent.mkdir(parents=True, exist_ok=True)
        fake_clip.write_bytes(b"FAKE_MP4")

        clip_builder = MagicMock()
        clip_builder.snapshot_event.return_value = _fake_ctx(_T0)
        clip_builder.build.return_value = fake_clip

        build_done = threading.Event()
        clip_builder.build.side_effect = lambda ctx: (build_done.set(), fake_clip)[1]

        # post_seconds=0 so the timer fires immediately in tests
        event_service = EventService(clip_builder=clip_builder, post_seconds=0, cooldown_seconds=0)
        on_auto_event = _AutoEventRouter(store, clip_builder, event_service)

        svc = AutoEventService(detector, on_auto_event, confidence_threshold=0.6, cooldown_seconds=0)
        svc.start()
        detector.analyze(b"fake_frame", _META)

        assert build_done.wait(timeout=2.0)

        # snapshot_event() and build() were each called once; timestamp is the detection time
        clip_builder.snapshot_event.assert_called_once()
        clip_builder.build.assert_called_once()

    def test_sidecar_written_when_clip_ready(
        self, store: SqliteEventStoreAdapter, tmp_path: Path
    ) -> None:
        """A .events.json sidecar must appear next to the clip after build completes."""
        detector = MockDetectorAdapter(confidence=0.9)

        fake_clip = tmp_path / "clips" / "event_000000.mp4"
        fake_clip.parent.mkdir(parents=True, exist_ok=True)
        fake_clip.write_bytes(b"FAKE_MP4")

        clip_builder = MagicMock()
        clip_builder.snapshot_event.return_value = _fake_ctx(_T0)
        clip_builder.build.return_value = fake_clip

        event_service = EventService(clip_builder=clip_builder, post_seconds=0, cooldown_seconds=0)
        on_auto_event = _AutoEventRouter(store, clip_builder, event_service)

        svc = AutoEventService(detector, on_auto_event, confidence_threshold=0.6, cooldown_seconds=0)
        svc.start()
        detector.analyze(b"fake_frame", _META)

        # Poll for the sidecar instead of a fixed sleep — build runs on a Timer thread.
        deadline = threading.Event()
        for _ in range(200):
            if sidecar_path(fake_clip).exists():
                break
            deadline.wait(0.01)

        # Sidecar must exist and contain the event
        sc_events = read_sidecar(fake_clip)
        assert len(sc_events) == 1
        assert sc_events[0].source == "auto:yolo"
        assert sc_events[0].clip_path == fake_clip

        # Store must have the updated event with clip_path
        stored = store.query()
        assert len(stored) == 1
        assert stored[0].clip_path == fake_clip

    def test_store_has_two_entries_after_clip(
        self, store: SqliteEventStoreAdapter, tmp_path: Path
    ) -> None:
        """Store should have the final updated entry (INSERT OR REPLACE), not two rows."""
        detector = MockDetectorAdapter(confidence=0.9)

        fake_clip = tmp_path / "clips" / "event.mp4"
        fake_clip.parent.mkdir(parents=True, exist_ok=True)
        fake_clip.write_bytes(b"FAKE_MP4")

        clip_builder = MagicMock()
        clip_builder.snapshot_event.return_value = _fake_ctx(_T0)
        clip_builder.build.return_value = fake_clip

        event_service = EventService(clip_builder=clip_builder, post_seconds=0, cooldown_seconds=0)
        on_auto_event = _AutoEventRouter(store, clip_builder, event_service)

        svc = AutoEventService(detector, on_auto_event, confidence_threshold=0.6, cooldown_seconds=0)
        svc.start()
        detector.analyze(b"fake_frame", _META)

        deadline = threading.Event()
        for _ in range(200):
            if len(store.query()) == 1 and store.query()[0].clip_path is not None:
                break
            deadline.wait(0.01)

        # INSERT OR REPLACE means same event_id → only ONE row in the store
        assert len(store.query()) == 1


class TestAutoEventBuildCoalescing:
    """Fix for the "sobreesfuerzo" bug: continuous detections used to each
    schedule their own full multi-monitor clip re-encode (30s event cooldown
    vs. a 4-minute clip window meant up to 8 heavily-overlapping builds for a
    single visit). A new clip BUILD is now only scheduled once per
    min_build_interval, independent of how often the event itself fires."""

    def test_rapid_events_schedule_only_one_build(
        self, store: SqliteEventStoreAdapter, tmp_path: Path
    ) -> None:
        fake_clip = tmp_path / "clips" / "event.mp4"
        fake_clip.parent.mkdir(parents=True, exist_ok=True)
        fake_clip.write_bytes(b"FAKE_MP4")

        clip_builder = MagicMock()
        clip_builder.snapshot_event.side_effect = _fake_ctx
        clip_builder.build.return_value = fake_clip

        event_service = EventService(clip_builder=clip_builder, post_seconds=0, cooldown_seconds=0)
        on_auto_event = _AutoEventRouter(
            store, clip_builder, event_service, min_build_interval=timedelta(seconds=240)
        )

        # Three events 30s apart — same pattern as the reported logs (person
        # re-detected every ~30s while the clip window is 240s wide).
        on_auto_event(AnalyticEvent(
            event_id="1", type="person", source="auto:yolo",
            start=_T0, end=_T0, confidence=0.9,
        ))
        on_auto_event(AnalyticEvent(
            event_id="2", type="person", source="auto:yolo",
            start=_T0 + timedelta(seconds=30), end=_T0, confidence=0.9,
        ))
        on_auto_event(AnalyticEvent(
            event_id="3", type="person", source="auto:yolo",
            start=_T0 + timedelta(seconds=60), end=_T0, confidence=0.9,
        ))

        import time
        time.sleep(0.2)

        # All three markers are still persisted for analytics/timeline...
        assert len(store.query()) == 3
        # ...but only the FIRST one triggered a clip build.
        clip_builder.snapshot_event.assert_called_once()
        clip_builder.build.assert_called_once()

    def test_event_past_min_interval_schedules_new_build(
        self, store: SqliteEventStoreAdapter, tmp_path: Path
    ) -> None:
        fake_clip = tmp_path / "clips" / "event.mp4"
        fake_clip.parent.mkdir(parents=True, exist_ok=True)
        fake_clip.write_bytes(b"FAKE_MP4")

        clip_builder = MagicMock()
        clip_builder.snapshot_event.side_effect = _fake_ctx
        clip_builder.build.return_value = fake_clip

        event_service = EventService(clip_builder=clip_builder, post_seconds=0, cooldown_seconds=0)
        on_auto_event = _AutoEventRouter(
            store, clip_builder, event_service, min_build_interval=timedelta(seconds=240)
        )

        on_auto_event(AnalyticEvent(
            event_id="1", type="person", source="auto:yolo",
            start=_T0, end=_T0, confidence=0.9,
        ))
        on_auto_event(AnalyticEvent(
            event_id="2", type="person", source="auto:yolo",
            start=_T0 + timedelta(seconds=241), end=_T0, confidence=0.9,
        ))

        import time
        time.sleep(0.2)

        assert clip_builder.snapshot_event.call_count == 2
        assert clip_builder.build.call_count == 2
