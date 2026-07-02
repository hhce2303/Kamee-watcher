"""EditorApi facade — timeline mutations + export events, inline for determinism."""
from __future__ import annotations

from pathlib import Path

from app.core.api import dto
from app.core.api.editor_api import EditorApi
from app.core.api.events import EventBus


class FakeExportPort:
    def __init__(self, fail=False):
        self.fail = fail
        self.exported = None

    def export(self, timeline, output_path, on_progress=None):
        if on_progress:
            on_progress(0.5)
            on_progress(1.0)
        if self.fail:
            raise RuntimeError("boom")
        self.exported = output_path


def _make(export_port=None):
    bus = EventBus()
    api = EditorApi(event_bus=bus, export_port=export_port, clips_dir=Path("/tmp/clips"))
    # Run export inline so tests are deterministic (no background thread).
    api._run_export_async = api._do_export  # type: ignore[assignment]
    return bus, api


def test_add_clip_publishes_timeline_changed() -> None:
    bus, api = _make()
    events: list[object] = []
    bus.subscribe(dto.TimelineChanged, events.append)
    api.add_clip(dto.AddClip(path="/a.mp4", duration_s=10.0))
    assert api.clip_count() == 1
    bus.drain()
    assert len(events) == 1


def test_export_success_emits_started_progress_finished() -> None:
    port = FakeExportPort()
    bus, api = _make(port)
    order: list[str] = []
    bus.subscribe(dto.ExportStarted, lambda e: order.append("start"))
    bus.subscribe(dto.ExportProgress, lambda e: order.append(f"prog:{e.fraction}"))
    bus.subscribe(dto.ExportFinished, lambda e: order.append(f"done:{e.output_path}"))

    api.add_clip(dto.AddClip(path="/a.mp4", duration_s=10.0))
    api.export_timeline(dto.ExportTimeline(output_path="/out/reel.mp4"))
    bus.drain()

    assert order[0] == "start"
    assert "prog:0.5" in order and "prog:1.0" in order
    assert order[-1] == "done:/out/reel.mp4"
    assert api.exporting is False
    assert str(port.exported) in ("/out/reel.mp4", "\\out\\reel.mp4")


def test_export_failure_emits_failed() -> None:
    port = FakeExportPort(fail=True)
    bus, api = _make(port)
    fails: list[object] = []
    bus.subscribe(dto.ExportFailed, fails.append)
    api.add_clip(dto.AddClip(path="/a.mp4", duration_s=10.0))
    api.export_timeline(dto.ExportTimeline(output_path="/out/reel.mp4"))
    bus.drain()
    assert len(fails) == 1
    assert "boom" in fails[0].message
    assert api.exporting is False


def test_export_without_engine_fails_fast() -> None:
    bus, api = _make(export_port=None)
    fails: list[object] = []
    bus.subscribe(dto.ExportFailed, fails.append)
    api.add_clip(dto.AddClip(path="/a.mp4", duration_s=10.0))
    api.export_timeline(dto.ExportTimeline(output_path="/out/reel.mp4"))
    bus.drain()
    assert len(fails) == 1


def test_clear_and_remove() -> None:
    bus, api = _make()
    api.add_clip(dto.AddClip(path="/a.mp4", duration_s=10.0))
    api.add_clip(dto.AddClip(path="/b.mp4", duration_s=5.0))
    assert api.clip_count() == 2
    api.remove_clip(0)
    assert api.clip_count() == 1
    api.clear()
    assert api.clip_count() == 0


def test_file_url_normalisation_windows() -> None:
    # file:///C:/x/y.mp4 → C:/x/y.mp4 (no Qt dependency).
    p = EditorApi._to_local_path("file:///C:/videos/clip%20one.mp4")
    assert p is not None
    assert p.as_posix().endswith("C:/videos/clip one.mp4")
