"""FFprobeClipInspectorAdapter — duration-scan fallback for containers with no
duration in their header (e.g. an interrupted/never-finalized live-muxed
recording, "File ended prematurely"). See _scan_duration's docstring for why
a stream-copy demux is the right fallback instead of just rejecting the file.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.adapters.ffmpeg.clip_inspector_adapter import FFprobeClipInspectorAdapter


def _fake_ffprobe_result(fmt: dict, streams: list | None = None) -> MagicMock:
    payload = {"format": fmt, "streams": streams or []}
    return MagicMock(returncode=0, stdout=json.dumps(payload).encode("utf-8"), stderr=b"")


def test_inspect_uses_header_duration_when_present(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    f = tmp_path / "clip.mp4"
    f.write_bytes(b"fake")
    adapter = FFprobeClipInspectorAdapter()
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return _fake_ffprobe_result({"duration": "12.5"})

    monkeypatch.setattr(subprocess, "run", fake_run)
    info = adapter.inspect(f)

    assert info.duration_seconds == 12.5
    assert len(calls) == 1  # never fell back to the scan — fast path only


def test_inspect_falls_back_to_scan_when_header_duration_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    f = tmp_path / "raw.mkv"
    f.write_bytes(b"fake")
    adapter = FFprobeClipInspectorAdapter()

    def fake_run(cmd, **kwargs):
        if "-show_format" in cmd:
            return _fake_ffprobe_result({})  # no "duration" key at all
        # the ffmpeg -c copy -f null - scan, mirroring real output on a
        # truncated Matroska recording (verified manually against a real
        # 13h45m/15.5GB interrupted capture).
        stderr = (
            b"frame=100 fps=0 q=-1.0 size=N/A time=13:45:19.74 bitrate=N/A speed=600x\n"
            b"[in#0/matroska,webm] File ended prematurely\n"
        )
        return MagicMock(returncode=0, stdout=b"", stderr=stderr)

    monkeypatch.setattr(subprocess, "run", fake_run)
    info = adapter.inspect(f)

    assert info.duration_seconds == pytest.approx(13 * 3600 + 45 * 60 + 19.74)


def test_scan_duration_returns_zero_on_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    f = tmp_path / "raw.mkv"
    f.write_bytes(b"fake")
    adapter = FFprobeClipInspectorAdapter()

    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=600)

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert adapter._scan_duration(f) == 0.0


def test_scan_duration_returns_zero_when_no_time_progress_at_all(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    f = tmp_path / "raw.mkv"
    f.write_bytes(b"fake")
    adapter = FFprobeClipInspectorAdapter()

    monkeypatch.setattr(
        subprocess, "run", lambda cmd, **kwargs: MagicMock(returncode=1, stdout=b"", stderr=b"no streams found")
    )
    assert adapter._scan_duration(f) == 0.0
