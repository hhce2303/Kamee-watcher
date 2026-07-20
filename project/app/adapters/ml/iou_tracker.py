"""IOU-based multi-object tracker (SORT-lite) — TrackerPort adapter (Fase 4).

Greedy IoU matching between consecutive detection sets.  No Kalman filter:
at ≤2 fps constant-velocity prediction adds minimal value and the simplicity
is worth the trade-off.  Pure Python + numpy; no scipy required.

Track lifecycle
───────────────
- New detection with no IoU match → new track (next_id++).
- Detection that matches a track (IoU ≥ iou_threshold) → track updated,
  age reset to 0, hits incremented.
- Track not matched for > max_age frames → evicted.
- Track with hits < min_hits → ID still emitted but caller may wish to filter
  tentative tracks (default min_hits=1 means all IDs are immediately stable).
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np
from loguru import logger

from app.core.analytics.models import BoundingBox, Detection
from app.core.ports.tracker_port import TrackerPort


@dataclass
class _Track:
    track_id: int
    bbox: np.ndarray   # (x1, y1, x2, y2) normalised float32
    class_name: str
    age: int = 0       # frames since last successful match
    hits: int = 1      # total matched frames


def _to_xyxy(b: BoundingBox) -> np.ndarray:
    return np.array([b.x, b.y, b.x + b.w, b.y + b.h], dtype=np.float32)


def _iou_matrix(tracks: List[_Track], det_boxes: np.ndarray) -> np.ndarray:
    """IoU between every (track, detection) pair.  Returns (T × D) float32."""
    if not tracks or det_boxes.shape[0] == 0:
        return np.zeros((len(tracks), det_boxes.shape[0]), dtype=np.float32)
    t_boxes = np.stack([t.bbox for t in tracks])  # (T, 4)
    d_boxes = det_boxes                            # (D, 4)
    xx1 = np.maximum(t_boxes[:, None, 0], d_boxes[None, :, 0])
    yy1 = np.maximum(t_boxes[:, None, 1], d_boxes[None, :, 1])
    xx2 = np.minimum(t_boxes[:, None, 2], d_boxes[None, :, 2])
    yy2 = np.minimum(t_boxes[:, None, 3], d_boxes[None, :, 3])
    inter = np.maximum(0.0, xx2 - xx1) * np.maximum(0.0, yy2 - yy1)
    area_t = (t_boxes[:, 2] - t_boxes[:, 0]) * (t_boxes[:, 3] - t_boxes[:, 1])
    area_d = (d_boxes[:, 2] - d_boxes[:, 0]) * (d_boxes[:, 3] - d_boxes[:, 1])
    union = area_t[:, None] + area_d[None, :] - inter + 1e-7
    return (inter / union).astype(np.float32)


class IouTracker(TrackerPort):
    """Greedy IoU multi-object tracker (O(T·D) per frame).

    Args:
        iou_threshold: minimum IoU to consider two boxes the same object.
        max_age: frames a track may go unmatched before being evicted.
        min_hits: minimum matched frames before a track emits an ID.
    """

    def __init__(
        self,
        iou_threshold: float = 0.3,
        max_age: int = 5,
        min_hits: int = 1,
    ) -> None:
        self._iou_threshold = iou_threshold
        self._max_age = max_age
        self._min_hits = min_hits
        self._tracks: List[_Track] = []
        self._next_id = 1

    def update(self, detections: Sequence[Detection]) -> List[Detection]:
        if not detections:
            for t in self._tracks:
                t.age += 1
            self._tracks = [t for t in self._tracks if t.age <= self._max_age]
            return []

        det_list = list(detections)
        det_boxes = np.stack([_to_xyxy(d.bbox) for d in det_list])  # (D, 4)
        iou_mat = _iou_matrix(self._tracks, det_boxes)               # (T, D)

        matched_tracks: set[int] = set()
        matched_dets: set[int] = set()
        det_to_tid: Dict[int, int] = {}

        # Greedy: process pairs in descending IoU order
        if iou_mat.size > 0:
            for flat_idx in np.argsort(iou_mat.ravel())[::-1]:
                t_idx, d_idx = divmod(int(flat_idx), len(det_list))
                if iou_mat[t_idx, d_idx] < self._iou_threshold:
                    break
                if t_idx in matched_tracks or d_idx in matched_dets:
                    continue
                matched_tracks.add(t_idx)
                matched_dets.add(d_idx)
                trk = self._tracks[t_idx]
                trk.bbox = det_boxes[d_idx]
                trk.class_name = det_list[d_idx].class_name
                trk.age = 0
                trk.hits += 1
                det_to_tid[d_idx] = trk.track_id

        # Age unmatched tracks; evict stale ones
        for i, t in enumerate(self._tracks):
            if i not in matched_tracks:
                t.age += 1
        self._tracks = [t for t in self._tracks if t.age <= self._max_age]

        # Spawn new tracks for unmatched detections
        for d_idx, det in enumerate(det_list):
            if d_idx not in matched_dets:
                trk = _Track(
                    track_id=self._next_id,
                    bbox=det_boxes[d_idx],
                    class_name=det.class_name,
                )
                self._next_id += 1
                self._tracks.append(trk)
                det_to_tid[d_idx] = trk.track_id

        # Build result with stable track_ids; respect min_hits gate
        result: List[Detection] = []
        for d_idx, det in enumerate(det_list):
            tid = det_to_tid.get(d_idx)
            trk = next((t for t in self._tracks if t.track_id == tid), None)
            if trk is not None and trk.hits >= self._min_hits:
                result.append(det.model_copy(update={"track_id": tid}))
            else:
                result.append(det)
        return result

    def reset(self) -> None:
        self._tracks.clear()
        self._next_id = 1
        logger.debug("[tracker] reset")
