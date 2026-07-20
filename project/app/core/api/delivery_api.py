"""DeliveryApi — facade over OneDrive folder+link delivery (ADR-0009).

Covers the AppBridge OneDrive slots' logic: derive the destination folder
(``<base>/<operator>/<YYYY-MM>``) from config + the active request, and produce a
share link via :class:`CloudShareService`.  The (slow) cloud call runs
synchronously here; the QML bridge marshals it off the UI thread and this facade
also publishes ``OneDriveChanged`` for the IPC consumer.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from loguru import logger

from app.core.api import dto
from app.core.api.events import EventBus
from app.core.ports.request_port import RequestPort


class DeliveryApi:
    """Command surface for delivering a reel to OneDrive — shared (with a link)
    or private (folder only, no link)."""

    def __init__(
        self,
        *,
        event_bus: EventBus,
        cloud_share_service=None,   # CloudShareService | None
        onedrive_base_folder: str = "SLC/clips-supervisor",
        request_port: Optional[RequestPort] = None,
        export_fn: Optional[Callable[[str], None]] = None,
        is_exporting: Optional[Callable[[], bool]] = None,
    ) -> None:
        self._bus = event_bus
        self._service = cloud_share_service
        self._base = onedrive_base_folder
        self._requests = request_port
        self._state = "idle"
        self._folder = ""
        self._link = ""
        # Private-save orchestration: reuses EditorApi's own export (injected as
        # plain callables so this facade never imports EditorApi directly — see
        # bootstrap.build_api_layer).
        self._export_fn = export_fn
        self._is_exporting = is_exporting
        self._pending: Optional[dict] = None
        self._bus.subscribe(dto.ExportFinished, self._on_export_finished)
        self._bus.subscribe(dto.ExportFailed, self._on_export_failed)

    @property
    def available(self) -> bool:
        return self._service is not None

    def set_request_port(self, request_port: Optional[RequestPort]) -> None:
        """Wire the request port after construction (for active-operator lookup)."""
        self._requests = request_port

    def compute_folder_path(self) -> str:
        """Derive ``<base>/<operator>/<YYYY-MM>`` (operator omitted if unknown)."""
        month = datetime.now().strftime("%Y-%m")
        operator = self._active_operator()
        segments = [self._base, operator, month]
        return "/".join(s.strip("/ ") for s in segments if s and s.strip("/ "))

    def ensure_folder_and_link(self, folder_path: str) -> dto.ShareResultDTO:
        """Create the folder (+parents) and mint a share link. Raises on failure.

        Publishes ``OneDriveChanged`` (linked) on success; the caller decides how
        to surface an exception (the QML bridge maps it to an error state).
        """
        if self._service is None:
            raise RuntimeError("OneDrive no está configurado.")
        path = (folder_path or "").strip() or self.compute_folder_path()
        result = self._service.ensure_folder_and_link(path)
        share = dto.ShareResultDTO(folder_path=result.folder_path, share_link=result.share_link)
        self._state, self._folder, self._link = "linked", share.folder_path, share.share_link
        self._bus.publish(dto.OneDriveChanged(state=self._state, folder=self._folder, link=self._link))
        return share

    def reset_onedrive(self) -> None:
        """Clear delivery state (e.g. before starting a fresh free-edit session)."""
        if (self._state, self._folder, self._link) == ("idle", "", ""):
            return
        self._state, self._folder, self._link = "idle", "", ""
        self._bus.publish(dto.OneDriveChanged(state="idle", folder="", link=""))

    def ensure_folder(self, folder_path: str = "") -> str:
        """Resolve and create the OneDrive folder — no link. Raises on failure."""
        if self._service is None:
            raise RuntimeError("OneDrive no está configurado.")
        path = (folder_path or "").strip() or self.compute_folder_path()
        return self._service.ensure_folder(path)

    def save_reel_privately(self, folder_path: str = "") -> None:
        """Export the current reel straight into the (private, link-less)
        OneDrive folder, as one action. Reuses EditorApi's own export via the
        injected ``export_fn`` rather than duplicating export logic; the actual
        success/failure is reported later, from the bus, once export finishes.

        FUTURE escalation to sharing: add e.g. ``share_saved_reel()`` that calls
        ``self._service.ensure_folder_and_link()`` (already implemented) against
        the last folder used here — additive, no restructuring needed.
        """
        if self._pending is not None:
            logger.warning("[delivery-api] private save already in progress — ignoring.")
            return
        if self._export_fn is None or self._is_exporting is None:
            self._bus.publish(dto.OneDriveSaveFailed(message="Exportador no configurado."))
            return
        if self._is_exporting():
            self._bus.publish(dto.OneDriveSaveFailed(message="Ya hay una exportación en curso."))
            return
        try:
            folder = self.ensure_folder(folder_path)
        except Exception as exc:  # noqa: BLE001
            self._bus.publish(dto.OneDriveSaveFailed(message=str(exc)))
            return
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        output_path = str(Path(folder) / f"reel_{stamp}.mp4")
        self._pending = {"folder": folder, "output_path": output_path}
        self._bus.publish(dto.OneDriveSaveStarted())
        self._export_fn(output_path)

    def _on_export_finished(self, ev: dto.ExportFinished) -> None:
        if self._pending is None or ev.output_path != self._pending["output_path"]:
            return  # not ours — e.g. a plain export from ExportDialog
        self._bus.publish(dto.OneDriveSaved(folder_path=self._pending["folder"], output_path=ev.output_path))
        self._pending = None

    def _on_export_failed(self, ev: dto.ExportFailed) -> None:
        if self._pending is None:
            return  # ExportFailed carries no path — only ours if we're waiting
        self._bus.publish(dto.OneDriveSaveFailed(message=ev.message))
        self._pending = None

    def _active_operator(self) -> str:
        """Operator of the current pending/processing request, or ''."""
        if self._requests is None:
            return ""
        try:
            for req in self._requests.load_all():
                if getattr(req, "status", "") in ("pending", "processing"):
                    return getattr(req, "operator", "") or ""
        except Exception:  # noqa: BLE001
            logger.warning("[delivery-api] could not resolve active operator.")
        return ""
