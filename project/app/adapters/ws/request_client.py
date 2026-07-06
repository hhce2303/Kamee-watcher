from __future__ import annotations

import asyncio
import json
import threading
from typing import Callable, Dict, List, Optional

import websockets
from loguru import logger

from app.core.ports.request_port import ClipRequest


class ClipRequestClient:
    """WebSocket client that sends clip requests to IT PCs.

    Runs its own asyncio event loop on a background thread (Qt-free). Keeps
    one persistent connection per configured host open so status updates from
    IT arrive without polling.

    Protocol: see :class:`app.adapters.ws.request_server.ClipRequestServer`.
    """

    def __init__(
        self,
        hosts: List[str],
        port: int,
        on_status_received: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        self._hosts = list(hosts)
        self._port = port
        self._on_status_received = on_status_received
        self._connections: Dict[str, object] = {}
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, name="clip-request-client", daemon=True)
        self._thread.start()

    def set_hosts(self, hosts: List[str]) -> None:
        """Update the target host list (e.g. when the user adds a new IT PC)."""
        self._hosts = list(hosts)

    def send_request(self, req: ClipRequest) -> None:
        """Send the request to every configured IT host (fire-and-forget)."""
        if not self._hosts:
            logger.warning("ClipRequestClient: no IT hosts configured — request not sent.")
            return
        payload = json.dumps({"type": "clip_request", "request": req.to_dict()})
        for host in self._hosts:
            asyncio.run_coroutine_threadsafe(self._send_to_host(host, payload), self._loop)

    def disconnect_all(self) -> None:
        fut = asyncio.run_coroutine_threadsafe(self._close_all(), self._loop)
        try:
            fut.result(timeout=5)
        except Exception:  # noqa: BLE001
            logger.exception("ClipRequestClient: error closing connections.")

    def stop(self) -> None:
        """Stop the background event loop. Call after :meth:`disconnect_all`."""
        self.disconnect_all()
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)

    # ── Event-loop thread ────────────────────────────────────────────

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    async def _send_to_host(self, host: str, payload: str) -> None:
        try:
            ws = await self._get_connection(host)
            await ws.send(payload)
            logger.info("ClipRequestClient: request sent to {}.", host)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ClipRequestClient: error connecting to {}: {}", host, exc)

    async def _get_connection(self, host: str):
        ws = self._connections.get(host)
        if ws is not None and not ws.closed:
            return ws
        logger.info("ClipRequestClient: connecting to {} …", host)
        ws = await websockets.connect(f"ws://{host}:{self._port}")
        self._connections[host] = ws
        asyncio.ensure_future(self._listen(host, ws))
        return ws

    async def _listen(self, host: str, ws) -> None:
        try:
            async for raw in ws:
                self._on_message(raw)
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self._connections.pop(host, None)
            logger.debug("ClipRequestClient: disconnected from {}.", host)

    def _on_message(self, raw: str) -> None:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return

        msg_type = data.get("type")
        if msg_type == "ack":
            logger.info("ClipRequestClient: ack for request {}.", data.get("id"))
        elif msg_type == "status_update":
            req_id = data.get("id", "")
            status = data.get("status", "")
            if req_id and status:
                logger.info("ClipRequestClient: status update {} → {}.", req_id, status)
                if self._on_status_received is not None:
                    self._on_status_received(req_id, status)

    async def _close_all(self) -> None:
        for ws in list(self._connections.values()):
            await ws.close()
        self._connections.clear()
