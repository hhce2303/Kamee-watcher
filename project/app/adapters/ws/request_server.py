from __future__ import annotations

import asyncio
import json
import threading
from typing import Callable, Optional, Set

import websockets
from loguru import logger

from app.core.ports.request_port import ClipRequest, RequestPort


class ClipRequestServer:
    """WebSocket server that receives clip requests from Supervisor PCs.

    Runs on the IT PC, bound to ``0.0.0.0:{port}``, on a dedicated background
    thread with its own asyncio event loop (Qt-free — ``adapters/`` know their
    transport, but not a UI framework; ADR-0009).

    Protocol (unchanged from the previous Qt implementation, so IT and
    Supervisor machines stay interoperable across a mixed-version rollout):
        Supervisor -> IT : ``{"type": "clip_request", "request": {...}}``
        IT -> Supervisor : ``{"type": "ack", "id": "..."}``
        IT -> all clients: ``{"type": "status_update", "id": "...", "status": "..."}``
    """

    def __init__(
        self,
        port: int,
        request_adapter: RequestPort,
        on_request_received: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._port = port
        self._adapter = request_adapter
        self._on_request_received = on_request_received
        self._clients: Set = set()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._server = None
        self._started = threading.Event()
        self._ok = False
        self._bound_port: Optional[int] = None

    @property
    def bound_port(self) -> Optional[int]:
        """Actual listening port — resolves ``port=0`` to the OS-assigned port (tests)."""
        return self._bound_port

    def start(self) -> bool:
        """Start the server thread and block until bound (or bind fails)."""
        self._thread = threading.Thread(target=self._run, name="clip-request-server", daemon=True)
        self._thread.start()
        self._started.wait(timeout=5)
        return self._ok

    def stop(self) -> None:
        if self._loop is None:
            return
        # _shutdown() must NOT stop the loop itself — run_coroutine_threadsafe's
        # future is resolved by a callback the loop schedules after the task
        # finishes, so stopping the loop from inside the same task races that
        # callback and this future never resolves (waits out the full timeout).
        # Stop the loop separately, only after _shutdown() has actually returned.
        fut = asyncio.run_coroutine_threadsafe(self._shutdown(), self._loop)
        try:
            fut.result(timeout=5)
        except Exception:  # noqa: BLE001
            logger.exception("ClipRequestServer: error during shutdown.")
        self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("ClipRequestServer stopped.")

    def send_status_update(self, req_id: str, status: str) -> None:
        """Broadcast a status update to all connected Supervisor clients."""
        if self._loop is None:
            return
        msg = json.dumps({"type": "status_update", "id": req_id, "status": status})
        asyncio.run_coroutine_threadsafe(self._broadcast(msg), self._loop)

    # ── Event-loop thread ────────────────────────────────────────────

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._bind())
        except Exception:  # noqa: BLE001
            logger.exception("ClipRequestServer: failed to bind on port {}.", self._port)
            self._ok = False
            self._started.set()
            return
        if self._ok:
            self._loop.run_forever()

    async def _bind(self) -> None:
        try:
            self._server = await websockets.serve(self._handle_client, "0.0.0.0", self._port)
            self._bound_port = self._server.sockets[0].getsockname()[1]
            self._ok = True
            logger.info("ClipRequestServer listening on port {}.", self._bound_port)
        except OSError as exc:
            logger.error("ClipRequestServer failed to bind on port {}: {}", self._port, exc)
            self._ok = False
        finally:
            self._started.set()

    async def _shutdown(self) -> None:
        for client in list(self._clients):
            await client.close()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    # ── Per-connection handler ───────────────────────────────────────

    async def _handle_client(self, websocket) -> None:
        self._clients.add(websocket)
        logger.info("IT server: client connected from {}.", websocket.remote_address)
        try:
            async for raw in websocket:
                await self._on_message(raw, websocket)
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self._clients.discard(websocket)
            logger.info("IT server: client disconnected.")

    async def _on_message(self, raw: str, websocket) -> None:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("IT server: received invalid JSON — ignored.")
            return

        msg_type = data.get("type")
        if msg_type == "clip_request":
            payload = data.get("request", {})
            try:
                req = ClipRequest.from_dict(payload)
            except (KeyError, TypeError):
                logger.warning("IT server: malformed clip_request payload — ignored.")
                return

            self._adapter.save(req)
            logger.info(
                "IT server: request {} received — {} / {}",
                req.id, req.operator, req.start_time,
            )
            await websocket.send(json.dumps({"type": "ack", "id": req.id}))
            if self._on_request_received is not None:
                self._on_request_received(req.id)
        else:
            logger.debug("IT server: unhandled message type '{}'.", msg_type)

    async def _broadcast(self, msg: str) -> None:
        dead = []
        for client in list(self._clients):
            try:
                await client.send(msg)
            except websockets.exceptions.ConnectionClosed:
                dead.append(client)
        for client in dead:
            self._clients.discard(client)
