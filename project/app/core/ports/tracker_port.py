"""Port: multi-object tracker — assigns stable IDs across frames (Fase 4)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import List

from app.core.analytics.models import Detection


class TrackerPort(ABC):
    """Stateful multi-object tracker.

    Each call to :meth:`update` processes one batch of per-frame detections
    and returns the same detections with stable ``track_id`` values assigned.
    IDs must be consistent across consecutive frames: a person visible for
    10 frames should carry the same ``track_id`` throughout.
    """

    @abstractmethod
    def update(self, detections: Sequence[Detection]) -> List[Detection]:
        """Match *detections* to existing tracks; return them with track_id set."""

    @abstractmethod
    def reset(self) -> None:
        """Clear all track state (e.g. after a scene change or restart)."""
