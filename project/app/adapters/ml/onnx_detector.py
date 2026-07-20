"""ONNX detector adapter (Fase 3, R-AI): DetectorPort backed by onnxruntime.

Supports YOLOv8 (output [1, 84+, 8400]) and YOLOv5 (output [1, 25200, 85])
ONNX formats — auto-detected from output shape.

Input frames must be raw RGB24 bytes pre-scaled to the model's input resolution
(default 640×640).  Supply ``width``/``height`` in *meta* so the adapter can
reshape the buffer without an image-decode dependency.  :class:`BatchClipAnalyzer`
produces the correct format via ffmpeg rawvideo output.

Execution providers (tried in order):
  - "directml" → DmlExecutionProvider → CPUExecutionProvider
  - "cuda"      → CUDAExecutionProvider → CPUExecutionProvider
  - "cpu"       → CPUExecutionProvider only

The model is not loaded until ``start()``; ``stop()`` releases the session.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, List, Optional

import numpy as np
from loguru import logger

from app.core.analytics.models import BoundingBox, Detection
from app.core.ports.detector_port import DetectorPort

# COCO 80-class names — default for models trained on COCO (YOLOv5/v8 base).
_COCO_NAMES: list[str] = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train",
    "truck", "boat", "traffic light", "fire hydrant", "stop sign",
    "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep",
    "cow", "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella",
    "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard",
    "sports ball", "kite", "baseball bat", "baseball glove", "skateboard",
    "surfboard", "tennis racket", "bottle", "wine glass", "cup", "fork",
    "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange",
    "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair",
    "couch", "potted plant", "bed", "dining table", "toilet", "tv",
    "laptop", "mouse", "remote", "keyboard", "cell phone", "microwave",
    "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase",
    "scissors", "teddy bear", "hair drier", "toothbrush",
]

_PROVIDER_MAP: dict[str, list[str]] = {
    "directml": ["DmlExecutionProvider", "CPUExecutionProvider"],
    "cuda":     ["CUDAExecutionProvider", "CPUExecutionProvider"],
    "cpu":      ["CPUExecutionProvider"],
}


def _nms(boxes: np.ndarray, scores: np.ndarray, iou_threshold: float) -> list[int]:
    """Greedy IoU-based NMS. Returns sorted-by-score indices to keep."""
    if len(boxes) == 0:
        return []
    x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
    areas = (x2 - x1) * (y2 - y1)
    order = scores.argsort()[::-1]
    keep: list[int] = []
    while order.size > 0:
        i = int(order[0])
        keep.append(i)
        if order.size == 1:
            break
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        inter = np.maximum(0.0, xx2 - xx1) * np.maximum(0.0, yy2 - yy1)
        iou = inter / (areas[i] + areas[order[1:]] - inter + 1e-7)
        order = order[1:][iou < iou_threshold]
    return keep


def _parse_yolov8(
    output: np.ndarray,
    conf_threshold: float,
    input_w: int,
    input_h: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Parse YOLOv8 ONNX output [1, 4+C, N] → (xyxy_norm, confs, class_ids)."""
    preds = output[0].T                          # [N, 4+C]
    boxes_xywh = preds[:, :4]                    # cx, cy, w, h in pixel coords
    class_scores = preds[:, 4:]                  # [N, C]
    class_ids = class_scores.argmax(axis=1)
    confs = class_scores[np.arange(len(class_ids)), class_ids]

    mask = confs >= conf_threshold
    if not mask.any():
        return np.empty((0, 4)), np.empty(0), np.empty(0, dtype=int)

    bxywh = boxes_xywh[mask]
    conf_f = confs[mask]
    cls_f = class_ids[mask]

    # Pixel coords → normalised xyxy
    x1 = np.clip((bxywh[:, 0] - bxywh[:, 2] / 2) / input_w, 0.0, 1.0)
    y1 = np.clip((bxywh[:, 1] - bxywh[:, 3] / 2) / input_h, 0.0, 1.0)
    x2 = np.clip((bxywh[:, 0] + bxywh[:, 2] / 2) / input_w, 0.0, 1.0)
    y2 = np.clip((bxywh[:, 1] + bxywh[:, 3] / 2) / input_h, 0.0, 1.0)
    return np.stack([x1, y1, x2, y2], axis=1), conf_f, cls_f.astype(int)


