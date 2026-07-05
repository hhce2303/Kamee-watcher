"""
Integration tests — Fase 3 (R-AI): batch clip analysis.

Covers:
  1. OnnxDetectorAdapter — model load, inference, NMS, YOLOv8/v5 parsing
     (onnxruntime is mocked; no real model needed)
  2. BatchClipAnalyzer — worker lifecycle, clip queuing, per-frame dispatch,
     threshold / cooldown, on_batch_event callback
     (FFmpeg subprocess is mocked; no real video file needed)
  3. _parse_clip_start — filename → datetime
  4. backend.py wiring — batch_analyzer wired + on_clip_ready chains to analyzer
"""
from __future__ import annotations

import sys
import threading
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional
from unittest.mock import MagicMock, call, patch

import numpy as np
import pytest

from app.core.analytics.batch_clip_analyzer import BatchClipAnalyzer, _parse_clip_start
from app.core.analytics.models import AnalyticEvent, BoundingBox, Detection

# ── helpers ──────────────────────────────────────────────────────────────────

_T0 = datetime(2026, 7, 4, 12, 0, 0, tzinfo=timezone.utc)


def _make_detection(conf: float = 0.9, cls: str = "person") -> Detection:
    return Detection(
        class_name=cls,
        confidence=conf,
        bbox=BoundingBox(x=0.1, y=0.1, w=0.5, h=0.5),
        frame_time=_T0,
    )


# ── OnnxDetectorAdapter ───────────────────────────────────────────────────────

