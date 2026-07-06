"""DeliveryApi — facade over OneDrive folder+link delivery (ADR-0009).

Covers the AppBridge OneDrive slots' logic: derive the destination folder
(``<base>/<operator>/<YYYY-MM>``) from config + the active request, and produce a
share link via :class:`CloudShareService`.  The (slow) cloud call runs
synchronously here; the QML bridge marshals it off the UI thread and this facade
also publishes ``OneDriveChanged`` for the IPC consumer.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from loguru import logger

from app.core.api import dto
from app.core.api.events import EventBus
from app.core.ports.request_port import RequestPort


class DeliveryApi:
    """Command surface for delivering a reel to a shared OneDrive folder."""

    def __init__(
        self,
        *,
        event_bus: EventBus,
        cloud_share_service=None,   # CloudShareService | None
        onedrive_base_folder: str = "SLC/clips-supervisor",
        request_port: Optional[RequestPort] = None,
    ) -> None:
        self._bus = event_bus
        self._service = cloud_share_service
        self._base = onedrive_base_folder
        self._requests = request_port
        self._state = "idle"
        self._folder = ""
        self._link = ""

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
