"""Tests for MjpegPreviewServerAdapter (operator-only localhost MJPEG server)."""
from __future__ import annotations

import socket
import time
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.adapters.preview_server.mjpeg_server_adapter import MjpegPreviewServerAdapter


# ── Helpers ──────────────────────────────────────────────────────────────────

def _free_port() -> int:
    """Return an unused TCP port on localhost."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _make_adapter(tmp_path: Path, port: int) -> MjpegPreviewServerAdapter:
    """Build an adapter wired to *tmp_path* as the segment directory."""
    settings = MagicMock()
    settings.preview_http_host = "127.0.0.1"
    settings.preview_http_port = port
    settings.segment_dir = tmp_path
    return MjpegPreviewServerAdapter(settings)


def _wait_up(port: int, timeout: float = 2.0) -> bool:
    """Poll until port accepts connections or *timeout* expires."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                return True
        except OSError:
            time.sleep(0.05)
    return False


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestMjpegPreviewServerLifecycle:
    def test_start_and_stop(self, tmp_path: Path) -> None:
        port = _free_port()
        adapter = _make_adapter(tmp_path, port)

        adapter.start()
        assert _wait_up(port), "server did not become reachable after start()"
        assert adapter.is_running

        adapter.stop()
        # Allow the thread a moment to wind down.
        time.sleep(0.1)
        assert not adapter.is_running

    def test_start_is_idempotent(self, tmp_path: Path) -> None:
        port = _free_port()
        adapter = _make_adapter(tmp_path, port)
        try:
            adapter.start()
            adapter.start()  # second call must not raise or create a second server
            assert adapter.is_running
        finally:
            adapter.stop()

    def test_base_url(self, tmp_path: Path) -> None:
        port = _free_port()
        adapter = _make_adapter(tmp_path, port)
        assert adapter.base_url == f"http://127.0.0.1:{port}"


class TestHealthEndpoint:
    def test_health_returns_200_json(self, tmp_path: Path) -> None:
        port = _free_port()
        adapter = _make_adapter(tmp_path, port)
        adapter.start()
        _wait_up(port)
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health") as resp:
                assert resp.status == 200
                body = resp.read()
                assert b"ok" in body
                assert b"operator" in body
        finally:
            adapter.stop()


class TestSnapshotEndpoint:
    def test_snapshot_returns_jpeg_when_file_exists(self, tmp_path: Path) -> None:
        port = _free_port()
        # Write a minimal valid JPEG-like payload (just header bytes).
        monitor_dir = tmp_path / "m0"
        monitor_dir.mkdir()
        # _read_valid_jpeg() requires both SOI and EOI markers — must end in \xff\xd9.
        jpeg_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 18 + b"\xff\xd9"
        (monitor_dir / "preview.jpg").write_bytes(jpeg_bytes)

        adapter = _make_adapter(tmp_path, port)
        adapter.start()
        _wait_up(port)
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/preview/m0"
            ) as resp:
                assert resp.status == 200
                assert resp.read() == jpeg_bytes
        finally:
            adapter.stop()

    def test_snapshot_returns_404_when_file_missing(self, tmp_path: Path) -> None:
        port = _free_port()
        adapter = _make_adapter(tmp_path, port)
        adapter.start()
        _wait_up(port)
        try:
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/preview/m0")
            assert exc_info.value.code == 404
        finally:
            adapter.stop()


class TestInvalidIndex:
    @pytest.mark.parametrize("bad_idx", ["../etc/passwd", "abc", "", "100", "0drop"])
    def test_invalid_index_returns_404(self, tmp_path: Path, bad_idx: str) -> None:
        port = _free_port()
        adapter = _make_adapter(tmp_path, port)
        adapter.start()
        _wait_up(port)
        try:
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/preview/m{bad_idx}"
                )
            assert exc_info.value.code == 404
        finally:
            adapter.stop()


class TestMjpegStream:
    def test_stream_sends_multipart_header(self, tmp_path: Path) -> None:
        port = _free_port()
        # Provide a real preview file so the loop sends at least one frame.
        monitor_dir = tmp_path / "m1"
        monitor_dir.mkdir()
        # _read_valid_jpeg() requires both SOI and EOI markers — must end in \xff\xd9.
        (monitor_dir / "preview.jpg").write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 8 + b"\xff\xd9")

        adapter = _make_adapter(tmp_path, port)
        adapter.start()
        _wait_up(port)
        try:
            # Open the stream and read just enough to verify the MJPEG boundary.
            # A recv() timeout is required: if the server ever again fails to
            # emit a frame (e.g. a future _read_valid_jpeg regression), recv()
            # would otherwise block forever with no way for the deadline loop
            # below to interrupt it, hanging the whole test run.
            conn = socket.create_connection(("127.0.0.1", port))
            conn.settimeout(0.2)
            conn.sendall(b"GET /stream/m1 HTTP/1.0\r\nHost: 127.0.0.1\r\n\r\n")
            raw = b""
            deadline = time.monotonic() + 3.0
            while time.monotonic() < deadline and b"--frame" not in raw:
                try:
                    chunk = conn.recv(4096)
                except socket.timeout:
                    continue
                if not chunk:
                    break
                raw += chunk
            conn.close()
            assert b"multipart/x-mixed-replace" in raw
            assert b"--frame" in raw
        finally:
            adapter.stop()
