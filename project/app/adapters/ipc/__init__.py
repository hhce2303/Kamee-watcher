"""adapters/ipc — authenticated local IPC over a Windows named pipe (ADR-0011).

The **only** place in the app that serializes the core/api contract. An input
adapter, interchangeable with the QML bridges, over the same facade layer:
command frames in → facade call → DTO response out; bus events streamed out.

Auth is the pipe's security descriptor (user-scoped SDDL) — no open TCP port.
Sensitive commands (start/stop/unlock/setRole) are audited by the facades, which
receive ``origin="ipc"`` so the audit row records where the command came from.
"""
from __future__ import annotations

from app.adapters.ipc.protocol import decode_frames, encode_frame
from app.adapters.ipc.router import IpcRouter

__all__ = ["IpcRouter", "encode_frame", "decode_frames"]