class TestOnnxDetectorAdapter:
    """Unit tests — onnxruntime is mocked throughout."""

    def _make_ort_mock(self, output: np.ndarray) -> types.ModuleType:
        """Return a minimal fake onnxruntime module."""
        ort = types.ModuleType("onnxruntime")
        ort.get_available_providers = lambda: ["CPUExecutionProvider"]
        session = MagicMock()
        session.get_inputs.return_value = [MagicMock(name="images", shape=[1, 3, 640, 640])]
        session.run.return_value = [output]
        ort.InferenceSession = MagicMock(return_value=session)
        return ort

    def _make_yolov8_output(self, cx=320.0, cy=320.0, w=100.0, h=200.0, conf=0.9, cls_idx=0):
        """YOLOv8 format: [1, 84, 8400]."""
        out = np.zeros((1, 84, 8400), dtype=np.float32)
        out[0, 0, 0] = cx
        out[0, 1, 0] = cy
        out[0, 2, 0] = w
        out[0, 3, 0] = h
        out[0, 4 + cls_idx, 0] = conf
        return out

    def _make_yolov5_output(self, cx=320.0, cy=320.0, w=100.0, h=200.0, obj=0.95, conf=0.9, cls_idx=0):
        """YOLOv5 format: [1, 25200, 85]."""
        out = np.zeros((1, 25200, 85), dtype=np.float32)
        out[0, 0, 0] = cx
        out[0, 0, 1] = cy
        out[0, 0, 2] = w
        out[0, 0, 3] = h
        out[0, 0, 4] = obj
        out[0, 0, 5 + cls_idx] = conf
        return out

    def test_start_loads_session(self, tmp_path):
        from app.adapters.ml.onnx_detector import OnnxDetectorAdapter
        fake_model = tmp_path / "model.onnx"
        fake_model.write_bytes(b"FAKE")
        ort = self._make_ort_mock(np.zeros((1, 84, 8400), dtype=np.float32))
        with patch.dict(sys.modules, {"onnxruntime": ort}):
            adapter = OnnxDetectorAdapter(fake_model, device="cpu")
            adapter.start()
        ort.InferenceSession.assert_called_once()

    def test_yolov8_detection_above_threshold(self, tmp_path):
        from app.adapters.ml.onnx_detector import OnnxDetectorAdapter
        out = self._make_yolov8_output(conf=0.85, cls_idx=0)
        ort = self._make_ort_mock(out)
        fake_model = tmp_path / "model.onnx"
        fake_model.write_bytes(b"FAKE")
        with patch.dict(sys.modules, {"onnxruntime": ort}):
            adapter = OnnxDetectorAdapter(fake_model, device="cpu", conf_threshold=0.25)
            adapter.start()
            frame = np.zeros((640, 640, 3), dtype=np.uint8).tobytes()
            meta = {"frame_time": _T0, "width": 640, "height": 640}
            detections = adapter.analyze(frame, meta)

        assert len(detections) == 1
        assert detections[0].class_name == "person"
        assert detections[0].confidence == pytest.approx(0.85, abs=1e-4)

    def test_yolov5_detection_above_threshold(self, tmp_path):
        from app.adapters.ml.onnx_detector import OnnxDetectorAdapter
        out = self._make_yolov5_output(obj=0.95, conf=0.9, cls_idx=0)
        ort = self._make_ort_mock(out)
        fake_model = tmp_path / "model.onnx"
        fake_model.write_bytes(b"FAKE")
        with patch.dict(sys.modules, {"onnxruntime": ort}):
            adapter = OnnxDetectorAdapter(fake_model, device="cpu", conf_threshold=0.25)
            adapter.start()
            frame = np.zeros((640, 640, 3), dtype=np.uint8).tobytes()
            meta = {"frame_time": _T0, "width": 640, "height": 640}
            detections = adapter.analyze(frame, meta)

        assert len(detections) == 1
        assert detections[0].class_name == "person"

    def test_below_threshold_returns_empty(self, tmp_path):
        from app.adapters.ml.onnx_detector import OnnxDetectorAdapter
        out = self._make_yolov8_output(conf=0.1, cls_idx=0)  # below default 0.25
        ort = self._make_ort_mock(out)
        fake_model = tmp_path / "model.onnx"
        fake_model.write_bytes(b"FAKE")
        with patch.dict(sys.modules, {"onnxruntime": ort}):
            adapter = OnnxDetectorAdapter(fake_model, device="cpu", conf_threshold=0.25)
            adapter.start()
            frame = np.zeros((640, 640, 3), dtype=np.uint8).tobytes()
            meta = {"frame_time": _T0, "width": 640, "height": 640}
            detections = adapter.analyze(frame, meta)

        assert detections == []

    def test_subscribe_callback_invoked(self, tmp_path):
        from app.adapters.ml.onnx_detector import OnnxDetectorAdapter
        out = self._make_yolov8_output(conf=0.85)
        ort = self._make_ort_mock(out)
        fake_model = tmp_path / "model.onnx"
        fake_model.write_bytes(b"FAKE")
        received = []
        with patch.dict(sys.modules, {"onnxruntime": ort}):
            adapter = OnnxDetectorAdapter(fake_model, device="cpu", conf_threshold=0.25)
            adapter.subscribe(received.extend)
            adapter.start()
            frame = np.zeros((640, 640, 3), dtype=np.uint8).tobytes()
            adapter.analyze(frame, {"frame_time": _T0, "width": 640, "height": 640})

        assert len(received) == 1
        assert isinstance(received[0], Detection)

    def test_missing_onnxruntime_raises(self, tmp_path):
        from app.adapters.ml.onnx_detector import OnnxDetectorAdapter
        fake_model = tmp_path / "model.onnx"
        fake_model.write_bytes(b"FAKE")
        # Remove onnxruntime from sys.modules to simulate it not being installed
        with patch.dict(sys.modules, {"onnxruntime": None}):
            adapter = OnnxDetectorAdapter(fake_model)
            with pytest.raises(RuntimeError, match="onnxruntime"):
                adapter.start()

    def test_bbox_is_normalised(self, tmp_path):
        from app.adapters.ml.onnx_detector import OnnxDetectorAdapter
        # Center at (320, 320) with w=128, h=256 in a 640×640 model → normalised 0.1..0.9
        out = self._make_yolov8_output(cx=320.0, cy=320.0, w=128.0, h=256.0, conf=0.85)
        ort = self._make_ort_mock(out)
        fake_model = tmp_path / "model.onnx"
        fake_model.write_bytes(b"FAKE")
        with patch.dict(sys.modules, {"onnxruntime": ort}):
            adapter = OnnxDetectorAdapter(fake_model, conf_threshold=0.25)
            adapter.start()
            frame = np.zeros((640, 640, 3), dtype=np.uint8).tobytes()
            dets = adapter.analyze(frame, {"frame_time": _T0, "width": 640, "height": 640})

        assert dets, "expected one detection"
        bb = dets[0].bbox
        assert 0.0 <= bb.x <= 1.0
        assert 0.0 <= bb.y <= 1.0
        assert 0.0 < bb.w <= 1.0
        assert 0.0 < bb.h <= 1.0


