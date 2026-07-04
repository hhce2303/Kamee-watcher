"""EditorBridge — Qt input adapter over :class:`EditorApi` (R-1, R-5; F1/ADR-0009).

Coexistence phase: this bridge no longer owns the timeline or the mutation logic
— that lives in ``core/api``.  The bridge translates QML slot calls into facade
commands (the single source of logic), reads reel state back from the shared
timeline, and emits its Qt Signals **synchronously** so the QML surface is
unchanged.  The facade also publishes the same changes onto the EventBus for the
future ``adapters/ipc`` consumer (one facade, interchangeable input adapters).

Per AGENTS.md a QObject must NOT also inherit an ABC (Qt/ABCMeta clash): this
bridge *uses* the facade by composition; it does not implement a port.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional

from loguru import logger
from PySide6.QtCore import Property, QObject, Signal, Slot

from app.core.analytics.sidecar import read_sidecar
from app.core.api import dto
from app.core.api.editor_api import EditorApi
from app.core.api.events import EventBus
from app.core.ports.clip_inspector_port import ClipInspectorPort
from app.core.ports.editor_export_port import EditorExportPort


class EditorBridge(QObject):
    """Owns the editing-tab QML contract; delegates all logic to EditorApi."""

    timelineChanged = Signal()
    exportStarted   = Signal()
    exportProgress  = Signal(float)   # 0.0 – 1.0
    exportFinished  = Signal(str)     # output path
    exportFailed    = Signal(str)     # human-readable error
    loadNotice      = Signal(str)     # human-readable load result (skips/failures)

    def __init__(
        self,
        export_port: Optional[EditorExportPort] = None,
        clips_dir: Optional[Path] = None,
        inspector: Optional[ClipInspectorPort] = None,
        parent: Optional[QObject] = None,
        *,
        editor_api: Optional[EditorApi] = None,
    ) -> None:
        super().__init__(parent)
        # main.py injects the shared facade; standalone (tests) builds its own
        # over a private bus.  Either way the facade is the single source of logic.
        self._api = editor_api or EditorApi(
            event_bus=EventBus(),
            export_port=export_port,
            clips_dir=Path(clips_dir) if clips_dir else None,
            inspector=inspector,
        )
        self._exporting = False

    # ── Exposed state (reads the shared timeline) ─────────────────────
    @Property("QVariantList", notify=timelineChanged)
    def clips(self) -> list:
        out = []
        for i, c in enumerate(self._api.timeline.clips):
            out.append(
                {
                    "index": i,
                    "sourcePath": str(c.source_path),
                    "fileName": c.source_path.name,
                    "sourceDuration": c.source_duration_s,
                    "inPoint": c.in_point_s,
                    "outPoint": c.out_point_s,
                    "trimmedDuration": c.trimmed_duration_s,
                }
            )
        return out

    @Property(float, notify=timelineChanged)
    def totalDuration(self) -> float:
        return self._api.total_duration()

    @Property(int, notify=timelineChanged)
    def count(self) -> int:
        return self._api.clip_count()

    @Property(bool, notify=exportStarted)
    def exporting(self) -> bool:
        return self._exporting

    # ── Mutations (QML → facade → Qt signal) ──────────────────────────
    @Slot(str, float)
    def addClip(self, path: str, duration_s: float) -> None:
        self._api.add_clip(dto.AddClip(path=path, duration_s=float(duration_s)))
        self.timelineChanged.emit()

    @Slot(str, float, float, float)
    def addClipTrimmed(self, path: str, duration_s: float, in_frac: float, out_frac: float) -> None:
        self._api.add_clip_trimmed(
            dto.AddClipTrimmed(
                path=path, duration_s=float(duration_s), in_frac=in_frac, out_frac=out_frac
            )
        )
        self.timelineChanged.emit()

    @Slot("QVariantList", result=int)
    def addFilesFromUrls(self, urls: list) -> int:
        """Add picked files (file:// URLs or paths) to the reel via the facade.

        Returns the index of the first clip added, or ``-1`` if nothing was added.
        """
        report = self._api.add_files_from_urls(
            dto.AddFilesFromUrls(urls=[self._url_to_str(u) for u in (urls or [])])
        )
        if report.added:
            self.timelineChanged.emit()
        # Tell the user what happened — never fail silently on a picked file.
        if report.requested and report.skipped:
            if report.added == 0:
                self.loadNotice.emit(
                    "No se pudo cargar ningún archivo (formato no compatible o ilegible)."
                )
            else:
                shown = ", ".join(report.skipped[:3]) + ("…" if len(report.skipped) > 3 else "")
                self.loadNotice.emit(
                    f"{report.added} de {report.requested} clips cargados · "
                    f"{len(report.skipped)} omitidos: {shown}"
                )
        return report.first_index

    @staticmethod
    def _url_to_str(raw: object) -> str:
        """Normalise a QML QUrl/string to a plain string the facade can parse."""
        from PySide6.QtCore import QUrl  # noqa: PLC0415

        if isinstance(raw, QUrl):
            local = raw.toLocalFile()
            return local or raw.toString()
        return str(raw)

    @Slot(int)
    def removeClip(self, index: int) -> None:
        self._api.remove_clip(index)
        self.timelineChanged.emit()

    @Slot(int, int)
    def moveClip(self, src: int, dst: int) -> None:
        self._api.move_clip(src, dst)
        self.timelineChanged.emit()

    @Slot(int, float, float)
    def setTrim(self, index: int, in_point_s: float, out_point_s: float) -> None:
        self._api.set_trim(index, in_point_s, out_point_s)
        self.timelineChanged.emit()

    @Slot(int, float, float)
    def setTrimFraction(self, index: int, in_frac: float, out_frac: float) -> None:
        tl = self._api.timeline
        if 0 <= index < len(tl):
            dur = tl[index].source_duration_s
            self._api.set_trim(index, in_frac * dur, out_frac * dur)
            self.timelineChanged.emit()

    @Slot()
    def clear(self) -> None:
        self._api.clear()
        self.timelineChanged.emit()

    # ── Sequencer helper (for the QML playhead) ───────────────────────
    @Slot(float, result="QVariantMap")
    def locate(self, global_pos_s: float) -> dict:
        hit = self._api.locate(global_pos_s)
        if hit is None:
            return {}
        return {
            "index": hit["index"],
            "localPos": hit["local_pos"],
            "sourcePath": hit["source_path"],
        }

    # ── Event markers (Fase 1) — pure sidecar read, no service ────────
    @Slot(str, result="QVariantList")
    def eventsForClip(self, clip_path: str) -> list:
        out = []
        for ev in read_sidecar(Path(clip_path)):
            out.append(
                {
                    "eventId": ev.event_id,
                    "type": ev.type,
                    "source": ev.source,
                    "start": ev.start.isoformat(),
                    "end": ev.end.isoformat(),
                    "confidence": ev.confidence if ev.confidence is not None else -1.0,
                }
            )
        return out

    # ── Export (bridge orchestrates for Qt progress feedback) ─────────
    def _default_output_path(self) -> Optional[Path]:
        out = self._api.default_output_path()
        return Path(out) if out else None

    @Slot()
    def exportReel(self) -> None:
        out = self._default_output_path()
        if out is None:
            self.exportFailed.emit("No hay carpeta de salida configurada.")
            return
        self.exportTimeline(str(out))

    @Slot(str)
    def exportTimeline(self, output_path: str) -> None:
        """Validate then export the reel on a background thread (Qt signals report progress)."""
        if self._exporting:
            logger.warning("[editor] export already in progress")
            return
        if self._api.export_port is None:
            self.exportFailed.emit("No hay motor de exportación configurado.")
            return
        errors = self._api.timeline.validate()
        if errors:
            self.exportFailed.emit(" ".join(errors))
            return
        self._exporting = True
        self.exportStarted.emit()
        threading.Thread(
            target=self._do_export, args=(output_path,), daemon=True, name="editor-export",
        ).start()

    def _do_export(self, output_path: str) -> None:
        try:
            self._api.export_port.export(
                self._api.timeline, Path(output_path), on_progress=self.exportProgress.emit
            )
            self.exportFinished.emit(output_path)
            logger.info("[editor] export finished: {}", output_path)
        except Exception as exc:  # noqa: BLE001
            logger.exception("[editor] export failed")
            self.exportFailed.emit(str(exc))
        finally:
            self._exporting = False
