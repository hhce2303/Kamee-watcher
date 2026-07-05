"""LiveInferenceService — real-time inference adapter (Fase 4, R-AI).

Wraps a :class:`DetectorPort` (ONNX or mock), polls per-monitor preview
JPEGs written by :class:`FFmpegRecorderAdapter`, applies a :class:`MotionFilter`
gate (Frigate-style two-stage pipeline) and an optional :class:`TrackerPort`,
then notifies subscribers with tracked detections.

Frigate two-stage pattern
─────────────────────────
1. Read preview JPEG from disk (cheap I/O).
2. Decode to grayscale at 160×90 → MotionFilter (pure numpy, ~0.1 ms).
3. If motion score < threshold: skip — ONNX not called.
4. If motion detected: decode JPEG to RGB at model input size → detector.analyze().
5. Apply IouTracker → stable track_ids.
6. Notify subscribers (AutoEventService._on_detections).

Recording is NEVER blocked: the poll loop runs in a daemon thread, and if
inference takes longer than poll_interval the next frame is simply skipped.
"""
from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from loguru import logger

from app.core.analytics.motion_filter import MotionFilter
from app.core.analytics.models import Detection
from app.core.ports.detector_port import DetectorPort
from app.core.ports.tracker_port import TrackerPort


class LiveInferenceService(DetectorPort):
    """DetectorPort wrapper: motion-gated live inference over preview JPEGs.

    *preview_paths* maps ``monitor_index → Path`` of the JPEG written by
    :class:`FFmpegRecorderAdapter` (``preview_fps=2``).

    The wrapped *detector*'s subscriber list is intentionally left empty —
    LiveInferenceService owns its own subscribers and notifies them after
    tracking.  This keeps :class:`BatchClipAnalyzer` (which calls the raw
    detector directly) isolated from the live notification path.
    """

    def __init__(
        self,
        detector: DetectorPort,
        preview_paths: Dict[int, Path],
        motion_threshold: float = 0.015,
        poll_interval: float = 0.5,
        model_input_size: int = 640,
        tracker: Optional[TrackerPort] = None,
    ) -> None:
        self._detector = detector
        self._preview_paths = dict(preview_paths)
        self._motion_threshold = motion_threshold
        self._poll_interval = poll_interval
        self._model_input_size = model_input_size
        self._tracker = tracker
        self._subs: List[Callable[[Sequence[Detection]], None]] = []
        self._motion_filters: Dict[int, MotionFilter] = {}
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    # ── DetectorPort ─────────────────────────────────────────────────────────

    def start(self) -> None:
        self._detector.start()
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="live-inference"
        )
        self._thread.start()
        logger.info(
            "[live] started — monitors={} poll={:.1f}s motion_thr={:.3f}",
            sorted(self._preview_paths.keys()),
            self._poll_interval,
            self._motion_threshold,
        )

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None
        self._detector.stop()
        logger.info("[live] stopped")

    def subscribe(self, callback: Callable[[Sequence[Detection]], None]) -> None:
        self._subs.append(callback)

    def analyze(self, frame: bytes, meta: dict[str, Any]) -> Sequence[Detection]:
        """Passthrough for direct calls (e.g. BatchClipAnalyzer)."""
        return self._detector.analyze(frame, meta)

    # ── Internal ─────────────────────────────────────────────────────────────

    def _loop(self) -> None:
        while not self._stop.wait(self._poll_interval):
            for monitor_idx, preview_path in list(self._preview_paths.items()):
                if self._stop.is_set():
                    return
                self._process_frame(monitor_idx, preview_path)

    def _process_frame(self, monitor_idx: int, preview_path: Path) -> None:
        try:
            jpeg_bytes = preview_path.read_bytes()
        except OSError:
            return

        gray = _jpeg_to_gray(jpeg_bytes)
        if gray is None:
            return

        mf = self._motion_filters.setdefault(
            monitor_idx, MotionFilter(self._motion_threshold)
        )
        score = mf.update(gray)
        if not mf.has_motion(score):
            logger.debug("[live] m{} motion={:.4f} → gate closed", monitor_idx, score)
            return

        rgb_bytes = _jpeg_to_rgb(jpeg_bytes, self._model_input_size)
        if rgb_bytes is None:
            return

        meta: dict[str, Any] = {
            "frame_time": datetime.now(tz=timezone.utc),
            "monitor_index": monitor_idx,
            "width": self._model_input_size,
            "height": self._model_input_size,
        }
        try:
            raw_dets = self._detector.analyze(rgb_bytes, meta)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[live] m{} analyze error: {}", monitor_idx, exc)
            return

        # Tag each detection with its monitor index for downstream zone lookup.
        detections: List[Detection] = [
            d.model_copy(update={"monitor_index": monitor_idx}) for d in raw_dets
        ]

        if self._tracker and detections:
            detections = self._tracker.update(detections)

        if detections:
            logger.debug(
                "[live] m{} motion={:.3f} → {} detections", monitor_idx, score, len(detections)
            )
            for cb in list(self._subs):
                cb(detections)


def _jpeg_to_gray(jpeg_bytes: bytes, width: int = 160, height: int = 90) -> Optional[np.ndarray]:
    """Decode JPEG to downscaled grayscale ndarray (for motion filter)."""
    try:
        from PIL import Image  # type: ignore[import-untyped]
        import io
        img = Image.open(io.BytesIO(jpeg_bytes)).convert("L").resize((width, height))
        return np.asarray(img, dtype=np.uint8)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[live] JPEG→gray decode error: {}", exc)
        return None


def _jpeg_to_rgb(jpeg_bytes: bytes, size: int = 640) -> Optional[bytes]:
    """Decode JPEG to raw RGB24 bytes at *size*×*size* (for ONNX inference)."""
    try:
        from PIL import Image  # type: ignore[import-untyped]
        import io
        img = Image.open(io.BytesIO(jpeg_bytes)).convert("RGB").resize((size, size))
        return img.tobytes()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[live] JPEG→RGB decode error: {}", exc)
        return None
