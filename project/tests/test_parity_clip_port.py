"""Track R2 M1 — Rust ↔ FFmpeg parity harness for ``FFmpegTrimAdapter``'s
single-monitor path (``ClipPort``).

Clone of ``test_parity_segment_compiler.py``'s methodology (framemd5 + ffprobe),
adapted to exercise the actual adapter callers use — ``build_clip()`` with real
``Segment`` domain objects (path + started_at/ended_at), not raw file paths —
so it validates the M1 wiring (``_build_single`` → ``_build_single_rust`` with
FFmpeg fallback), not just the underlying engine.

Self-activating like its sibling: skips cleanly while the native engine is
absent, turns green the moment it's built.
"""
from __future__ import annotations

import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

import pytest
from loguru import logger

pytestmark = pytest.mark.parity

try:
    from app.adapters.ffmpeg.ffmpeg_path import resolve_ffmpeg, resolve_ffprobe

    _FFMPEG = resolve_ffmpeg()
    _FFPROBE = resolve_ffprobe()
except Exception as exc:  # noqa: BLE001
    pytest.skip(f"ffmpeg/ffprobe unavailable: {exc}", allow_module_level=True)

from app.adapters.ffmpeg.clip_inspector_adapter import FFprobeClipInspectorAdapter
from app.adapters.ffmpeg.trim_adapter import FFmpegTrimAdapter
from app.adapters.native import rust_segment_compiler as rsc
from app.core.recording_service.models import MonitorInfo, Segment

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
_FPS = 30
_GOP = 15  # keyframe every 15 frames -> keyframes at 0.0, 0.5, 1.0, 1.5s
_DUR = 2  # seconds per synthetic segment
_FRAME_PERIOD = 1.0 / _FPS
_MONITOR = MonitorInfo(name="TestMonitor", width=320, height=240, x=0, y=0, is_primary=True, index=0)


