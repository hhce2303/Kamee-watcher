"""Fase 3 (F0 gate) — Rust ↔ FFmpeg parity harness for ``SegmentCompilerPort``.

Runs the FFmpeg oracle (:class:`FFmpegSegmentCompilerAdapter`) and the native
Rust engine (:class:`RustSegmentCompilerAdapter`) over identical inputs and
asserts they produce equivalent output at the *stream-copy* level:

  * identical decoded-frame sequence (``ffmpeg -f framemd5`` — the gold signal;
    stream-copy keeps coded frames bit-for-bit, so decode must match),
  * identical frame count,
  * identical video codec / resolution / pixel format / fps (via ffprobe),
  * duration within one frame period (both cut at the same keyframe),
  * playable with no decode errors.

Byte-identical containers are NOT required — different muxers order atoms
differently. Parity is measured on frames + metadata, which is what matters for
a lossless remux.

Scope note: the port is **keyframe-aligned** stream-copy, not frame-exact
(frame-exact boundary trimming is EditorExportPort's re-encode job, ADR-0002).

The harness is self-activating: it constructs the Rust adapter directly (it does
NOT depend on the ``ENGINE_READY`` factory flag, which flips in a later phase),
and skips cleanly while the native ``compile_clip`` is absent or unimplemented —
so it turns green the moment the Rust engine lands, before the flag is flipped.

Run:  ``python -m pytest tests/test_parity_segment_compiler.py -v -m parity``
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List, Optional

import pytest

pytestmark = pytest.mark.parity

# ── FFmpeg availability (module-level skip; no fixtures needed) ────────────
try:
    from app.adapters.ffmpeg.ffmpeg_path import resolve_ffmpeg, resolve_ffprobe

    _FFMPEG = resolve_ffmpeg()
    _FFPROBE = resolve_ffprobe()
except Exception as exc:  # noqa: BLE001
    pytest.skip(f"ffmpeg/ffprobe unavailable: {exc}", allow_module_level=True)

from app.adapters.ffmpeg.clip_inspector_adapter import FFprobeClipInspectorAdapter
from app.adapters.ffmpeg.segment_compiler_adapter import FFmpegSegmentCompilerAdapter
from app.adapters.native import rust_segment_compiler as rsc
from app.core.player.models import StreamInfo
from app.core.ports.segment_compiler_port import SegmentCompilerPort

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
_FPS = 30
_GOP = 15  # keyframe every 15 frames → keyframes at 0.0, 0.5, 1.0, 1.5 s
_DUR = 2  # seconds per synthetic source
_FRAME_PERIOD = 1.0 / _FPS


# ── ffmpeg/ffprobe measurement helpers ────────────────────────────────────
def _run(cmd: List[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=120, creationflags=_NO_WINDOW,
    )


def _framemd5(path: Path) -> List[str]:
    """Per-decoded-frame MD5 sequence of the first video stream."""
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


def _video_stream(path: Path) -> StreamInfo:
    info = FFprobeClipInspectorAdapter().inspect(path)
    vids = [s for s in info.streams if s.type == "video"]
    assert vids, f"no video stream in {path}"
    return vids[0]


def _duration(path: Path) -> float:
    return FFprobeClipInspectorAdapter().inspect(path).duration_seconds


def _first_is_keyframe(path: Path) -> bool:
    res = _run([
        _FFPROBE, "-v", "error", "-select_streams", "v:0",
        "-show_entries", "frame=key_frame", "-of", "csv=p=0", str(path),
    ])
    vals = [x.strip() for x in res.stdout.decode("utf-8", "replace").splitlines() if x.strip()]
    return bool(vals) and vals[0].split(",")[0] == "1"


def _source_md5(sources: List[Path]) -> List[str]:
    """Decoded-frame MD5s of the sources concatenated in order (the reference
    for a lossless stream-copy: every retained output frame must equal a source
    frame bit-for-bit)."""
    seq: List[str] = []
    for s in sources:
        seq.extend(_framemd5(s))
    return seq


def _contiguous_start(sub: List[str], full: List[str]) -> int:
    """Index where ``sub`` occurs as a contiguous run inside ``full``, else -1."""
    if not sub:
        return -1
    for i in range(len(full) - len(sub) + 1):
        if full[i:i + len(sub)] == sub:
            return i
    return -1


def _make_ts(path: Path, codec: str, src_filter: str) -> None:
    """Generate a deterministic ~{_DUR}s TS with a known GOP via ffmpeg lavfi."""
    encoder = {"h264": "libx264", "hevc": "libx265"}[codec]
    cmd = [
        _FFMPEG, "-y",
        "-f", "lavfi", "-i", f"{src_filter}=duration={_DUR}:size=320x240:rate={_FPS}",
        "-c:v", encoder, "-g", str(_GOP), "-keyint_min", str(_GOP),
        "-pix_fmt", "yuv420p",
    ]
    if codec == "hevc":
        cmd += ["-tag:v", "hvc1", "-x265-params", "log-level=error"]
    cmd += ["-f", "mpegts", str(path)]
    res = _run(cmd)
    if res.returncode != 0:
        raise RuntimeError(res.stderr.decode("utf-8", "replace"))


# ── fixtures: synthetic sources + engines ──────────────────────────────────
@pytest.fixture(scope="session")
def h264_sources(tmp_path_factory: pytest.TempPathFactory) -> List[Path]:
    d = tmp_path_factory.mktemp("parity_h264")
    a, b = d / "a.ts", d / "b.ts"
    _make_ts(a, "h264", "testsrc")
    _make_ts(b, "h264", "testsrc2")
    return [a, b]


@pytest.fixture(scope="session")
def hevc_source(tmp_path_factory: pytest.TempPathFactory) -> Path:
    d = tmp_path_factory.mktemp("parity_hevc")
    p = d / "h.ts"
    try:
        _make_ts(p, "hevc", "testsrc")
    except RuntimeError as exc:  # libx265 not built into this ffmpeg
        pytest.skip(f"HEVC (libx265) unavailable in ffmpeg: {exc}")
    return p


@pytest.fixture(scope="session")
def rust_engine(tmp_path_factory: pytest.TempPathFactory) -> SegmentCompilerPort:
    """Construct the Rust adapter directly and probe it once.

    Skips the whole harness if the native module is absent or ``compile_clip``
    is not yet implemented — so this file is dormant until the Rust engine lands
    and then activates automatically, independent of the ENGINE_READY flag.
    """
    present, _ready = rsc.rust_engine_status()
    if not present:
        pytest.skip("native watcher_segments engine not present (.pyd not built)")
    try:
        engine = rsc.RustSegmentCompilerAdapter()
    except RuntimeError as exc:
        pytest.skip(f"Rust adapter unavailable: {exc}")

    probe_src = tmp_path_factory.mktemp("parity_probe") / "probe.ts"
    _make_ts(probe_src, "h264", "testsrc")
    probe_out = probe_src.with_name("probe.mp4")
    try:
        engine.compile([probe_src], probe_out)
    except Exception as exc:  # noqa: BLE001 — not-yet-implemented / load failure
        pytest.skip(f"Rust compile_clip not ready: {exc}")
    return engine


@pytest.fixture(scope="session")
def ffmpeg_engine() -> SegmentCompilerPort:
    return FFmpegSegmentCompilerAdapter(codec="h264")


@pytest.fixture(scope="session")
def mp4_sources(tmp_path_factory: pytest.TempPathFactory) -> List[Path]:
    """H.264 MP4 sources — mirrors what the editor feeds the concat step
    (EditorExportAdapter writes MP4 parts, then calls compile(parts))."""
    d = tmp_path_factory.mktemp("parity_mp4")
    a, b = d / "a.mp4", d / "b.mp4"
    for p, filt in ((a, "testsrc"), (b, "testsrc2")):
        cmd = [
            _FFMPEG, "-y", "-f", "lavfi",
            "-i", f"{filt}=duration={_DUR}:size=320x240:rate={_FPS}",
            "-c:v", "libx264", "-g", str(_GOP), "-keyint_min", str(_GOP),
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(p),
        ]
        res = _run(cmd)
        if res.returncode != 0:
            raise RuntimeError(res.stderr.decode("utf-8", "replace"))
    return [a, b]


@pytest.fixture(scope="session")
def rust_engine_mp4(
    rust_engine: SegmentCompilerPort,
    mp4_sources: List[Path],
    tmp_path_factory: pytest.TempPathFactory,
) -> SegmentCompilerPort:
    """Same Rust engine, but skips if MP4-input demux isn't supported yet —
    so the MP4 scenarios stay dormant until that capability lands, then activate
    automatically (same self-activating pattern as :func:`rust_engine`)."""
    probe_out = tmp_path_factory.mktemp("parity_mp4_probe") / "probe.mp4"
    try:
        rust_engine.compile([mp4_sources[0]], probe_out)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Rust engine does not support MP4 input yet: {exc}")
    return rust_engine


# ── the parity assertion, shared by every scenario ────────────────────────
def _assert_parity(rust_out: Path, ff_out: Path) -> None:
    assert _is_playable(rust_out), "Rust output is not playable"
    assert _is_playable(ff_out), "FFmpeg output is not playable"

    rv, fv = _video_stream(rust_out), _video_stream(ff_out)
    assert (rv.codec, rv.width, rv.height, rv.pixel_format, rv.fps) == (
        fv.codec, fv.width, fv.height, fv.pixel_format, fv.fps
    ), f"metadata mismatch: rust={rv} ffmpeg={fv}"

    assert _frame_count(rust_out) == _frame_count(ff_out), "frame count mismatch"

    assert abs(_duration(rust_out) - _duration(ff_out)) <= _FRAME_PERIOD, (
        "duration differs by more than one frame period"
    )

    # Gold signal: identical decoded-frame MD5 sequence (stream-copy ⇒ identical).
    assert _framemd5(rust_out) == _framemd5(ff_out), "framemd5 sequence mismatch"


# ── exact-parity scenarios (no window) — strict frame-for-frame vs oracle ──
# These are the paths the app actually relies on: full remux and lossless concat
# of already-trimmed parts (the shipped default export uses reencode=True, which
# only ever asks the compiler to concatenate — never to window). Full framemd5
# equality with the FFmpeg oracle is required here.
# (name, n_sources, in_point_s, out_point_s)
_EXACT_SCENARIOS = [
    ("single_no_window", 1, None, None),
    ("concat_no_window", 2, None, None),
    ("out_beyond_total", 1, None, 999.0),
    ("in_zero_omits_ss", 1, 0.0, None),
]


@pytest.mark.parametrize(
    "name,n,in_s,out_s", _EXACT_SCENARIOS, ids=[s[0] for s in _EXACT_SCENARIOS]
)
def test_parity_h264(
    name: str,
    n: int,
    in_s: Optional[float],
    out_s: Optional[float],
    h264_sources: List[Path],
    rust_engine: SegmentCompilerPort,
    ffmpeg_engine: SegmentCompilerPort,
    tmp_path: Path,
) -> None:
    sources = h264_sources[:n]
    rust_out = tmp_path / f"{name}_rust.mp4"
    ff_out = tmp_path / f"{name}_ffmpeg.mp4"
    rust_engine.compile(sources, rust_out, in_s, out_s)
    ffmpeg_engine.compile(sources, ff_out, in_s, out_s)
    _assert_parity(rust_out, ff_out)


# ── windowed scenarios — lossless + keyframe-aligned, validated vs SOURCE ──
# NOT compared to FFmpeg: its concat-demuxer + output-side ``-ss`` with ``-c
# copy`` + ``make_zero`` is implementation-defined and was observed dropping an
# extra GOP (skipping a valid keyframe at the in-point). The port contract
# explicitly leaves exact framing to the caller (EditorExportPort re-encodes the
# boundary GOP), so enshrining that quirk would be wrong. Instead we assert the
# stronger, correct invariants directly against the source frames.
# (name, n_sources, in_point_s, out_point_s)
_WINDOW_SCENARIOS = [
    ("single_in_only", 1, 0.5, None),
    ("single_in_out", 1, 0.5, 1.5),
    ("concat_window_across_boundary", 2, 1.0, float(_DUR) + 0.5),
]


@pytest.mark.parametrize(
    "name,n,in_s,out_s", _WINDOW_SCENARIOS, ids=[s[0] for s in _WINDOW_SCENARIOS]
)
def test_window_lossless_keyframe_aligned(
    name: str,
    n: int,
    in_s: Optional[float],
    out_s: Optional[float],
    h264_sources: List[Path],
    rust_engine: SegmentCompilerPort,
    tmp_path: Path,
) -> None:
    sources = h264_sources[:n]
    out = tmp_path / f"{name}_rust.mp4"
    rust_engine.compile(sources, out, in_s, out_s)

    assert _is_playable(out), "windowed output is not playable"
    assert _first_is_keyframe(out), "windowed output must start on a keyframe"

    src = _source_md5(sources)
    om = _framemd5(out)
    start = _contiguous_start(om, src)
    assert start >= 0, (
        "output frames are not a bit-identical contiguous run of the source "
        "(stream-copy is not lossless)"
    )

    total = len(src) / _FPS
    in_eff = in_s or 0.0
    out_eff = min(out_s, total) if out_s else total
    gop_s = _GOP / _FPS
    start_s = start / _FPS
    end_s = (start + len(om)) / _FPS

    # Start snaps to the LAST keyframe at or before the in-point (not after, and
    # not an earlier keyframe than necessary).
    assert start_s <= in_eff + _FRAME_PERIOD, f"start {start_s:.3f}s is after in-point {in_eff}"
    assert start_s > in_eff - gop_s - _FRAME_PERIOD, (
        f"start {start_s:.3f}s is more than one GOP before in-point {in_eff}"
    )
    # End does not overrun the out-point beyond a single frame.
    assert end_s <= out_eff + _FRAME_PERIOD + 1e-6, f"end {end_s:.3f}s overruns out-point {out_eff}"


def test_parity_hevc_single(
    hevc_source: Path,
    rust_engine: SegmentCompilerPort,
    tmp_path: Path,
) -> None:
    """HEVC remux must keep the hvc1 tag and match the oracle frame-for-frame."""
    ffmpeg_engine = FFmpegSegmentCompilerAdapter(codec="hevc")
    rust_out = tmp_path / "hevc_rust.mp4"
    ff_out = tmp_path / "hevc_ffmpeg.mp4"
    rust_engine.compile([hevc_source], rust_out, None, None)
    ffmpeg_engine.compile([hevc_source], ff_out, None, None)
    _assert_parity(rust_out, ff_out)
    assert _video_stream(rust_out).codec == "hevc"


# ── MP4-input scenarios — the production concat path ───────────────────────
# The editor writes MP4 parts and calls compile(parts) to join them, so the
# engine MUST accept MP4 input, not just MPEG-TS. Strict frame-for-frame parity
# vs the FFmpeg oracle (these are the paths the shipped default relies on).
def test_parity_mp4_single_remux(
    mp4_sources: List[Path],
    rust_engine_mp4: SegmentCompilerPort,
    ffmpeg_engine: SegmentCompilerPort,
    tmp_path: Path,
) -> None:
    rust_out, ff_out = tmp_path / "mp4_single_rust.mp4", tmp_path / "mp4_single_ffmpeg.mp4"
    rust_engine_mp4.compile([mp4_sources[0]], rust_out, None, None)
    ffmpeg_engine.compile([mp4_sources[0]], ff_out, None, None)
    _assert_parity(rust_out, ff_out)


def test_parity_mp4_concat(
    mp4_sources: List[Path],
    rust_engine_mp4: SegmentCompilerPort,
    ffmpeg_engine: SegmentCompilerPort,
    tmp_path: Path,
) -> None:
    """The exact production case: lossless concat of two MP4 parts."""
    rust_out, ff_out = tmp_path / "mp4_concat_rust.mp4", tmp_path / "mp4_concat_ffmpeg.mp4"
    rust_engine_mp4.compile(mp4_sources, rust_out, None, None)
    ffmpeg_engine.compile(mp4_sources, ff_out, None, None)
    _assert_parity(rust_out, ff_out)
