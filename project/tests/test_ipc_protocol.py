"""IPC wire protocol — length-prefixed framing round-trips and partial reads."""
from __future__ import annotations

import pytest

from app.adapters.ipc.protocol import FrameDecoder, decode_frames, encode_frame


def test_round_trip_single_frame() -> None:
    obj = {"id": "1", "cmd": "start_recording", "payload": {}}
    frames = decode_frames(encode_frame(obj))
    assert frames == [obj]


def test_multiple_frames_in_one_buffer() -> None:
    a = {"id": "1", "ok": True, "result": 1}
    b = {"event": "recording_state_changed", "state": {"is_recording": True}}
    frames = decode_frames(encode_frame(a) + encode_frame(b))
    assert frames == [a, b]


def test_partial_frame_waits_for_rest() -> None:
    obj = {"id": "1", "cmd": "x", "payload": {"k": "v" * 100}}
    blob = encode_frame(obj)
    dec = FrameDecoder()
    # Feed byte-by-byte in two halves — nothing decodes until the frame completes.
    assert list(dec.feed(blob[:10])) == []
    out = list(dec.feed(blob[10:]))
    assert out == [obj]


def test_two_frames_split_across_chunks() -> None:
    a, b = {"id": "a", "ok": True}, {"id": "b", "ok": True}
    blob = encode_frame(a) + encode_frame(b)
    dec = FrameDecoder()
    mid = len(encode_frame(a)) + 2
    got = list(dec.feed(blob[:mid])) + list(dec.feed(blob[mid:]))
    assert got == [a, b]


def test_oversize_length_rejected() -> None:
    import struct
    bad = struct.pack(">I", 999_999_999) + b"{}"
    with pytest.raises(ValueError):
        list(FrameDecoder().feed(bad))


def test_unicode_payload() -> None:
    obj = {"id": "1", "result": "Operador · 1440×900 café"}
    assert decode_frames(encode_frame(obj)) == [obj]