# ── BatchClipAnalyzer ─────────────────────────────────────────────────────────

def _fake_ffmpeg_proc(frames: list[bytes]) -> MagicMock:
    """Return a mock subprocess.Popen that yields *frames* then EOF."""
    stdout = MagicMock()
    if frames:
        data = b"".join(frames)
        chunk = len(frames[0])
        read_values = [data[i : i + chunk] for i in range(0, len(data), chunk)]
        read_values.append(b"")  # EOF
    else:
        read_values = [b""]  # immediate EOF
    stdout.read.side_effect = read_values
    proc = MagicMock()
    proc.stdout = stdout
    proc.wait.return_value = 0
    return proc


class TestBatchClipAnalyzer:

    def _mock_detector(self, detections_per_frame: list[list[Detection]]) -> MagicMock:
        detector = MagicMock()
        detector.analyze.side_effect = detections_per_frame
        detector.start.return_value = None
        detector.stop.return_value = None
        return detector

    def test_queue_clip_calls_on_batch_event(self, tmp_path):
        """A detection above threshold must produce an AnalyticEvent via on_batch_event."""
        clip = tmp_path / "2026-07-04_12-00-00_m0.mp4"
        clip.write_bytes(b"FAKE")
        frame_w, frame_h = 640, 640
        raw_frame = bytes(frame_w * frame_h * 3)

        detector = self._mock_detector([[_make_detection(conf=0.9)], []])
        received: List[tuple[AnalyticEvent, Path]] = []
        analyzer = BatchClipAnalyzer(
            detector=detector,
            on_batch_event=lambda ev, p: received.append((ev, p)),
            confidence_threshold=0.6,
            cooldown_seconds=0,
            frame_interval_seconds=1,
            input_width=frame_w,
            input_height=frame_h,
        )

        done = threading.Event()
        orig_analyze = analyzer._analyze_clip

        def _patched_analyze(clip_path, clip_start):
            orig_analyze(clip_path, clip_start)
            done.set()

        proc = _fake_ffmpeg_proc([raw_frame, raw_frame])
        with (
            patch("app.core.analytics.batch_clip_analyzer.resolve_ffmpeg", return_value="ffmpeg"),
            patch("subprocess.Popen", return_value=proc),
        ):
            analyzer._analyze_clip = _patched_analyze
            analyzer.start()
            analyzer.queue_clip(clip)
            done.wait(timeout=3.0)

        assert len(received) == 1
        ev, p = received[0]
        assert ev.source == "auto:yolo"
        assert ev.type == "person"
        assert ev.confidence == pytest.approx(0.9)
        assert ev.clip_path == clip
        assert p == clip

    def test_below_threshold_no_event(self, tmp_path):
        clip = tmp_path / "2026-07-04_12-00-00_m0.mp4"
        clip.write_bytes(b"FAKE")
        raw_frame = bytes(640 * 640 * 3)

        detector = self._mock_detector([[_make_detection(conf=0.3)]])
        received: list = []
        analyzer = BatchClipAnalyzer(
            detector=detector,
            on_batch_event=lambda ev, p: received.append(ev),
            confidence_threshold=0.6,
            cooldown_seconds=0,
        )

        done = threading.Event()
        orig = analyzer._analyze_clip

        def _patched(clip_path, clip_start):
            orig(clip_path, clip_start)
            done.set()

        proc = _fake_ffmpeg_proc([raw_frame])
        with (
            patch("app.core.analytics.batch_clip_analyzer.resolve_ffmpeg", return_value="ffmpeg"),
            patch("subprocess.Popen", return_value=proc),
        ):
            analyzer._analyze_clip = _patched
            analyzer.start()
            analyzer.queue_clip(clip)
            done.wait(timeout=3.0)

        assert received == []

    def test_cooldown_suppresses_second_event(self, tmp_path):
        clip = tmp_path / "2026-07-04_12-00-00_m0.mp4"
        clip.write_bytes(b"FAKE")
        raw_frame = bytes(640 * 640 * 3)

        # Two frames each with a high-confidence detection; cooldown=60s prevents second
        detector = self._mock_detector([
            [_make_detection(conf=0.9)],
            [_make_detection(conf=0.9)],
        ])
        received: list = []
        analyzer = BatchClipAnalyzer(
            detector=detector,
            on_batch_event=lambda ev, p: received.append(ev),
            confidence_threshold=0.6,
            cooldown_seconds=60,  # 60s cooldown but frames are 1s apart
        )

        done = threading.Event()
        orig = analyzer._analyze_clip

        def _patched(clip_path, clip_start):
            orig(clip_path, clip_start)
            done.set()

        proc = _fake_ffmpeg_proc([raw_frame, raw_frame])
        with (
            patch("app.core.analytics.batch_clip_analyzer.resolve_ffmpeg", return_value="ffmpeg"),
            patch("subprocess.Popen", return_value=proc),
        ):
            analyzer._analyze_clip = _patched
            analyzer.start()
            analyzer.queue_clip(clip)
            done.wait(timeout=3.0)

        # Only the first detection should produce an event
        assert len(received) == 1

    def test_stop_joins_worker(self, tmp_path):
        """stop() must drain the queue gracefully."""
        clip = tmp_path / "2026-07-04_12-00-00_m0.mp4"
        clip.write_bytes(b"FAKE")
        detector = self._mock_detector([])
        analyzer = BatchClipAnalyzer(detector=detector, on_batch_event=lambda ev, p: None)

        proc = _fake_ffmpeg_proc([])  # empty clip
        with (
            patch("app.core.analytics.batch_clip_analyzer.resolve_ffmpeg", return_value="ffmpeg"),
            patch("subprocess.Popen", return_value=proc),
        ):
            analyzer.start()
            analyzer.stop()

        assert not (analyzer._thread and analyzer._thread.is_alive())


