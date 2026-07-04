"""IPC named-pipe integration — real pipe round-trip + streamed events (ADR-0011).

Exercises the full transport: server on a user-scoped pipe, a client sends a
command and gets a DTO response, and a bus event is streamed to the client.
Requires pywin32 (skipped otherwise).
"""
from __future__ import annotations

import os

import pytest

pytest.importorskip("win32pipe")

from app.adapters.ipc.pipe_client import NamedPipeIpcClient
from app.adapters.ipc.pipe_server import NamedPipeIpcServer
from app.adapters.ipc.router import IpcRouter
from app.core.api.bootstrap import build_api_layer
from app.core.recording_service.models import MonitorInfo

_counter = 0


class FakeDetection:
    def get_monitors(self):
        return [MonitorInfo(name="\\\\.\\DISPLAY1", width=1920, height=1080, x=0, y=0, is_primary=True, index=0)]


class FakeRecording:
    def __init__(self):
        self.started = False

    def is_recording(self):
        return self.started

    def start(self):
        self.started = True

    def stop(self):
        self.started = False

    def total_stored_duration_seconds(self):
        return 0.0

    def change_monitors(self, monitors):
        pass


class Cfg:
    role = "it"
    autorecord = True
    selected_monitor_fingerprints: list = []


class FakeUserConfigPort:
    def load(self):
        return Cfg()

    def save(self, cfg):
        pass


class FakeSettings:
    it_pin = "4321"


def _unique_pipe_name() -> str:
    global _counter
    _counter += 1
    return rf"\\.\pipe\TheWatcher.test.{os.getpid()}.{_counter}"


@pytest.fixture
def server_and_client():
    layer = build_api_layer(
        detection_service=FakeDetection(),
        settings=FakeSettings(),
        user_config_port=FakeUserConfigPort(),
        recording_service=FakeRecording(),
        start_bus=True,   # dispatcher running so events stream
    )
    router = IpcRouter(layer)
    server = NamedPipeIpcServer(router, layer.bus, pipe_name=_unique_pipe_name())
    server.start()
    client = NamedPipeIpcClient(server.pipe_name)
    client.connect(timeout_ms=5000)
    try:
        yield server, client, layer
    finally:
        client.close()
        server.stop()
        layer.stop()


def test_command_round_trip(server_and_client) -> None:
    _server, client, _layer = server_and_client
    resp = client.call("get_recording_state")
    assert resp["ok"] is True
    assert resp["result"]["is_recording"] is False


def test_get_monitors_over_pipe(server_and_client) -> None:
    _server, client, _layer = server_and_client
    resp = client.call("get_monitors")
    assert resp["ok"] is True
    assert resp["result"][0]["resolution"] == "1920×1080"


def test_start_recording_streams_state_event(server_and_client) -> None:
    _server, client, _layer = server_and_client
    resp = client.call("start_recording")
    assert resp["ok"] is True and resp["result"]["is_recording"] is True
    # The facade published RecordingStateChanged on the bus → streamed to us.
    event = client.read_event()
    assert event["event"] == "recording_state_changed"
    assert event["state"]["is_recording"] is True


def test_unknown_command_over_pipe(server_and_client) -> None:
    _server, client, _layer = server_and_client
    resp = client.call("bogus_cmd")
    assert resp["ok"] is False and "unknown command" in resp["error"]
