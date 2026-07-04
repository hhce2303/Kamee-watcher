"""build_recording_backend — non-recording roles get an empty backend (ADR-0010).

The recording-role path constructs FFmpeg recorders (needs real monitors/ffmpeg),
so it is exercised by the app at runtime; here we lock down the role gating and
the empty-backend contract that the headless daemon/QML paths both rely on.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.runtime.backend import RecordingBackend, build_recording_backend


class _Storage:
    pass


def _settings(tmp_path):
    return SimpleNamespace(
        segment_dir=tmp_path / "segments",
        video_codec="h264",
    )


def test_supervisor_gets_empty_backend(tmp_path):
    backend = build_recording_backend(
        settings=_settings(tmp_path),
        user_config=SimpleNamespace(role="supervisor", selected_monitor_fingerprints=[]),
        storage=_Storage(),
        all_monitors=[],
        clips_dir=tmp_path / "clips",
        raw_clips_dir=tmp_path / "raw",
    )
    assert isinstance(backend, RecordingBackend)
    assert backend.records is False
    assert backend.recording_service is None
    assert backend.build_worker_for is None
    assert backend.workers == []


def test_unconfigured_role_gets_empty_backend(tmp_path):
    backend = build_recording_backend(
        settings=_settings(tmp_path),
        user_config=SimpleNamespace(role="", selected_monitor_fingerprints=[]),
        storage=_Storage(),
        all_monitors=[],
        clips_dir=tmp_path / "clips",
        raw_clips_dir=tmp_path / "raw",
    )
    assert backend.records is False
    assert backend.event_store is None
