"""RequestsApi — facade over the clip-request system (ADR-0009).

Covers the AppBridge request slots: enumerate storages/operators (via
:class:`FileBrowserPort`), create + send a clip request (Supervisor → IT), read
the inbox/outbox, and update a request's status (IT → Supervisor).  The WS
server/client are injected opaque transports (``send_request`` /
``send_status_update``); serialization/Qt live outside this facade.
"""
from __future__ import annotations

import json
import socket
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

from loguru import logger

from app.core.api import dto
from app.core.api.events import EventBus
from app.core.ports.file_browser_port import FileBrowserPort
from app.core.ports.request_port import ClipRequest, RequestPort


@dataclass(frozen=True)
class StorageInfo:
    name: str
    path: str
    operator_count: int


@dataclass(frozen=True)
class OperatorInfo:
    name: str
    storage: str  # storage share name only — no navigable path (security contract)


class RequestsApi:
    """Command surface for the Supervisor↔IT clip-request workflow."""

    def __init__(
        self,
        *,
        event_bus: EventBus,
        request_port: Optional[RequestPort] = None,
        file_browser: Optional[FileBrowserPort] = None,
        slc_storage_host: str = "",
        server=None,   # ClipRequestServer | None (IT)
        client=None,   # ClipRequestClient | None (Supervisor)
    ) -> None:
        self._bus = event_bus
        self._requests = request_port
        self._browser = file_browser
        self._host = slc_storage_host or r"\\SIG-SLC-Storage"
        self._server = server
        self._client = client

    def set_transports(self, *, server=None, client=None) -> None:
        self._server = server
        self._client = client

    def configure(self, *, request_port=None, slc_storage_host=None, server=None, client=None) -> None:
        """Wire the request system after construction (main.py's set_request_system)."""
        if request_port is not None:
            self._requests = request_port
        if slc_storage_host:
            self._host = slc_storage_host
        self._server = server
        self._client = client

    # ── Storage / operator enumeration ────────────────────────────────

    def list_storages(self) -> List[StorageInfo]:
        """Return the storage shares on the NAS with an operator-folder count."""
        if self._browser is None:
            return []
        shares = self._browser.list_shares(self._host)
        return [
            StorageInfo(
                name=s.name, path=s.path, operator_count=self._browser.count_dirs(s.path)
            )
            for s in shares
        ]

    def list_operators(self, storage_path: str) -> List[OperatorInfo]:
        """Operator folder NAMES inside one storage share (no navigable path)."""
        if self._browser is None:
            return []
        storage_name = storage_path.rstrip("\\/").rsplit("\\", 1)[-1].rsplit("/", 1)[-1]
        listing = self._browser.list_directory(storage_path)
        return [
            OperatorInfo(name=e.name, storage=storage_name)
            for e in listing.entries
            if e.is_dir
        ]

    def list_all_operators(self) -> List[OperatorInfo]:
        """Every operator across all storages, sorted by name."""
        ops: List[OperatorInfo] = []
        for storage in self.list_storages():
            ops.extend(self.list_operators(storage.path))
        return sorted(ops, key=lambda o: o.name.lower())

    # ── Request lifecycle ─────────────────────────────────────────────

    def send_clip_request(self, cmd: dto.SendClipRequest) -> bool:
        """Parse, persist, and send a clip request to the configured IT hosts."""
        if self._requests is None:
            logger.warning("[requests-api] send: request system not initialised.")
            return False
        try:
            data = json.loads(cmd.request_json)
            data["id"] = str(uuid.uuid4())
            data["created_at"] = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            data["supervisor_host"] = socket.gethostname()
            data["status"] = "pending"
            req = ClipRequest.from_dict(data)
        except (json.JSONDecodeError, KeyError, TypeError):
            logger.exception("[requests-api] send: invalid request JSON.")
            return False

        self._requests.save(req)
        if self._client is not None:
            self._client.send_request(req)
        else:
            logger.warning("[requests-api] send: no WS client — request saved locally only.")
        logger.info("Clip request {} created: {} / {}", req.id, req.operator, req.start_time)
        return True

    def inbox_requests(self) -> List[ClipRequest]:
        return list(self._requests.load_all()) if self._requests else []

    def my_requests(self) -> List[ClipRequest]:
        return list(self._requests.load_all()) if self._requests else []

    def update_request_status(self, cmd: dto.UpdateRequestStatus) -> None:
        """Persist a status change and broadcast it to the Supervisor (IT side)."""
        if self._requests is None:
            return
        self._requests.update_status(cmd.request_id, cmd.status)
        if self._server is not None:
            self._server.send_status_update(cmd.request_id, cmd.status)
        self._bus.publish(dto.RequestStatusChanged(request_id=cmd.request_id, status=cmd.status))
        self._bus.publish(dto.RequestReceived())

    # ── Inbound WS callbacks (from the request server/client) ─────────

    def on_request_received(self, req_id: str) -> None:
        """IT: a new request arrived from a Supervisor."""
        if self._requests is not None:
            self._requests.update_status(req_id, "pending")
        self._bus.publish(dto.RequestReceived())

    def on_status_received(self, req_id: str, status: str) -> None:
        """Supervisor: a previously sent request changed status."""
        if self._requests is not None:
            self._requests.update_status(req_id, status)
        self._bus.publish(dto.RequestStatusChanged(request_id=req_id, status=status))

    @property
    def server(self):
        return self._server
