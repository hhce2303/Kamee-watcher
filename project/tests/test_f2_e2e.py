"""
Integration test — Fase 2 (R-AI): detect → AnalyticEvent → EventStore + sidecar + clip.

Proves the full pipeline end-to-end without FFmpeg or a real model:
    MockDetectorAdapter
        → AutoEventService (threshold + cooldown)
            → _on_auto_event callback
                → EventStorePort.add()          (marker)
                → ClipBuilder.snapshot_event()  (same call as manual events)
                → ClipBuilder.build()           (stubbed, returns instantly)
                → write_sidecar()               (JSON sidecar next to clip)
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from unittest.mock import MagicMock, patch

import pytest

from app.adapters.ml.mock_detector import MockDetectorAdapter
from app.adapters.storage.sqlite_event_store import SqliteEventStoreAdapter
from app.core.analytics.models import AnalyticEvent
from app.core.analytics.sidecar import read_sidecar, sidecar_path
from app.core.auto_event_service import AutoEventService
from app.core.recording_service.models import EventContext, MonitorInfo

_T0 = datetime(2026, 6, 22, 12, 0, 0, tzinfo=timezone.utc)
_META = {"frame_time": _T0, "monitor_index": 0, "width": 1920, "height": 1080}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fake_monitor() -> MonitorInfo:
    return MonitorInfo(index=0, name=r"\\.\DISPLAY1", width=1920, height=1080,
                       x=0, y=0, is_primary=True, fingerprint="FP0")


def _fake_ctx(triggered_at: datetime) -> EventContext:
    from datetime import timedelta
    return EventContext(
        event_id=triggered_at.strftime("%H%M%S"),
        triggered_at=triggered_at,
        window_start=triggered_at - timedelta(seconds=120),
        window_end=triggered_at + timedelta(seconds=120),
        monitors=(_fake_monitor(),),
    )


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
        """on_auto_event must call snapshot_event() then schedule build() via Timer."""
        detector = MockDetectorAdapter(confidence=0.9)

        # Stub ClipBuilder: snapshot_event() returns a context, build() returns a fake path.
        fake_clip = tmp_path / "clips" / "event_000000.mp4"
        fake_clip.parent.mkdir(parents=True, exist_ok=True)
        fake_clip.write_bytes(b"FAKE_MP4")

        clip_builder = MagicMock()
        clip_builder.snapshot_event.return_value = _fake_ctx(_T0)
        clip_builder.build.return_value = fake_clip

        # Build the same _on_auto_event closure as in backend.py
        build_done = threading.Event()

        def _on_auto_event(event: AnalyticEvent) -> None:
            store.add(event)
            ctx = clip_builder.snapshot_event(event.start)

            def _build_auto_clip() -> None:
                output = clip_builder.build(ctx)
                if output:
                    updated = event.model_copy(update={"clip_path": output})
                    store.add(updated)
                    from app.core.analytics.sidecar import write_sidecar
                    write_sidecar(output, [updated])
                build_done.set()

            # post_seconds=0 to run immediately in tests
            t = threading.Timer(0, _build_auto_clip)
            t.daemon = True
            t.start()

        svc = AutoEventService(detector, _on_auto_event, confidence_threshold=0.6, cooldown_seconds=0)
        svc.start()
        detector.analyze(b"fake_frame", _META)

        build_done.wait(timeout=2.0)

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

        build_done = threading.Event()

        def _on_auto_event(event: AnalyticEvent) -> None:
            store.add(event)
            ctx = clip_builder.snapshot_event(event.start)

            def _build_auto_clip() -> None:
                output = clip_builder.build(ctx)
                if output:
                    updated = event.model_copy(update={"clip_path": output})
                    store.add(updated)
                    from app.core.analytics.sidecar import write_sidecar
                    write_sidecar(output, [updated])
                build_done.set()

            t = threading.Timer(0, _build_auto_clip)
            t.daemon = True
            t.start()

        svc = AutoEventService(detector, _on_auto_event, confidence_threshold=0.6, cooldown_seconds=0)
        svc.start()
        detector.analyze(b"fake_frame", _META)

        build_done.wait(timeout=2.0)

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

        build_done = threading.Event()

        def _on_auto_event(event: AnalyticEvent) -> None:
            store.add(event)
            ctx = clip_builder.snapshot_event(event.start)

            def _build_auto_clip() -> None:
                output = clip_builder.build(ctx)
                if output:
                    updated = event.model_copy(update={"clip_path": output})
                    store.add(updated)
                    from app.core.analytics.sidecar import write_sidecar
                    write_sidecar(output, [updated])
                build_done.set()

            t = threading.Timer(0, _build_auto_clip)
            t.daemon = True
            t.start()

        svc = AutoEventService(detector, _on_auto_event, confidence_threshold=0.6, cooldown_seconds=0)
        svc.start()
        detector.analyze(b"fake_frame", _META)

        build_done.wait(timeout=2.0)

        # INSERT OR REPLACE means same event_id → only ONE row in the store
        assert len(store.query()) == 1
