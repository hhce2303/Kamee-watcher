"""MotionFilter — frame-diff motion gate (Fase 4, R-AI).

Pure numpy, no image-decode dependency.  The adapter layer (LiveInferenceService)
handles JPEG decoding and passes a downscaled grayscale H×W uint8 array here.

This is the "cheap CPU gate" in the Frigate two-stage pattern: motion detected
here → ONNX inference triggered; no motion → ONNX skipped entirely.
"""
from __future__ import annotations

from typing import Optional

import numpy as np


class MotionFilter:
    """Two-frame absolute-diff motion detector.

    Args:
        threshold: minimum fraction of changed pixels [0..1] to count as motion.
            0.015 (~1.5 %) works well for a static operator station; raise it in
            noisy environments (flickering monitors, AC vents).
        pixel_threshold: absolute grayscale diff per pixel (0-255) above which a
            pixel is counted as "changed".
    """

    def __init__(
        self,
        threshold: float = 0.015,
        pixel_threshold: int = 25,
    ) -> None:
        if not 0.0 < threshold <= 1.0:
            raise ValueError(f"threshold must be in (0, 1], got {threshold!r}")
        self._threshold = threshold
        self._pixel_threshold = pixel_threshold
        self._prev: Optional[np.ndarray] = None

    def update(self, gray: np.ndarray) -> float:
        """Return motion score 0..1 (fraction of pixels that changed).

        *gray* must be a uint8 H×W array.  Returns 0.0 on the first call or
        when the frame shape changes (e.g. after a monitor-resolution switch).
        """
        if self._prev is None or self._prev.shape != gray.shape:
            self._prev = gray.copy()
            return 0.0
        diff = np.abs(gray.astype(np.int16) - self._prev.astype(np.int16))
        score = float(np.mean(diff > self._pixel_threshold))
        self._prev = gray.copy()
        return score

    def has_motion(self, score: float) -> bool:
        return score >= self._threshold

    def reset(self) -> None:
        """Clear previous frame (call after a recording gap or monitor change)."""
        self._prev = None
