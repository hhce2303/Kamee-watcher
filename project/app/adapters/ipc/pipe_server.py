"""NamedPipeIpcServer — Windows named-pipe transport for the IPC channel.

Thin: it owns the pipe lifecycle and framing, and delegates every command to the
:class:`IpcRouter`.  It subscribes to the EventBus and streams event frames to the
connected client.  Auth is the pipe's user-scoped security descriptor (ADR-0011);
no TCP port is opened.

Single client at a time (the Tauri UI is one client); the accept loop handles
reconnection.  pywin32 is imported lazily so this module imports without it —
:meth:`start` raises a clear error if it is missing.
"""
from __future__ import annotations

import queue
import threading
from typing import Optional

from loguru import logger

from app.adapters.ipc.protocol import FrameDecoder, encode_frame
from app.adapters.ipc.router import IpcRouter
from app.adapters.ipc import security
from app.core.api.events import EventBus

_BUF = 64 * 1024
_POLL_SECONDS = 0.01   # serve-loop tick when idle (control events are tiny)


class NamedPipeIpcServer:
    """Serve the IPC contract over a user-scoped Windows named pipe."""

    def __init__(
        self,
        router: IpcRouter,
        event_bus: EventBus,
        pipe_name: Optional[str] = None,
    ) -> None:
        self._router = router
        self._bus = event_bus
        self._pipe_name = pipe_name or security.default_pipe_name()
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._handle = None            # current pipe instance handle
        self._subscription = None
        self._ready = threading.Event()   # set once the pipe exists (start() waits)
        # Events are enqueued by the bus dispatcher thread and flushed by the
        # single serve thread — ALL pipe I/O happens on that one thread, so a
        # blocking read never serializes against an event write (synchronous
        # named-pipe handles deadlock otherwise).
        self._event_q: "queue.Queue[bytes]" = queue.Queue(maxsize=4096)

    @property
    def pipe_name(self) -> str:
        return self._pipe_name

    def start(self) -> None:
        """Start the accept/serve loop on a background thread. Idempotent."""
        if self._running:
            return
        # Fail fast + clearly if the transport dependency is missing.
        import win32pipe  # noqa: F401, PLC0415

        self._running = True
        self._ready.clear()
        self._subscription = self._bus.subscribe(None, self._on_event)
        self._thread = threading.Thread(target=self._run, name="ipc-pipe", daemon=True)
        self._thread.start()
        # Block until the pipe actually exists so a client connecting right after
        # start() does not race CreateNamedPipe (WaitNamedPipe → file-not-found).
        if not self._ready.wait(timeout=5.0):
            logger.warning("[ipc] pipe did not become ready within 5s")
        logger.info("[ipc] named-pipe server listening on {}", self._pipe_name)

    def stop(self, timeout: float = 2.0) -> None:
        if not self._running:
            return
        self._running = False
        if self._subscription is not None:
            self._subscription.cancel()
            self._subscription = None
        # Unblock a ConnectNamedPipe wait by opening a throwaway client.
        self._nudge()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None
        logger.info("[ipc] named-pipe server stopped.")

    # ── Accept / serve loop ───────────────────────────────────────────

    def _run(self) -> None:
        import win32pipe        # noqa: PLC0415
        import win32file        # noqa: PLC0415
        import pywintypes       # noqa: PLC0415
        import winerror         # noqa: PLC0415

        sa = self._safe_security_attributes()
        while self._running:
            try:
                handle = win32pipe.CreateNamedPipe(
                    self._pipe_name,
                    win32pipe.PIPE_ACCESS_DUPLEX,
                    win32pipe.PIPE_TYPE_BYTE | win32pipe.PIPE_READMODE_BYTE | win32pipe.PIPE_WAIT,
                    win32pipe.PIPE_UNLIMITED_INSTANCES,
                    _BUF, _BUF, 0, sa,
                )
            except pywintypes.error:
                logger.exception("[ipc] CreateNamedPipe failed")
                self._ready.set()  # unblock start() even on failure
                return
            self._ready.set()  # the pipe now exists — clients may connect
            try:
                # ERROR_PIPE_CONNECTED means a client connected between Create and
                # Connect — that is success, not a failure (classic named-pipe race).
                try:
                    win32pipe.ConnectNamedPipe(handle, None)
                except pywintypes.error as exc:
                    if exc.winerror != winerror.ERROR_PIPE_CONNECTED:
                        raise
                if not self._running:
                    win32file.CloseHandle(handle)
                    break
                self._handle = handle
                self._serve_client(handle)
            except pywintypes.error as exc:
                logger.debug("[ipc] connection ended: {}", exc)
            finally:
                self._handle = None
                self._drain_event_queue()  # discard events buffered for a gone client
                try:
                    win32pipe.DisconnectNamedPipe(handle)
                    win32file.CloseHandle(handle)
                except Exception:  # noqa: BLE001
                    pass

    def _serve_client(self, handle) -> None:
        """Single-threaded I/O: poll for commands, flush queued events. No
        concurrent read/write on the synchronous handle (would deadlock)."""
        import win32file        # noqa: PLC0415
        import win32pipe        # noqa: PLC0415
        import pywintypes       # noqa: PLC0415
        import winerror         # noqa: PLC0415

        decoder = FrameDecoder()
        while self._running:
            # 1. Serve any pending commands (non-blocking peek → read → respond).
            try:
                _data, avail, _left = win32pipe.PeekNamedPipe(handle, 0)
            except pywintypes.error as exc:
                if exc.winerror in (winerror.ERROR_BROKEN_PIPE, winerror.ERROR_PIPE_NOT_CONNECTED):
                    return  # client disconnected
                raise
            if avail:
                try:
                    _hr, data = win32file.ReadFile(handle, min(avail, _BUF))
                except pywintypes.error:
                    return
                for request in decoder.feed(data):
                    self._raw_write(handle, encode_frame(self._router.handle(request)))
                continue  # loop back to drain any more buffered commands promptly
            # 2. Idle: block briefly for an event (near-zero event latency); the
            #    timeout bounds command latency to one tick. All I/O on this thread.
            try:
                frame = self._event_q.get(timeout=_POLL_SECONDS)
            except queue.Empty:
                continue
            self._raw_write(handle, frame)
            self._flush_events(handle)  # drain any burst

    # ── Event streaming ───────────────────────────────────────────────

    def _on_event(self, event: object) -> None:
        """Bus subscriber (bus dispatcher thread) — enqueue only, never write."""
        payload = event.model_dump(mode="json") if hasattr(event, "model_dump") else None
        if payload is None:
            return
        try:
            self._event_q.put_nowait(encode_frame(payload))
        except queue.Full:
            pass  # slow/dead client — drop control events rather than block the bus

    def _flush_events(self, handle) -> None:
        while True:
            try:
                frame = self._event_q.get_nowait()
            except queue.Empty:
                return
            self._raw_write(handle, frame)

    def _drain_event_queue(self) -> None:
        while True:
            try:
                self._event_q.get_nowait()
            except queue.Empty:
                return

    def _raw_write(self, handle, data: bytes) -> None:
        import win32file  # noqa: PLC0415

        win32file.WriteFile(handle, data)

    # ── Helpers ───────────────────────────────────────────────────────

    def _safe_security_attributes(self):
        try:
            return security.make_security_attributes()
        except Exception:  # noqa: BLE001
            logger.exception("[ipc] could not build security attributes — using default ACL")
            return None

    def _nudge(self) -> None:
        """Open + close a client handle to unblock a pending ConnectNamedPipe."""
        try:
            import win32file  # noqa: PLC0415

            h = win32file.CreateFile(
                self._pipe_name,
                win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                0, None, win32file.OPEN_EXISTING, 0, None,
            )
            win32file.CloseHandle(h)
        except Exception:  # noqa: BLE001
            pass
