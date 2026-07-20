"""MjpegPreviewServerAdapter — operator-only localhost HTTP preview server.

Serves live screen-preview JPEG frames written by the FFmpeg recorder.  Runs
entirely in a daemon thread; the main process never blocks.

Routes
------
GET /health               → JSON health check
GET /preview/m{index}     → single JPEG snapshot (no-cache)
GET /stream/m{index}      → MJPEG stream (multipart/x-mixed-replace, ~2 fps)

Security
--------
* Binds only to ``127.0.0.1`` — never reachable over the network.
* Monitor index is validated with a strict regex (1-2 digits) before any path
  is constructed to prevent path traversal.
* CORS header is set to ``*`` — acceptable because the server is localhost-only;
  an external origin cannot reach it across NAT.
"""
from __future__ import annotations

import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from app.core.ports.preview_server_port import PreviewServerPort

if TYPE_CHECKING:
    from app.infrastructure.config import Settings

# ── Constants ──────────────────────────────────────────────────────────────
_BOUNDARY = b"frame"
_FRAME_INTERVAL = 0.5          # seconds between MJPEG frames (matches FFmpeg preview_fps=2)
_MONITOR_INDEX_RE = re.compile(r"^\d{1,2}$")  # 0–99 only
_JPEG_SOI = b"\xff\xd8"        # JPEG Start-Of-Image magic (2 bytes)
_JPEG_EOI = b"\xff\xd9"        # JPEG End-Of-Image (2 bytes)


class MjpegPreviewServerAdapter(PreviewServerPort):
    """Stdlib HTTP MJPEG server that serves preview JPEGs from segments/m{N}/."""

    def __init__(self, settings: "Settings") -> None:
        self._host: str = settings.preview_http_host
        self._port: int = settings.preview_http_port
        self._segment_dir: Path = settings.segment_dir
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._running = False

    # ── PreviewServerPort ──────────────────────────────────────────────

    def start(self) -> None:
        if self._running:
            return
        try:
            handler = _make_handler(self._segment_dir)
            self._server = ThreadingHTTPServer((self._host, self._port), handler)
            self._thread = threading.Thread(
                target=self._server.serve_forever,
                name="preview-http",
                daemon=True,
            )
            self._thread.start()
            self._running = True
            logger.info(
                "[preview-server] listening on {} — MJPEG at /stream/m{{index}}",
                self.base_url,
            )
        except OSError as exc:
            # Port in use or permission denied — log and continue; recording still works.
            logger.error(
                "[preview-server] failed to bind {}:{} — {}", self._host, self._port, exc
            )

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server = None
        self._running = False
        logger.info("[preview-server] stopped.")

    @property
    def base_url(self) -> str:
        return f"http://{self._host}:{self._port}"

    @property
    def is_running(self) -> bool:
        return self._running and self._thread is not None and self._thread.is_alive()


# ── JPEG integrity helper ─────────────────────────────────────────────────

def _read_valid_jpeg(path: Path, retries: int = 1) -> bytes | None:
    """Read *path* and return its bytes only if it looks like a complete JPEG.

    FFmpeg overwrites preview.jpg in-place (no atomic rename), so we may catch
    it mid-write.  We retry up to *retries* times with a short sleep before
    giving up and returning None.  The caller skips sending broken frames.
    """
    for attempt in range(max(retries, 1)):
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            return None
        if (
            len(data) >= 4
            and data[:2] == _JPEG_SOI
            and data[-2:] == _JPEG_EOI
        ):
            return data
        # Partial write — short sleep before retry
        if attempt < retries - 1:
            time.sleep(0.05)
    return None  # still not a valid JPEG after all retries


# ── HTTP handler factory ───────────────────────────────────────────────────

