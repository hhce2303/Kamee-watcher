"""EditorApi — facade over the evidence-reel timeline + export (ADR-0009).

Owns an :class:`EditTimeline` and drives the :class:`EditorExportPort`, replacing
``editor_bridge``'s Qt-coupled logic.  Export runs on a background thread and
reports progress via bus events (``ExportStarted/Progress/Finished/Failed``);
timeline mutations publish ``TimelineChanged``.  No Qt.
"""
from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger

from app.core.api import dto
from app.core.api.events import EventBus
from app.core.editor.models import ClipEntry, EditTimeline
from app.core.editor.sequencer import TimelineSequencer
from app.core.ports.clip_inspector_port import ClipInspectorPort
from app.core.ports.editor_export_port import EditorExportPort


class EditorApi:
    """Command surface for building and exporting the evidence reel."""

    def __init__(
        self,
        *,
        event_bus: EventBus,
        export_port: Optional[EditorExportPort] = None,
        clips_dir: Optional[Path] = None,
        inspector: Optional[ClipInspectorPort] = None,
    ) -> None:
        self._bus = event_bus
        self._timeline = EditTimeline()
        self._export_port = export_port
        self._clips_dir = Path(clips_dir) if clips_dir else None
        self._inspector = inspector
        self._exporting = False

    # ── Queries ───────────────────────────────────────────────────────

    @property
    def timeline(self) -> EditTimeline:
        return self._timeline

    @property
    def exporting(self) -> bool:
        return self._exporting

    def clip_count(self) -> int:
        return len(self._timeline)

    def total_duration(self) -> float:
        return self._timeline.total_duration_s

    # ── Timeline mutations ────────────────────────────────────────────

    def add_clip(self, cmd: dto.AddClip) -> None:
        self._timeline.add(ClipEntry(Path(cmd.path), float(cmd.duration_s)))
        self._bus.publish(dto.TimelineChanged())

    def add_clip_trimmed(self, cmd: dto.AddClipTrimmed) -> None:
        dur = float(cmd.duration_s)
        self._timeline.add(
            ClipEntry(Path(cmd.path), dur, cmd.in_frac * dur, cmd.out_frac * dur)
        )
        self._bus.publish(dto.TimelineChanged())

    def add_files_from_urls(self, cmd: dto.AddFilesFromUrls) -> int:
        """Probe each file's duration and append it; skip un-probeable files.

        Returns the index of the first clip added, or -1 if nothing was added.
        """
        first = -1
        added = 0
        for raw in cmd.urls or []:
            path = self._to_local_path(raw)
            if path is None:
                continue
            dur = self._probe_duration(path)
            if dur <= 0:
                logger.warning("[editor-api] skipping un-probeable file: {}", path)
                continue
            idx = self._timeline.add(ClipEntry(path, dur))
            added += 1
            if first < 0:
                first = idx
        if added:
            self._bus.publish(dto.TimelineChanged())
        return first

    def remove_clip(self, index: int) -> None:
        try:
            self._timeline.remove(index)
        except IndexError:
            logger.warning("[editor-api] removeClip: bad index {}", index)
            return
        self._bus.publish(dto.TimelineChanged())

    def move_clip(self, src: int, dst: int) -> None:
        try:
            self._timeline.move(src, dst)
        except IndexError:
            logger.warning("[editor-api] moveClip: bad src {}", src)
            return
        self._bus.publish(dto.TimelineChanged())

    def set_trim(self, index: int, in_point_s: float, out_point_s: float) -> None:
        if 0 <= index < len(self._timeline):
            self._timeline.set_trim(index, in_point_s, out_point_s)
            self._bus.publish(dto.TimelineChanged())

    def clear(self) -> None:
        self._timeline.clear()
        self._bus.publish(dto.TimelineChanged())

    def locate(self, global_pos_s: float) -> Optional[dict]:
        hit = TimelineSequencer(self._timeline).locate(global_pos_s)
        if hit is None:
            return None
        index, local = hit
        return {
            "index": index,
            "local_pos": local,
            "source_path": str(self._timeline[index].source_path),
        }

    # ── Export ────────────────────────────────────────────────────────

    def export_timeline(self, cmd: dto.ExportTimeline) -> None:
        """Validate then export the reel on a background thread (bus events report progress)."""
        if self._exporting:
            logger.warning("[editor-api] export already in progress")
            return
        if self._export_port is None:
            self._bus.publish(dto.ExportFailed(message="No hay motor de exportación configurado."))
            return
        errors = self._timeline.validate()
        if errors:
            self._bus.publish(dto.ExportFailed(message=" ".join(errors)))
            return
        self._exporting = True
        self._bus.publish(dto.ExportStarted())
        self._run_export_async(cmd.output_path)

    def default_output_path(self) -> Optional[str]:
        if self._clips_dir is None:
            return None
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        return str(self._clips_dir / f"reel_{stamp}.mp4")

    # ── Internal ──────────────────────────────────────────────────────

    def _run_export_async(self, output_path: str) -> None:
        """Overridable in tests so export can run inline for determinism."""
        threading.Thread(
            target=self._do_export, args=(output_path,), daemon=True, name="editor-export"
        ).start()

    def _do_export(self, output_path: str) -> None:
        try:
            self._export_port.export(
                self._timeline,
                Path(output_path),
                on_progress=lambda f: self._bus.publish(dto.ExportProgress(fraction=f)),
            )
            self._bus.publish(dto.ExportFinished(output_path=output_path))
            logger.info("[editor-api] export finished: {}", output_path)
        except Exception as exc:  # noqa: BLE001
            logger.exception("[editor-api] export failed")
            self._bus.publish(dto.ExportFailed(message=str(exc)))
        finally:
            self._exporting = False

    def _probe_duration(self, path: Path) -> float:
        if self._inspector is None:
            logger.error("[editor-api] no inspector configured — cannot probe {}", path)
            return 0.0
        try:
            return float(self._inspector.inspect(path).duration_seconds)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[editor-api] failed to probe {}: {}", path, exc)
            return 0.0

    @staticmethod
    def _to_local_path(raw: object) -> Optional[Path]:
        """Normalise a url/string into a local Path — no Qt (unlike the old bridge)."""
        s = str(raw)
        if s.startswith("file:"):
            from urllib.parse import unquote, urlparse  # noqa: PLC0415

            parsed = urlparse(s)
            local = unquote(parsed.path)
            # file:///C:/x → /C:/x on Windows; strip the leading slash.
            if len(local) >= 3 and local[0] == "/" and local[2] == ":":
                local = local[1:]
            return Path(local) if local else None
        return Path(s) if s else None
