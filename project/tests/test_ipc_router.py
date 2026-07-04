"""IpcRouter — command dispatch, response envelopes, and IPC audit (ADR-0011).

The audited commands must record origin="ipc" (a client cannot spoof "ui"), which
is enforced by the router constructing the DTOs with origin="ipc" and the facades'
AuditPort recording them.
"""
from __future__ import annotations

from app.adapters.ipc.router import IpcRouter
from app.core.api.bootstrap import build_api_layer
from app.core.recording_service.models import MonitorInfo


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
        return 5.0

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


class FakeAudit:
    def __init__(self):
        self.entries = []

    def record(self, command, origin, timestamp, detail="", success=True):
        self.entries.append((command, origin, detail, success))


def _layer(audit=None, recording=None):
    return build_api_layer(
        detection_service=FakeDetection(),
        settings=FakeSettings(),
        user_config_port=FakeUserConfigPort(),
        audit_port=audit,
        recording_service=recording or FakeRecording(),
        relaunch_cb=lambda: None,
    )


def test_get_recording_state() -> None:
    router = IpcRouter(_layer())
    resp = router.handle({"id": "1", "cmd": "get_recording_state"})
    assert resp["ok"] is True
    assert resp["result"]["is_recording"] is False


def test_get_monitors_returns_dtos() -> None:
    router = IpcRouter(_layer())
    resp = router.handle({"id": "2", "cmd": "get_monitors"})
    assert resp["ok"] is True
    assert isinstance(resp["result"], list) and resp["result"][0]["resolution"] == "1920×1080"


def test_start_recording_audited_as_ipc() -> None:
    audit = FakeAudit()
    rec = FakeRecording()
    router = IpcRouter(_layer(audit=audit, recording=rec))
    resp = router.handle({"id": "3", "cmd": "start_recording"})
    assert resp["ok"] is True
    assert rec.started is True
    assert ("startRecording", "ipc", "", True) in audit.entries


def test_stop_recording_audited_as_ipc() -> None:
    audit = FakeAudit()
    router = IpcRouter(_layer(audit=audit))
    router.handle({"id": "4", "cmd": "stop_recording"})
    assert any(c == "stopRecording" and o == "ipc" for (c, o, _d, _s) in audit.entries)


def test_set_role_audited_as_ipc_origin() -> None:
    audit = FakeAudit()
    router = IpcRouter(_layer(audit=audit))  # role "it" can change role
    resp = router.handle({"id": "5", "cmd": "set_role", "payload": {"role": "supervisor"}})
    assert resp["ok"] is True and resp["result"]["applied"] is True
    assert any(c == "setRole" and o == "ipc" for (c, o, _d, _s) in audit.entries)


def test_unlock_it_via_ipc() -> None:
    audit = FakeAudit()
    router = IpcRouter(_layer(audit=audit))
    ok_resp = router.handle({"id": "6", "cmd": "unlock_it", "payload": {"pin": "4321"}})
    assert ok_resp["result"]["ok"] is True
    bad_resp = router.handle({"id": "7", "cmd": "unlock_it", "payload": {"pin": "0000"}})
    assert bad_resp["result"]["ok"] is False
    assert any(c == "unlockIT" and o == "ipc" for (c, o, _d, _s) in audit.entries)


def test_unknown_command() -> None:
    router = IpcRouter(_layer())
    resp = router.handle({"id": "8", "cmd": "nope"})
    assert resp["ok"] is False and "unknown command" in resp["error"]


def test_bad_payload_returns_error_not_crash() -> None:
    router = IpcRouter(_layer())
    resp = router.handle({"id": "9", "cmd": "toggle_monitor", "payload": {}})  # missing fingerprint
    assert resp["ok"] is False and resp["error"]


def test_commands_cover_all_facades() -> None:
    cmds = IpcRouter(_layer()).commands
    for expected in ("get_monitors", "set_role", "list_clips", "list_storages",
                     "export_timeline", "ensure_folder_and_link"):
        assert expected in cmds
