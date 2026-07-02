"""SettingsApi facade — role authorization, audit (ADR-0011), and persistence."""
from __future__ import annotations

from app.core.api import dto
from app.core.api.events import EventBus
from app.core.api.settings_api import SettingsApi
from app.core.role import IT, OPERATOR, SUPERVISOR


class Cfg:
    def __init__(self, role=""):
        self.role = role
        self.autorecord = False
        self.clips_dir = ""
        self.driver = "auto"
        self.codec = "hevc"


class FakeUserConfigPort:
    def __init__(self, role=""):
        self._cfg = Cfg(role)

    def load(self):
        # Return the same object so mutate+save round-trips in this fake.
        return self._cfg

    def save(self, cfg):
        self._cfg = cfg


class FakeSettings:
    it_pin = "1379"


class FakeAudit:
    def __init__(self):
        self.entries = []

    def record(self, command, origin, timestamp, detail="", success=True):
        self.entries.append((command, origin, detail, success))


def _make(role="", audit=None, relaunch=None):
    bus = EventBus()
    ucp = FakeUserConfigPort(role)
    api = SettingsApi(
        event_bus=bus,
        user_config_port=ucp,
        settings=FakeSettings(),
        audit_port=audit,
        relaunch_cb=relaunch,
    )
    return bus, ucp, api


def test_first_run_can_set_role_and_relaunches() -> None:
    audit = FakeAudit()
    calls = []
    bus, ucp, api = _make(role="", audit=audit, relaunch=lambda: calls.append(True))
    role_events: list[object] = []
    bus.subscribe(dto.RoleChanged, role_events.append)

    assert api.set_role(dto.SetRole(role=OPERATOR, origin="ui")) is True
    assert ucp.load().role == OPERATOR
    assert calls == [True]  # relaunch requested
    bus.drain()
    assert role_events and role_events[0].role == OPERATOR
    assert ("setRole", "ui", "→operator", True) == audit.entries[-1]


def test_supervisor_cannot_change_role_without_unlock() -> None:
    audit = FakeAudit()
    bus, ucp, api = _make(role=SUPERVISOR, audit=audit)
    assert api.set_role(dto.SetRole(role=IT)) is False
    assert ucp.load().role == SUPERVISOR  # unchanged
    assert audit.entries[-1][3] is False  # audited as unauthorised


def test_unlock_it_then_change_role() -> None:
    audit = FakeAudit()
    bus, ucp, api = _make(role=SUPERVISOR, audit=audit, relaunch=lambda: None)
    assert api.unlock_it(dto.UnlockIT(pin="wrong")) is False
    assert api.is_it_unlocked is False
    assert api.unlock_it(dto.UnlockIT(pin="1379")) is True
    assert api.is_it_unlocked is True
    assert api.set_role(dto.SetRole(role=IT)) is True
    assert ucp.load().role == IT
    # unlockIT audited both the failure and the success.
    unlock_rows = [e for e in audit.entries if e[0] == "unlockIT"]
    assert (False in [r[3] for r in unlock_rows]) and (True in [r[3] for r in unlock_rows])


def test_invalid_role_rejected_and_audited() -> None:
    audit = FakeAudit()
    bus, ucp, api = _make(role=IT, audit=audit, relaunch=lambda: None)
    assert api.set_role(dto.SetRole(role="hacker")) is False
    assert audit.entries[-1] == ("setRole", "ui", "invalid:hacker", False)


def test_set_autorecord_persists_and_invokes_callback() -> None:
    toggles = []
    bus = EventBus()
    ucp = FakeUserConfigPort(role=IT)
    api = SettingsApi(
        event_bus=bus,
        user_config_port=ucp,
        settings=FakeSettings(),
        autorecord_cb=toggles.append,
    )
    api.set_autorecord(dto.SetAutorecord(enabled=True))
    assert ucp.load().autorecord is True
    assert toggles == [True]


def test_set_codec_ignores_invalid() -> None:
    bus, ucp, api = _make(role=IT)
    api.set_codec(dto.SetCodec(codec="av1"))  # unsupported → no change
    assert ucp.load().codec == "hevc"
    api.set_codec(dto.SetCodec(codec="H264"))
    assert ucp.load().codec == "h264"
