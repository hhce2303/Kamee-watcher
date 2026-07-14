"""FFmpegMp4ConverterAdapter — timeout-kill safety and duration-probe reuse.

Two bugs fixed here, both surfaced while transcoding a 13h45m/15.5GB
interrupted recording (see test_clip_inspector_adapter.py for the root
duration issue):
1. A flat 1-hour process.wait() timeout that, on expiry, stopped waiting but
   never killed the ffmpeg process — orphaning it in the background while the
   caller reported failure.
2. A separate, non-fallback-aware ffprobe call for progress-bar duration, so
   on_progress() was silently never called at all for exactly the class of
   file (no header duration) this converter exists to rescue.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import threading

from app.adapters.ffmpeg.clip_inspector_adapter import FFprobeClipInspectorAdapter
from app.adapters.ffmpeg.mp4_converter_adapter import FFmpegMp4ConverterAdapter, _conversion_timeout_s
from app.core.player.models import ClipInfo


def test_probe_duration_delegates_to_clip_inspector(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    f = tmp_path / "clip.mp4"
    f.write_bytes(b"fake")
    adapter = FFmpegMp4ConverterAdapter()

    monkeypatch.setattr(
        FFprobeClipInspectorAdapter,
        "inspect",
        lambda self, path: ClipInfo(path=path, duration_seconds=49519.74, size_bytes=1),
    )
    assert adapter._probe_duration(f) == 49519.74


def test_probe_duration_returns_zero_on_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    f = tmp_path / "clip.mp4"
    f.write_bytes(b"fake")
    adapter = FFmpegMp4ConverterAdapter()

    def _boom(self, path):
        raise RuntimeError("ffprobe exploded")

    monkeypatch.setattr(FFprobeClipInspectorAdapter, "inspect", _boom)
    assert adapter._probe_duration(f) == 0.0


def _patch_process_plumbing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neutralize the real Job-Object/telemetry side effects convert() has —
    they're defensive against a bogus pid already, but keep the test from
    depending on real OS process-tracking behavior."""
    monkeypatch.setattr("app.adapters.ffmpeg.mp4_converter_adapter.track_process", lambda *a, **kw: None)
    monkeypatch.setattr("app.adapters.ffmpeg.mp4_converter_adapter.untrack_process", lambda *a, **kw: None)
    monkeypatch.setattr("app.adapters.ffmpeg.mp4_converter_adapter.assign_to_batch_job", lambda *a, **kw: None)


def test_conversion_timeout_scales_with_duration() -> None:
    """A 5h source should get a deadline longer than the flat 1h default —
    otherwise a legitimately slow (but progressing) conversion of a large
    file gets killed and reported as a timeout for no real reason. Extracted
    as a pure function specifically so this doesn't need to be inferred from
    mock call args tied to the polling implementation."""
    assert _conversion_timeout_s(0) == 3600.0
    assert _conversion_timeout_s(120) == 3600.0  # short clip still gets the 1h floor
    assert _conversion_timeout_s(5 * 3600) == pytest.approx(5 * 3600 * 2)


def test_convert_kills_process_on_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "huge.mkv"
    source.write_bytes(b"fake")
    adapter = FFmpegMp4ConverterAdapter()
    monkeypatch.setattr(adapter, "_probe_duration", lambda path: 0.0)
    _patch_process_plumbing(monkeypatch)

    proc = MagicMock()
    proc.pid = 4242
    proc.stderr = iter([])
    # First poll times out; the loop then sees the (mocked) deadline has
    # already passed and kills — the post-kill wait() succeeds normally.
    proc.wait.side_effect = [subprocess.TimeoutExpired(cmd="ffmpeg", timeout=0.5), 0]
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: proc)
    monkeypatch.setattr(
        "app.adapters.ffmpeg.mp4_converter_adapter.time.monotonic",
        MagicMock(side_effect=[100.0, 4000.0]),  # deadline=100+3600=3700; 4000 >= 3700
    )

    with pytest.raises(RuntimeError, match="timed out"):
        adapter.convert(source)

    proc.kill.assert_called_once()
    # First wait() raised TimeoutExpired; the second is the post-kill wait().
    assert proc.wait.call_count == 2


def test_convert_cancels_and_kills_process_when_cancel_event_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "huge.mkv"
    source.write_bytes(b"fake")
    adapter = FFmpegMp4ConverterAdapter()
    monkeypatch.setattr(adapter, "_probe_duration", lambda path: 0.0)
    _patch_process_plumbing(monkeypatch)

    cancel_event = threading.Event()
    cancel_event.set()  # already requested before the first poll — deterministic

    proc = MagicMock()
    proc.pid = 4242
    proc.stderr = iter([])
    proc.wait.side_effect = [subprocess.TimeoutExpired(cmd="ffmpeg", timeout=0.5), 0]
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: proc)

    with pytest.raises(RuntimeError, match="[Cc]ancel"):
        adapter.convert(source, cancel_event=cancel_event)

    proc.kill.assert_called_once()
    assert proc.wait.call_count == 2