def _make_handler(segment_dir: Path):
    """Return a handler class that closes over *segment_dir*."""

    class _PreviewHandler(BaseHTTPRequestHandler):
        _seg_dir = segment_dir

        # Silence default access log — loguru owns all output.
        def log_message(self, fmt, *args):  # noqa: N802
            pass

        def log_error(self, fmt, *args):  # noqa: N802
            logger.debug("[preview-server] {}", fmt % args)

        def do_GET(self):  # noqa: N802
            path = self.path.split("?")[0]  # strip query string

            if path in ("/", "/monitors"):
                self._index_page()
            elif path == "/health":
                self._health()
            elif path.startswith("/preview/m"):
                idx = path[len("/preview/m"):]
                self._snapshot(idx)
            elif path.startswith("/stream/m"):
                idx = path[len("/stream/m"):]
                self._stream(idx)
            else:
                self._not_found()

        # ── Route handlers ─────────────────────────────────────────────

        def _index_page(self):
            # Discover which monitor dirs have a preview.jpg
            monitors = sorted(
                int(d.name[1:])
                for d in self._seg_dir.iterdir()
                if d.is_dir()
                and _MONITOR_INDEX_RE.match(d.name[1:])
                and d.name.startswith("m")
                and (d / "preview.jpg").exists()
            ) if self._seg_dir.exists() else []

            tiles = "".join(
                f"""<div class="tile">
                  <p>Monitor {idx}</p>
                  <img src="/stream/m{idx}" alt="Monitor {idx}">
                </div>"""
                for idx in monitors
            ) or "<p class='empty'>No hay pantallas activas aún. Inicia la grabación.</p>"

            host = self.headers.get("Host", "127.0.0.1:8787")
            body = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>The Watcher — Preview en vivo</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0 }}
    body {{ background: #0d0d0d; color: #e0e0e0; font-family: system-ui, sans-serif; padding: 24px }}
    h1 {{ font-size: 18px; font-weight: 600; margin-bottom: 4px }}
    .sub {{ font-size: 12px; color: #666; margin-bottom: 24px }}
    .grid {{ display: flex; flex-wrap: wrap; gap: 16px }}
    .tile {{ background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 8px;
             padding: 12px; min-width: 320px; flex: 1 }}
    .tile p {{ font-size: 11px; color: #888; margin-bottom: 8px; text-transform: uppercase;
               letter-spacing: .06em }}
    .tile img {{ width: 100%; display: block; border-radius: 4px; background: #111 }}
    .empty {{ color: #555; font-size: 13px }}
  </style>
</head>
<body>
  <h1>The Watcher — Preview en vivo</h1>
  <p class="sub">Operador &bull; {host} &bull; ~2 fps MJPEG</p>
  <div class="grid">{tiles}</div>
  <script>
    // Reload the page when a new monitor appears (poll every 5s)
    setTimeout(() => location.reload(), 5000);
  </script>
</body>
</html>""".encode()
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(body)

        def _health(self):
            body = json.dumps({"status": "ok", "role": "operator"}).encode()
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _snapshot(self, idx: str):
            jpeg_path = self._resolve_preview(idx)
            if jpeg_path is None:
                self._not_found()
                return
            data = _read_valid_jpeg(jpeg_path)
            if data is None:
                self._not_found()
                return
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()
            self.wfile.write(data)

        def _stream(self, idx: str):
            jpeg_path = self._resolve_preview(idx)
            if jpeg_path is None:
                self._not_found()
                return
            self.send_response(200)
            self._cors()
            self.send_header(
                "Content-Type",
                f"multipart/x-mixed-replace; boundary={_BOUNDARY.decode()}",
            )
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()
            try:
                while True:
                    data = _read_valid_jpeg(jpeg_path, retries=3)
                    if data is None:
                        # Monitor inactive or file still being written — wait without sending a broken frame.
                        time.sleep(_FRAME_INTERVAL)
                        continue
                    frame_header = (
                        b"--" + _BOUNDARY + b"\r\n"
                        b"Content-Type: image/jpeg\r\n"
                        b"Content-Length: " + str(len(data)).encode() + b"\r\n"
                        b"\r\n"
                    )
                    try:
                        self.wfile.write(frame_header)
                        self.wfile.write(data)
                        self.wfile.write(b"\r\n")
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError):
                        # Client disconnected — exit the stream loop cleanly.
                        break
                    time.sleep(_FRAME_INTERVAL)
            except Exception:  # noqa: BLE001
                pass  # Any other error terminates this stream; never crashes the server.

        def _not_found(self):
            self.send_response(404)
            self._cors()
            self.end_headers()

        def _cors(self):
            self.send_header("Access-Control-Allow-Origin", "*")

        def _resolve_preview(self, idx: str) -> Path | None:
            """Validate *idx* and return the JPEG path, or None on invalid input."""
            if not _MONITOR_INDEX_RE.match(idx):
                return None
            return self._seg_dir / f"m{idx}" / "preview.jpg"

    return _PreviewHandler