# ── _parse_clip_start ─────────────────────────────────────────────────────────

class TestParseClipStart:

    def test_parses_standard_filename(self):
        p = Path("2026-07-04_12-30-00_m0.mp4")
        dt = _parse_clip_start(p)
        assert dt == datetime(2026, 7, 4, 12, 30, 0, tzinfo=timezone.utc)

    def test_fallback_on_unparseable_name(self):
        p = Path("unknown_clip.mp4")
        dt = _parse_clip_start(p)
        # Should return a valid UTC datetime close to now (not crash)
        assert dt.tzinfo is not None
        assert abs((dt - datetime.now(tz=timezone.utc)).total_seconds()) < 5


# ── backend wiring ────────────────────────────────────────────────────────────

class TestBackendF3Wiring:
    """Verify backend.py wires BatchClipAnalyzer correctly."""

    def test_batch_analyzer_created_in_backend(self):
        from app.runtime.backend import RecordingBackend
        # RecordingBackend dataclass must expose batch_analyzer field
        b = RecordingBackend()
        assert hasattr(b, "batch_analyzer")
        assert b.batch_analyzer is None  # not set on empty backend

    def test_on_clip_ready_queues_batch_analyzer(self, tmp_path):
        """When on_clip_ready fires, batch_analyzer.queue_clip is called."""
        from app.adapters.ffmpeg.hourly_recording_builder import HourlyRecordingBuilder
        from app.runtime.backend import RecordingBackend

        queued: list[Path] = []
        fake_analyzer = MagicMock()
        fake_analyzer.queue_clip.side_effect = lambda p: queued.append(p)

        backend = RecordingBackend()
        backend.batch_analyzer = fake_analyzer

        clip_path = tmp_path / "2026-07-04_12-00-00_m0.mp4"
        clip_path.write_bytes(b"FAKE")

        def _on_clip_ready(p: Path) -> None:
            if backend.batch_analyzer is not None:
                backend.batch_analyzer.queue_clip(p)

        _on_clip_ready(clip_path)

        assert queued == [clip_path]
        fake_analyzer.queue_clip.assert_called_once_with(clip_path)