def _run(cmd: List[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120, creationflags=_NO_WINDOW)


def _framemd5(path: Path) -> List[str]:
    res = _run([_FFMPEG, "-i", str(path), "-map", "0:v:0", "-f", "framemd5", "-"])
    if res.returncode != 0:
        raise RuntimeError(res.stderr.decode("utf-8", "replace"))
    hashes: List[str] = []
    for line in res.stdout.decode("utf-8", "replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        hashes.append(line.split(",")[-1].strip())
    return hashes


def _frame_count(path: Path) -> int:
    res = _run([
        _FFPROBE, "-v", "error", "-select_streams", "v:0",
        "-count_frames", "-show_entries", "stream=nb_read_frames",
        "-of", "csv=p=0", str(path),
    ])
    return int(res.stdout.decode("utf-8", "replace").strip() or 0)


def _is_playable(path: Path) -> bool:
    res = _run([_FFMPEG, "-v", "error", "-i", str(path), "-f", "null", "-"])
    return res.returncode == 0 and not res.stderr.decode("utf-8", "replace").strip()


def _first_is_keyframe(path: Path) -> bool:
    res = _run([
        _FFPROBE, "-v", "error", "-select_streams", "v:0",
        "-show_entries", "frame=key_frame", "-of", "csv=p=0", str(path),
    ])
    vals = [x.strip() for x in res.stdout.decode("utf-8", "replace").splitlines() if x.strip()]
    return bool(vals) and vals[0].split(",")[0] == "1"


def _source_md5(paths: List[Path]) -> List[str]:
    seq: List[str] = []
    for p in paths:
        seq.extend(_framemd5(p))
    return seq


def _contiguous_start(sub: List[str], full: List[str]) -> int:
    if not sub:
        return -1
    for i in range(len(full) - len(sub) + 1):
        if full[i:i + len(sub)] == sub:
            return i
    return -1


def _video_stream(path: Path):
    info = FFprobeClipInspectorAdapter().inspect(path)
    vids = [s for s in info.streams if s.type == "video"]
    assert vids, f"no video stream in {path}"
    return vids[0]


def _make_ts(path: Path, codec: str, src_filter: str, duration: float = _DUR) -> None:
    encoder = {"h264": "libx264", "hevc": "libx265"}[codec]
    cmd = [
        _FFMPEG, "-y", "-f", "lavfi", "-i", f"{src_filter}=duration={duration}:size=320x240:rate={_FPS}",
        "-c:v", encoder, "-g", str(_GOP), "-keyint_min", str(_GOP), "-pix_fmt", "yuv420p",
    ]
    if codec == "hevc":
        cmd += ["-tag:v", "hvc1", "-x265-params", "log-level=error"]
    cmd += ["-f", "mpegts", str(path)]
    res = _run(cmd)
    if res.returncode != 0:
        raise RuntimeError(res.stderr.decode("utf-8", "replace"))


def _segments(paths: List[Path], base: datetime) -> List[Segment]:
    """Wrap sequential synthetic TS files as contiguous, finalized Segments."""
    segs = []
    t = base
    for p in paths:
        end = t + timedelta(seconds=_DUR)
        segs.append(Segment(path=p, started_at=t, ended_at=end, finalized=True))
        t = end
    return segs


def _assert_parity(a: Path, b: Path) -> None:
    assert _is_playable(a), f"{a} is not playable"
    assert _is_playable(b), f"{b} is not playable"
    va, vb = _video_stream(a), _video_stream(b)
    assert (va.codec, va.width, va.height, va.pixel_format, va.fps) == (
        vb.codec, vb.width, vb.height, vb.pixel_format, vb.fps
    ), f"metadata mismatch: a={va} b={vb}"
    assert _frame_count(a) == _frame_count(b), "frame count mismatch"
    assert _framemd5(a) == _framemd5(b), "framemd5 sequence mismatch"


@pytest.fixture(scope="module")
def rust_ready() -> None:
    present, ready = rsc.rust_engine_status()
    if not (present and ready):
        pytest.skip("native watcher_segments engine not present/ready (.pyd not built)")


@pytest.fixture()
def rust_adapter(rust_ready) -> FFmpegTrimAdapter:
    return FFmpegTrimAdapter(codec="h264", segment_compiler=rsc.RustSegmentCompilerAdapter())


@pytest.fixture()
def ffmpeg_adapter() -> FFmpegTrimAdapter:
    return FFmpegTrimAdapter(codec="h264", segment_compiler=None)


@pytest.fixture()
def h264_segments(tmp_path_factory: pytest.TempPathFactory) -> List[Segment]:
    d = tmp_path_factory.mktemp("clipport_h264")
    a, b = d / "a.ts", d / "b.ts"
    _make_ts(a, "h264", "testsrc")
    _make_ts(b, "h264", "testsrc2")
    return _segments([a, b], datetime(2026, 7, 11, 9, 0, 0, tzinfo=timezone.utc))


def _build(adapter: FFmpegTrimAdapter, segments: List[Segment], out: Path,
           clip_start: Optional[datetime] = None, clip_end: Optional[datetime] = None) -> Path:
    return adapter.build_clip({_MONITOR: segments}, out, clip_start, clip_end)


class TestExactParityNoWindow:
    def test_single_segment(self, rust_adapter, ffmpeg_adapter, h264_segments, tmp_path):
        segs = h264_segments[:1]
        rust_out, ff_out = tmp_path / "rust.mp4", tmp_path / "ffmpeg.mp4"
        _build(rust_adapter, segs, rust_out)
        _build(ffmpeg_adapter, segs, ff_out)
        _assert_parity(rust_out, ff_out)

    def test_two_segments_concatenated(self, rust_adapter, ffmpeg_adapter, h264_segments, tmp_path):
        rust_out, ff_out = tmp_path / "rust.mp4", tmp_path / "ffmpeg.mp4"
        _build(rust_adapter, h264_segments, rust_out)
        _build(ffmpeg_adapter, h264_segments, ff_out)
        _assert_parity(rust_out, ff_out)


class TestWindowedParity:
    """Windowed scenarios are validated against SOURCE frames, never against
    FFmpeg's own windowed output — this is the same scope decision
    test_parity_segment_compiler.py documents: FFmpeg's concat-demuxer
    inpoint/outpoint + -c copy is implementation-defined at the boundary (this
    harness independently confirmed it: a requested ~1.0s window produced a
    0.1s FFmpeg output while the Rust engine correctly returned ~1.03s,
    snapped to the enclosing keyframes). That's a pre-existing FFmpeg quirk,
    not a Rust-path regression — the port's contract is keyframe-aligned
    stream-copy against the SOURCE, which is what's asserted here."""

    def test_window_within_one_segment(self, rust_adapter, h264_segments, tmp_path):
        segs = h264_segments[:1]
        clip_start = segs[0].started_at + timedelta(seconds=0.5)
        clip_end = segs[0].started_at + timedelta(seconds=1.5)
        out = tmp_path / "rust.mp4"
        _build(rust_adapter, segs, out, clip_start, clip_end)
        self._assert_window_matches_source(out, [segs[0].path], in_eff=0.5, out_eff=1.5)

    def test_window_across_segment_boundary(self, rust_adapter, h264_segments, tmp_path):
        clip_start = h264_segments[0].started_at + timedelta(seconds=1.0)
        clip_end = h264_segments[1].started_at + timedelta(seconds=0.5)
        out = tmp_path / "rust.mp4"
        _build(rust_adapter, h264_segments, out, clip_start, clip_end)
        self._assert_window_matches_source(
            out, [s.path for s in h264_segments], in_eff=1.0, out_eff=_DUR + 0.5
        )

    @staticmethod
    def _assert_window_matches_source(out: Path, source_paths: List[Path], in_eff: float, out_eff: float) -> None:
        assert _is_playable(out), "windowed output is not playable"
        assert _first_is_keyframe(out), "windowed output must start on a keyframe"

        src = _source_md5(source_paths)
        om = _framemd5(out)
        start = _contiguous_start(om, src)
        assert start >= 0, "output frames are not a bit-identical contiguous run of the source"

        gop_s = _GOP / _FPS
        start_s = start / _FPS
        end_s = (start + len(om)) / _FPS
        assert start_s <= in_eff + _FRAME_PERIOD, f"start {start_s:.3f}s is after in-point {in_eff}"
        assert start_s > in_eff - gop_s - _FRAME_PERIOD, (
            f"start {start_s:.3f}s is more than one GOP before in-point {in_eff}"
        )
        assert end_s <= out_eff + _FRAME_PERIOD + 1e-6, f"end {end_s:.3f}s overruns out-point {out_eff}"


class TestHevc:
    def test_hevc_single_segment(self, rust_ready, tmp_path):
        d = tmp_path / "hevc_src"
        d.mkdir()
        p = d / "h.ts"
        try:
            _make_ts(p, "hevc", "testsrc")
        except RuntimeError as exc:
            pytest.skip(f"HEVC (libx265) unavailable in ffmpeg: {exc}")
        segs = _segments([p], datetime(2026, 7, 11, 9, 0, 0, tzinfo=timezone.utc))

        rust_adapter = FFmpegTrimAdapter(codec="hevc", segment_compiler=rsc.RustSegmentCompilerAdapter())
        ffmpeg_adapter = FFmpegTrimAdapter(codec="hevc", segment_compiler=None)
        rust_out, ff_out = tmp_path / "rust.mp4", tmp_path / "ffmpeg.mp4"
        _build(rust_adapter, segs, rust_out)
        _build(ffmpeg_adapter, segs, ff_out)
        _assert_parity(rust_out, ff_out)
        assert _video_stream(rust_out).codec == "hevc"


class TestMissingSegmentFallback:
    """The M1 safety contract: any Rust failure falls back to FFmpeg in the
    SAME call — a caller (ClipBuilder) never sees the Rust-specific error."""

    def test_missing_segment_falls_back_to_ffmpeg_and_still_builds(
        self, rust_adapter, h264_segments, tmp_path
    ):
        # Delete one of the two segment files on disk — the Rust engine
        # requires every source present and raises; FFmpegTrimAdapter's
        # concat-file writer skips missing segments gracefully instead.
        h264_segments[1].path.unlink()
        out = tmp_path / "fallback.mp4"

        # loguru doesn't propagate to stdlib logging, so pytest's `caplog`
        # can't see it — capture via a temporary sink instead.
        messages: List[str] = []
        sink_id = logger.add(lambda msg: messages.append(msg.record["message"]), level="WARNING")
        try:
            result = rust_adapter.build_clip({_MONITOR: h264_segments}, out)
        finally:
            logger.remove(sink_id)

        assert result == out
        assert _is_playable(out)
        assert any("falling back to FFmpeg" in m for m in messages)
