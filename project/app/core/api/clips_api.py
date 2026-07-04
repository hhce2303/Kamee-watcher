"""ClipsApi — facade over clip listing, playback metadata, and browsing (ADR-0009).

Covers the AppBridge slots that deal with recorded clips: listing the output
folder, loading a clip's media metadata (via PlayerService), and browsing local
or UNC directories (via :class:`FileBrowserPort`).  No Qt, no ``os.scandir``, no
``subprocess`` — the browsing lives behind the port.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from loguru import logger

from app.core.api import dto
from app.core.api.events import EventBus
from app.core.ports.file_browser_port import BrowseListing, FileBrowserPort


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
        player_service=None,
        file_browser: Optional[FileBrowserPort] = None,
    ) -> None:
        self._bus = event_bus
        self._clips_dir = Path(clips_dir)
        self._player = player_service
        self._browser = file_browser

    # ── Clip listing ──────────────────────────────────────────────────

    def list_clips(self, limit: int = 100) -> List[dto.ClipDTO]:
        """List clips in the output folder, newest first (mirrors refreshClips)."""
        clips: List[dto.ClipDTO] = []
        if not self._clips_dir.exists():
            return clips
        files = sorted(
            self._clips_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True
        )
        today = datetime.now().date()
        for f in files[:limit]:
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            date_label = self._date_label(mtime.date(), today)
            size_mb = f.stat().st_size / (1024 * 1024)
            clips.append(
                dto.ClipDTO(
                    clip_name=f.name,
                    path=str(f),
                    size_label=f"{size_mb:.0f} MB",
                    date_label=date_label,
                    is_event="_event" in f.stem,
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
        yesterday = today.replace(day=today.day - 1) if today.day > 1 else today
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
        return path
