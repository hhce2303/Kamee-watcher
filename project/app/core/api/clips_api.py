"""ClipsApi — facade over clip listing, playback metadata, and browsing (ADR-0009).

Covers the AppBridge slots that deal with recorded clips: listing the output
folder, loading a clip's media metadata (via PlayerService), and browsing local
or UNC directories (via :class:`FileBrowserPort`).  No Qt, no ``os.scandir``, no
``subprocess`` — the browsing lives behind the port.
"""
from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from loguru import logger

from app.core.api import dto
from app.core.api.events import EventBus
from app.core.ports.file_browser_port import BrowseListing, FileBrowserPort
from app.core.ports.mp4_converter_port import Mp4ConverterPort


@dataclass
class LoadedClip:
    """Result of :meth:`ClipsApi.load_clip` — resolved path + media info."""

    path: str
    info: Optional[dto.ClipInfoDTO]
    ok: bool


def _fmt_size(size_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.0f} {unit}"
        size_bytes //= 1024
    return f"{size_bytes:.0f} TB"


class ClipsApi:
    """Command surface for the clip browser + player metadata."""

    def __init__(
        self,
        *,
        event_bus: EventBus,
        clips_dir: Path,
        event_clips_dir: Optional[Path] = None,
        player_service=None,
        file_browser: Optional[FileBrowserPort] = None,
        mp4_converter: Optional[Mp4ConverterPort] = None,
    ) -> None:
        self._bus = event_bus
        self._clips_dir = Path(clips_dir)
        self._event_clips_dir = Path(event_clips_dir) if event_clips_dir else None
        self._player = player_service
        self._browser = file_browser
        self._converter = mp4_converter
        self._transcoding: set[str] = set()

    # ── Clip listing ──────────────────────────────────────────────────

    def list_clips(self, limit: int = 100) -> List[dto.ClipDTO]:
        """List clips across the combined + event folders, newest first (mirrors refreshClips)."""
        sources: List[tuple[Path, bool]] = [(self._clips_dir, False)]
        if self._event_clips_dir is not None:
            sources.append((self._event_clips_dir, True))

        files: List[tuple[Path, bool]] = []
        for directory, from_events_dir in sources:
            if not directory.exists():
                continue
            files.extend((f, from_events_dir) for f in directory.glob("*.mp4"))
        files.sort(key=lambda item: item[0].stat().st_mtime, reverse=True)

        today = datetime.now().date()
        clips: List[dto.ClipDTO] = []
        for f, from_events_dir in files[:limit]:
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            date_label = self._date_label(mtime.date(), today)
            size_mb = f.stat().st_size / (1024 * 1024)
            clips.append(
                dto.ClipDTO(
                    clip_name=f.name,
                    path=str(f),
                    size_label=f"{size_mb:.0f} MB",
                    date_label=date_label,
                    is_event=from_events_dir or "_event" in f.stem,
                )
            )
        return clips

    def publish_clips(self) -> List[dto.ClipDTO]:
        """List clips and publish a ClipsChanged event (for the IPC consumer)."""
        clips = self.list_clips()
        self._bus.publish(dto.ClipsChanged(clips=clips))
        return clips

    @staticmethod
    def _date_label(day, today) -> str:
        yesterday = today - timedelta(days=1)
        if day == today:
            return "Hoy"
        if day == yesterday:
            return "Ayer"
        # Windows uses %#d for a non-zero-padded day; POSIX uses %-d.
        fmt = "%#d %b" if os.name == "nt" else "%-d %b"
        return datetime(day.year, day.month, day.day).strftime(fmt)

    # ── Player metadata ───────────────────────────────────────────────

    def load_clip(self, cmd: dto.LoadClip) -> LoadedClip:
        """Resolve + inspect a clip; returns its media metadata (or ok=False)."""
        path = cmd.path
        if not path:
            return LoadedClip(path="", info=None, ok=False)
        p = Path(path)
        # UNC paths may be slow / need auth — skip the exists() check for them.
        is_unc = path.startswith("\\\\") or path.startswith("//")
        if not is_unc and not p.exists():
            return LoadedClip(path="", info=None, ok=False)
        if self._player is None:
            return LoadedClip(path=str(p), info=None, ok=True)
        try:
            info = self._player.load(p)
            v = info.video_stream if info else None
            dto_info = dto.ClipInfoDTO(
                resolution=f"{v.width}×{v.height}" if (v and v.width and v.height) else "",
                codec=(info.video_codec or "") if info else "",
                fps=f"{info.fps:.0f}" if (info and info.fps) else "",
                bitrate=f"{v.bitrate_kbps} kbps" if (v and v.bitrate_kbps) else "",
                duration_seconds=info.duration_seconds if info else 0.0,
            )
            return LoadedClip(path=str(p), info=dto_info, ok=True)
        except Exception:
            logger.exception("[clips-api] load_clip: failed to inspect {}", p)
            return LoadedClip(path=str(p), info=dto.ClipInfoDTO(), ok=True)

    # ── Directory browsing ────────────────────────────────────────────

    def list_directory(self, cmd: dto.ListDirectory) -> BrowseListing:
        """Resolve the LOCAL_* tokens then delegate to the file-browser port."""
        if self._browser is None:
            return BrowseListing(failed=True)
        resolved = self._resolve_token(cmd.path)
        return self._browser.list_directory(resolved)

    def _resolve_token(self, path: str) -> str:
        if path == "LOCAL_CLIPS":
            return str(self._clips_dir)
        if path == "LOCAL_RAW":
            return str(self._clips_dir.parent / "clips_raw")
        if path == "LOCAL_EVENTS":
            return str(self._event_clips_dir) if self._event_clips_dir else ""
        return path

    # ── On-demand transcode (TD-1: WebView2 has no software HEVC decoder) ─

    def transcode_clip(self, cmd: dto.TranscodeClip) -> None:
        """Re-encode *path* to H.264 on a background thread; bus reports progress.

        Used by the player's HEVC-playback-failed fallback — the source clip is
        left untouched, a sibling ``*_converted.mp4`` is produced alongside it.
        """
        path = cmd.path
        if path in self._transcoding:
            logger.warning("[clips-api] transcode already in progress for {}", path)
            return
        if self._converter is None:
            self._bus.publish(dto.TranscodeFailed(path=path, message="No hay conversor configurado."))
            return
        if not Path(path).exists():
            self._bus.publish(dto.TranscodeFailed(path=path, message="Archivo no encontrado."))
            return
        self._transcoding.add(path)
        self._bus.publish(dto.TranscodeStarted(path=path))
        self._run_transcode_async(path)

    def _run_transcode_async(self, path: str) -> None:
        """Overridable in tests so transcode can run inline for determinism."""
        threading.Thread(
            target=self._do_transcode, args=(path,), daemon=True, name="clip-transcode"
        ).start()

    def _do_transcode(self, path: str) -> None:
        try:
            output = self._converter.convert(
                Path(path),
                on_progress=lambda f: self._bus.publish(dto.TranscodeProgress(path=path, fraction=f)),
            )
            self._bus.publish(dto.TranscodeFinished(path=path, output_path=str(output)))
            logger.info("[clips-api] transcode finished: {} → {}", path, output)
        except Exception as exc:  # noqa: BLE001
            logger.exception("[clips-api] transcode failed: {}", path)
            self._bus.publish(dto.TranscodeFailed(path=path, message=str(exc)))
        finally:
            self._transcoding.discard(path)
