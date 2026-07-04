"""IPC wire protocol — length-prefixed JSON frames.

Each frame is a 4-byte big-endian unsigned length followed by that many bytes of
UTF-8 JSON.  Framing is transport-agnostic (works over a byte pipe or any stream)
and lets the reader recover discrete messages from a byte stream.

Message shapes (all JSON objects)::

    request   {"id": "<str>", "cmd": "<name>", "payload": {...}}
    response  {"id": "<str>", "ok": true,  "result": <json>}
              {"id": "<str>", "ok": false, "error": "<str>"}
    event     {"event": "<discriminator>", ...}   # a DTO event, model_dump'd
"""
from __future__ import annotations

import json
import struct
from typing import Iterator

_HEADER = struct.Struct(">I")  # 4-byte big-endian unsigned length
MAX_FRAME = 32 * 1024 * 1024   # 32 MiB guard against a bad/huge length prefix


def encode_frame(obj: dict) -> bytes:
    """Serialize *obj* to a length-prefixed JSON frame."""
    body = json.dumps(obj, separators=(",", ":")).encode("utf-8")
    if len(body) > MAX_FRAME:
        raise ValueError(f"frame too large: {len(body)} bytes")
    return _HEADER.pack(len(body)) + body


class FrameDecoder:
    """Incremental decoder — feed it bytes, iterate whole frames as they complete."""

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, chunk: bytes) -> Iterator[dict]:
        self._buf.extend(chunk)
        while True:
            if len(self._buf) < _HEADER.size:
                return
            (length,) = _HEADER.unpack_from(self._buf, 0)
            if length > MAX_FRAME:
                raise ValueError(f"frame length {length} exceeds max {MAX_FRAME}")
            if len(self._buf) < _HEADER.size + length:
                return
            start = _HEADER.size
            body = bytes(self._buf[start:start + length])
            del self._buf[: start + length]
            yield json.loads(body.decode("utf-8"))


def decode_frames(data: bytes) -> list[dict]:
    """Decode all complete frames in *data* (convenience for tests/whole buffers)."""
    dec = FrameDecoder()
    return list(dec.feed(data))