def _parse_yolov5(
    output: np.ndarray,
    conf_threshold: float,
    input_w: int,
    input_h: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Parse YOLOv5 ONNX output [1, N, 5+C] → (xyxy_norm, confs, class_ids)."""
    preds = output[0]                            # [N, 5+C]
    obj_conf = preds[:, 4]
    class_scores = preds[:, 5:]
    class_ids = class_scores.argmax(axis=1)
    confs = obj_conf * class_scores[np.arange(len(class_ids)), class_ids]

    mask = confs >= conf_threshold
    if not mask.any():
        return np.empty((0, 4)), np.empty(0), np.empty(0, dtype=int)

    bxywh = preds[mask, :4]
    conf_f = confs[mask]
    cls_f = class_ids[mask]

    x1 = np.clip((bxywh[:, 0] - bxywh[:, 2] / 2) / input_w, 0.0, 1.0)
    y1 = np.clip((bxywh[:, 1] - bxywh[:, 3] / 2) / input_h, 0.0, 1.0)
    x2 = np.clip((bxywh[:, 0] + bxywh[:, 2] / 2) / input_w, 0.0, 1.0)
    y2 = np.clip((bxywh[:, 1] + bxywh[:, 3] / 2) / input_h, 0.0, 1.0)
    return np.stack([x1, y1, x2, y2], axis=1), conf_f, cls_f.astype(int)


class OnnxDetectorAdapter(DetectorPort):
    """DetectorPort backed by an ONNX model (YOLOv8 or YOLOv5 format).

    *frame* passed to :meth:`analyze` must be raw RGB24 bytes at
    ``meta['width']`` × ``meta['height']`` — the same resolution as the model's
    input (default 640×640).  Use :class:`BatchClipAnalyzer`, which extracts
    pre-scaled frames from closed clips via FFmpeg.
    """

    def __init__(
        self,
        model_path: "str | Path",
        device: str = "cpu",
        input_size: tuple[int, int] = (640, 640),
        conf_threshold: float = 0.25,
        iou_threshold: float = 0.45,
        class_names: Optional[list[str]] = None,
    ) -> None:
        self._model_path = str(model_path)
        self._providers = _PROVIDER_MAP.get(device.lower(), _PROVIDER_MAP["cpu"])
        self._input_w, self._input_h = input_size
        self._conf = conf_threshold
        self._iou = iou_threshold
        self._names = class_names or _COCO_NAMES
        self._session = None
        self._input_name: str = ""
        self._subs: List[Callable[[Sequence[Detection]], None]] = []

    # ── DetectorPort ─────────────────────────────────────────────────────────

    def start(self) -> None:
        try:
            import onnxruntime as ort
        except ImportError as exc:
            raise RuntimeError(
                "onnxruntime is not installed. Run: pip install onnxruntime"
            ) from exc

        available = ort.get_available_providers()
        providers = [p for p in self._providers if p in available]
        if not providers:
            logger.warning("[onnx] none of {} available — falling back to CPU", self._providers)
            providers = ["CPUExecutionProvider"]

        logger.info("[onnx] loading {} | providers={}", self._model_path, providers)
        self._session = ort.InferenceSession(self._model_path, providers=providers)
        self._input_name = self._session.get_inputs()[0].name
        inp = self._session.get_inputs()[0]
        logger.info("[onnx] ready — input={} shape={}", self._input_name, inp.shape)

    def stop(self) -> None:
        self._session = None
        self._subs.clear()
        logger.info("[onnx] session released")

    def subscribe(self, callback: Callable[[Sequence[Detection]], None]) -> None:
        self._subs.append(callback)

    def analyze(self, frame: bytes, meta: dict[str, Any]) -> Sequence[Detection]:
        if self._session is None:
            raise RuntimeError("OnnxDetectorAdapter not started — call start() first")

        w = int(meta.get("width", self._input_w))
        h = int(meta.get("height", self._input_h))
        frame_time = meta["frame_time"]

        # Raw RGB24 → [1, 3, H, W] float32
        arr = np.frombuffer(frame, dtype=np.uint8).reshape((h, w, 3))
        tensor = arr.transpose(2, 0, 1).astype(np.float32) / 255.0
        tensor = np.expand_dims(tensor, 0)  # [1, 3, H, W]

        raw = self._session.run(None, {self._input_name: tensor})
        output = raw[0]

        # Auto-detect format: YOLOv8 has shape[1] < shape[2]; YOLOv5 is transposed
        if output.ndim == 3 and output.shape[1] < output.shape[2]:
            xyxy, confs, cls_ids = _parse_yolov8(output, self._conf, w, h)
        else:
            xyxy, confs, cls_ids = _parse_yolov5(output, self._conf, w, h)

        if len(xyxy) == 0:
            for cb in list(self._subs):
                cb([])
            return []

        keep = _nms(xyxy, confs, self._iou)
        detections: list[Detection] = [
            Detection(
                class_name=self._names[cls_ids[i]] if cls_ids[i] < len(self._names) else str(cls_ids[i]),
                confidence=float(confs[i]),
                bbox=BoundingBox(
                    x=float(xyxy[i, 0]),
                    y=float(xyxy[i, 1]),
                    w=float(xyxy[i, 2] - xyxy[i, 0]),
                    h=float(xyxy[i, 3] - xyxy[i, 1]),
                ),
                frame_time=frame_time,
            )
            for i in keep
        ]

        for cb in list(self._subs):
            cb(detections)
        return detections
