from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import List, Optional

from loguru import logger

from app.adapters.ffmpeg.ffmpeg_path import resolve_ffmpeg, resolve_ffprobe
from app.core.player.models import ClipInfo, StreamInfo
from app.core.ports.clip_inspector_port import ClipInspectorPort

_TIME_RE = re.compile(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)")


class FFprobeClipInspectorAdapter(ClipInspectorPort):
    """Uses ffprobe (JSON output) to extract stream metadata from any media file."""

    def inspect(self, path: Path) -> ClipInfo:
        if not path.exists():
            raise FileNotFoundError(f"Clip not found: {path}")

        probe = self._run_ffprobe(path)
        streams = self._parse_streams(probe.get("streams", []))

        fmt = probe.get("format", {})
        duration = float(fmt.get("duration", 0.0) or 0.0)
        if duration <= 0:
            # Some containers never got a duration written into their header —
            # e.g. a live-muxed Matroska recording interrupted before it could
            # finalize (no SegmentInfo/Duration, no Cues — "File ended
            # prematurely" from ffmpeg). The only way to know how much is
            # actually playable is to demux the whole file (stream-copy, no
            # decode — ~80s for a 13h/15GB dump in testing, effectively
            # instant for a normal-length clip) and read the last packet
            # timestamp ffmpeg reports as it goes.
            duration = self._scan_duration(path)
            if duration > 0:
                logger.info(
                    "FFprobeInspector: {} had no header duration — scanned {:.1f}s instead.",
                    path.name,
                    duration,
                )
        size_bytes = path.stat().st_size

        logger.debug(
            "FFprobeInspector: {} → {:.1f}s, {} streams",
            path.name,
            duration,
            len(streams),
        )
        return ClipInfo(
            path=path,
            duration_seconds=duration,
            size_bytes=size_bytes,
            streams=streams,
        )

    # ── private helpers ───────────────────────────────────────────────

    def _run_ffprobe(self, path: Path) -> dict:
        cmd = [
            resolve_ffprobe(),
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(path),
        ]
        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                "ffprobe not found — ensure FFmpeg is installed."
            ) from exc

        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="replace")
            raise RuntimeError(f"ffprobe failed (rc={result.returncode}): {stderr}")

        return json.loads(result.stdout)

    def _scan_duration(self, path: Path) -> float:
        """Demux the whole file (no decode) and return the last packet
        timestamp ffmpeg reports — the fallback for containers with no
        duration in their header. Best-effort: any failure (including a
        timeout on a pathologically large/slow file) yields 0.0, same as the
        caller's existing "un-probeable" skip — never raises."""
        cmd = [resolve_ffmpeg(), "-i", str(path), "-c", "copy", "-f", "null", "-"]
        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=600,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            logger.warning("FFprobeInspector: duration scan failed for {}: {}", path, exc)
            return 0.0

        stderr = result.stderr.decode("utf-8", errors="replace")
        matches = _TIME_RE.findall(stderr)
        if not matches:
            return 0.0
        h, m, s = matches[-1]
        return int(h) * 3600 + int(m) * 60 + float(s)

    def _parse_streams(self, raw_streams: list) -> List[StreamInfo]:
        streams: List[StreamInfo] = []
        for s in raw_streams:
            codec_type = s.get("codec_type", "unknown")
            codec_name = s.get("codec_name", "unknown")

            fps: Optional[float] = None
            if codec_type == "video":
                r_frame_rate = s.get("r_frame_rate", "")
                if "/" in r_frame_rate:
                    num_str, den_str = r_frame_rate.split("/", 1)
                    den = int(den_str)
                    if den:
                        fps = round(int(num_str) / den, 3)

            bitrate_kbps: Optional[int] = None
            raw_bitrate = s.get("bit_rate")
            if raw_bitrate:
                try:
                    bitrate_kbps = int(raw_bitrate) // 1000
                except ValueError:
                    pass

            sample_rate: Optional[int] = None
            raw_sr = s.get("sample_rate")
            if raw_sr:
                try:
                    sample_rate = int(raw_sr)
                except ValueError:
                    pass

            streams.append(
                StreamInfo(
                    index=int(s.get("index", 0)),
                    type=codec_type,
                    codec=codec_name,
                    width=s.get("width"),
                    height=s.get("height"),
                    fps=fps,
                    pixel_format=s.get("pix_fmt"),
                    sample_rate=sample_rate,
                    channels=s.get("channels"),
                    bitrate_kbps=bitrate_kbps,
                    language=s.get("tags", {}).get("language"),
                )
            )
        return streams
