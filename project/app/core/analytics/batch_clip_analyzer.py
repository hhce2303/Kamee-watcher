"""BatchClipAnalyzer (Fase 3, R-AI): analyze closed clips out-of-process.

When a recording clip is finalized, call :meth:`queue_clip` to schedule it for
inference.  A single background thread drains the queue, extracts frames at
*frame_interval_seconds* via FFmpeg (rawvideo RGB24, pre-scaled to the model's
input resolution), and feeds each frame to :class:`DetectorPort`.

Detections above the confidence threshold are converted to :class:`AnalyticEvent`
objects (``source="auto:yolo"``) with ``clip_path`` pointing to the source clip —
no new clip is built because the footage already exists.

Recording is never blocked — all decode/inference runs on the background thread.
"""
from __future__ import annotations

import queue
import subprocess
import threading
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from app.adapters.ffmpeg.clip_window import parse_clip_start as _shared_parse_clip_start
from app.adapters.ffmpeg.ffmpeg_path import resolve_ffmpeg
from app.adapters.ffmpeg.process_guard import assign_to_batch_job, batch_slot
from app.core.analytics.models import AnalyticEvent, Detection
from app.core.ports.detector_port import DetectorPort
from app.infrastructure.proc_telemetry import track_process, untrack_process


class BatchClipAnalyzer:
    """Analyze closed recording clips using a :class:`DetectorPort` in background."""

    def __init__(
        self,
        detector: DetectorPort,
        on_batch_event: Callable[[AnalyticEvent, Path], None],
        confidence_threshold: float = 0.6,
        cooldown_seconds: int = 30,
        frame_interval_seconds: int = 1,
        input_width: int = 640,
        input_height: int = 640,
    ) -> None:
        self._detector = detector
        self._on_event = on_batch_event
        self._threshold = confidence_threshold
        self._cooldown = cooldown_seconds
        self._frame_interval = frame_interval_seconds
        self._input_w = input_width
        self._input_h = input_height
        self._queue: queue.Queue[Optional[tuple[Path, Optional[datetime]]]] = queue.Queue()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._detector.start()
        self._thread = threading.Thread(
            target=self._worker, name="batch-clip-analyzer", daemon=True
        )
        self._thread.start()
        logger.info("[batch-analyzer] started (interval={}s)", self._frame_interval)

    def stop(self) -> None:
        self._queue.put(None)  # sentinel — drains and exits
        if self._thread:
            self._thread.join(timeout=10.0)
        self._detector.stop()
        logger.info("[batch-analyzer] stopped")

    def queue_clip(self, clip_path: Path, clip_start: Optional[datetime] = None) -> None:
        """Schedule a closed clip for analysis (non-blocking)."""
        self._queue.put((clip_path, clip_start))
        logger.debug("[batch-analyzer] queued {}", clip_path.name)

    # ── Internal ─────────────────────────────────────────────────────────────

    def _worker(self) -> None:
        while True:
            item = self._queue.get()
            if item is None:
                break
            clip_path, clip_start = item
            try:
                self._analyze_clip(clip_path, clip_start)
            except Exception as exc:  # noqa: BLE001
                logger.warning("[batch-analyzer] error on {}: {}", clip_path.name, exc)

    def _analyze_clip(self, clip_path: Path, clip_start: Optional[datetime]) -> None:
        if clip_start is None:
            clip_start = _parse_clip_start(clip_path)

        logger.info("[batch-analyzer] analyzing {} (start={})", clip_path.name, clip_start)

        ffmpeg = resolve_ffmpeg()
        frame_bytes = self._input_w * self._input_h * 3
        fps_expr = f"1/{self._frame_interval}" if self._frame_interval > 1 else "1"
        scale_filter = (
            f"fps={fps_expr},"
            f"scale={self._input_w}:{self._input_h}"
            ":force_original_aspect_ratio=decrease,"
            f"pad={self._input_w}:{self._input_h}:(ow-iw)/2:(oh-ih)/2"
        )
        cmd = [
            ffmpeg, "-i", str(clip_path),
            "-vf", scale_filter,
            "-f", "rawvideo",
            "-pix_fmt", "rgb24",
            "pipe:1",
        ]

        last_event_at: Optional[datetime] = None
        frame_idx = 0

        with batch_slot():
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            assign_to_batch_job(proc)
            track_process(proc.pid, category="batch", label="batch_analyzer")
            try:
                while True:
                    chunk = proc.stdout.read(frame_bytes)  # type: ignore[union-attr]
                    if len(chunk) < frame_bytes:
                        break

                    frame_time = clip_start + timedelta(
                        seconds=frame_idx * self._frame_interval
                    )
                    meta: dict[str, Any] = {
                        "frame_time": frame_time,
                        "monitor_index": 0,
                        "width": self._input_w,
                        "height": self._input_h,
                    }
                    detections = self._detector.analyze(chunk, meta)
                    last_event_at = self._maybe_emit(
                        detections, frame_time, clip_path, last_event_at
                    )
                    frame_idx += 1
            finally:
                untrack_process(proc.pid)
                proc.stdout.close()  # type: ignore[union-attr]
                proc.wait()

        logger.info("[batch-analyzer] done {} ({} frames)", clip_path.name, frame_idx)

    def _maybe_emit(
        self,
        detections: Sequence[Detection],
        frame_time: datetime,
        clip_path: Path,
        last_event_at: Optional[datetime],
    ) -> Optional[datetime]:
        """Emit an event if threshold + cooldown pass. Returns updated last_event_at."""
        best = max(detections, key=lambda d: d.confidence, default=None)
        if best is None or best.confidence < self._threshold:
            return last_event_at

        if last_event_at is not None:
            elapsed = (frame_time - last_event_at).total_seconds()
            if elapsed < self._cooldown:
                logger.debug(
                    "[batch-analyzer] suppressed — cooldown ({:.0f}s left)",
                    self._cooldown - elapsed,
                )
                return last_event_at

        event = AnalyticEvent(
            event_id=frame_time.strftime("%Y%m%d%H%M%S%f"),
            type=best.class_name,
            source="auto:yolo",
            start=frame_time,
            end=frame_time,
            confidence=best.confidence,
            track_id=best.track_id,
            detections=tuple(detections),
            clip_path=clip_path,
        )
        logger.info(
            "[batch-analyzer] {} (conf={:.2f}) at {} in {}",
            best.class_name, best.confidence, frame_time, clip_path.name,
        )
        self._on_event(event, clip_path)
        return frame_time


def _parse_clip_start(clip_path: Path) -> datetime:
    """Extract start time from filenames like ``2026-07-04_12-00-00_m0.mp4``.

    Falls back to UTC now if the name cannot be parsed.
    """
    parsed = _shared_parse_clip_start(clip_path)
    if parsed is None:
        logger.warning(
            "[batch-analyzer] cannot parse start time from '{}' — using now", clip_path.stem
        )
        return datetime.now(tz=timezone.utc)
    return parsed
