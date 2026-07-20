"""NamedPipeIpcClient — minimal client for the IPC channel.

Used by the contract tests and as the basis for the future Tauri/React bridge.
Sends a command frame and reads response/event frames.  pywin32 is imported
lazily so the module imports without it.
"""
from __future__ import annotations

import itertools
from typing import Optional

from app.adapters.ipc.protocol import FrameDecoder, encode_frame

_BUF = 64 * 1024


class NamedPipeIpcClient:
    """Connect to the server pipe, send commands, read framed responses/events."""

    def __init__(self, pipe_name: str) -> None:
        self._pipe_name = pipe_name
        self._handle = None
        self._decoder = FrameDecoder()
        self._buffered: list[dict] = []   # frames decoded from the wire, FIFO
        self._events: list[dict] = []     # event frames seen while awaiting a response
        self._ids = itertools.count(1)

    def connect(self, timeout_ms: int = 5000) -> None:
        import win32file   # noqa: PLC0415
        import win32pipe    # noqa: PLC0415

        win32pipe.WaitNamedPipe(self._pipe_name, timeout_ms)
        self._handle = win32file.CreateFile(
            self._pipe_name,
            win32file.GENERIC_READ | win32file.GENERIC_WRITE,
            0, None, win32file.OPEN_EXISTING, 0, None,
        )

    def close(self) -> None:
        if self._handle is not None:
            import win32file  # noqa: PLC0415

            try:
                win32file.CloseHandle(self._handle)
            finally:
                self._handle = None

    # ── Request/response ──────────────────────────────────────────────

    def call(self, cmd: str, payload: Optional[dict] = None, max_reads: int = 100) -> dict:
        """Send *cmd* and return its response envelope (buffering event frames)."""
        req_id = str(next(self._ids))
        self._send({"id": req_id, "cmd": cmd, "payload": payload or {}})
        for _ in range(max_reads):
            frame = self._next_frame()
            if frame.get("id") == req_id and "ok" in frame:
                return frame
            if "event" in frame:
                self._events.append(frame)
        raise TimeoutError(f"no response for command '{cmd}'")

    def read_event(self, max_reads: int = 100) -> dict:
        """Return the next event frame (from the buffer or the wire)."""
        if self._events:
            return self._events.pop(0)
        for _ in range(max_reads):
            frame = self._next_frame()
            if "event" in frame:
                return frame
        raise TimeoutError("no event frame received")

    # ── Wire helpers ──────────────────────────────────────────────────

    def _send(self, obj: dict) -> None:
        import win32file  # noqa: PLC0415

        win32file.WriteFile(self._handle, encode_frame(obj))

    def _next_frame(self) -> dict:
        import win32file  # noqa: PLC0415

        while not self._buffered:
            _hr, data = win32file.ReadFile(self._handle, _BUF)
            for frame in self._decoder.feed(data):
                self._buffered.append(frame)
        return self._buffered.pop(0)
