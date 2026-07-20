"""Qt-free WS request server/client — real roundtrip over an ephemeral port.

Ports the coverage from the deleted Qt-based test_ws_inbound.py/test_ws_outbound.py.
No Qt, no qt_app fixture: ClipRequestServer/Client are plain asyncio-on-a-thread
adapters (ADR-0009, C1 of the Tauri migration).
"""
from __future__ import annotations

import time

import pytest

from app.adapters.ws.request_client import ClipRequestClient
from app.adapters.ws.request_server import ClipRequestServer
from app.core.ports.request_port import ClipRequest


class InMemoryRequestPort:
    def __init__(self):
        self._items: dict[str, ClipRequest] = {}

    def save(self, req: ClipRequest) -> None:
        self._items[req.id] = req

    def load_all(self):
        return list(self._items.values())

    def update_status(self, req_id: str, status: str) -> None:
        if req_id in self._items:
            self._items[req_id].status = status


def _wait_until(predicate, timeout=5.0, interval=0.05) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


def _make_request(rid="r1", operator="Operator-28") -> ClipRequest:
    return ClipRequest(
        id=rid,
        created_at="2026-07-06T00:00:00Z",
        supervisor_host="SUP-PC",
        operator=operator,
        storage="Storage1",
        start_time="2026-07-06 10:00",
        end_time="2026-07-06 10:30",
        description="test incident",
        status="pending",
    )


@pytest.fixture
def server():
    adapter = InMemoryRequestPort()
    received: list[str] = []
    srv = ClipRequestServer(port=0, request_adapter=adapter, on_request_received=received.append)
    assert srv.start() is True
    srv.received = received  # type: ignore[attr-defined]
    srv.adapter = adapter  # type: ignore[attr-defined]
    yield srv
    srv.stop()


def test_server_binds_to_an_ephemeral_port(server) -> None:
    assert server.bound_port is not None and server.bound_port > 0


def test_client_sends_request_server_saves_and_notifies(server) -> None:
    statuses: list[tuple[str, str]] = []
    client = ClipRequestClient(
        hosts=["127.0.0.1"], port=server.bound_port, on_status_received=lambda i, s: statuses.append((i, s))
    )
    try:
        req = _make_request()
        client.send_request(req)

        assert _wait_until(lambda: len(server.received) == 1)
        assert server.received == ["r1"]
        assert server.adapter.load_all()[0].operator == "Operator-28"
    finally:
        client.stop()


def test_server_broadcasts_status_update_to_client(server) -> None:
    statuses: list[tuple[str, str]] = []
    client = ClipRequestClient(
        hosts=["127.0.0.1"], port=server.bound_port, on_status_received=lambda i, s: statuses.append((i, s))
    )
    try:
        client.send_request(_make_request())
        assert _wait_until(lambda: len(server.received) == 1)

        server.send_status_update("r1", "processing")

        assert _wait_until(lambda: statuses == [("r1", "processing")])
    finally:
        client.stop()


def test_client_with_no_hosts_does_not_raise() -> None:
    client = ClipRequestClient(hosts=[], port=9999)
    try:
        client.send_request(_make_request())  # should log + no-op, not raise
    finally:
        client.stop()


def test_set_hosts_updates_target_list(server) -> None:
    client = ClipRequestClient(hosts=[], port=server.bound_port)
    try:
        client.set_hosts(["127.0.0.1"])
        client.send_request(_make_request(rid="r2"))
        assert _wait_until(lambda: "r2" in server.received)
    finally:
        client.stop()


def test_malformed_json_is_ignored_not_fatal(server) -> None:
    # Exercise the server's own parser directly (no client plumbing needed
    # for "not fatal" — a real client can't easily send invalid JSON).
    import asyncio

    class FakeWs:
        sent = []

        async def send(self, msg):
            self.sent.append(msg)

    fut = asyncio.run_coroutine_threadsafe(server._on_message("not json", FakeWs()), server._loop)
    fut.result(timeout=5)  # must not raise
