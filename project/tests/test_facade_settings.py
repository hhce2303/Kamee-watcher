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
    clips_dir = r"C:\WatcherData\clips"
    segment_dir = r"C:\WatcherData\segments"
    video_codec = "hevc"
    slc_storage_host = r"\\SIG-SLC-Storage"


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


def test_get_settings_snapshot(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.core.api.settings_api.autostart.is_autostart_enabled", lambda: True
    )
    bus, ucp, api = _make(role=IT)
    snap = api.get_settings()
    assert snap.role == IT
    assert snap.codec == "hevc"
    assert snap.driver == "auto"
    assert snap.autorecord is False
    assert snap.autostart is True
    assert snap.it_unlocked is False


def test_get_settings_falls_back_to_config_defaults(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.core.api.settings_api.autostart.is_autostart_enabled", lambda: False
    )
    bus, ucp, api = _make(role="")
    ucp.load().clips_dir = ""  # unset → falls back to Settings.clips_dir
    ucp.load().codec = None    # unset → falls back to Settings.video_codec
    snap = api.get_settings()
    assert snap.clips_dir == FakeSettings.clips_dir
    assert snap.codec == FakeSettings.video_codec


def test_get_media_roots() -> None:
    bus, ucp, api = _make(role=IT)
    roots = api.get_media_roots()
    assert roots.segments_dir == FakeSettings.segment_dir
    assert roots.clips_dir == FakeSettings.clips_dir
    assert roots.storage_roots == [FakeSettings.slc_storage_host]


def test_set_autostart_delegates_to_infrastructure(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        "app.core.api.settings_api.autostart.set_autostart", calls.append
    )
    bus, ucp, api = _make(role=IT)
    api.set_autostart(dto.SetAutostart(enabled=True))
    assert calls == [True]


def test_apply_encoder_now_no_callback_publishes_failed() -> None:
    bus, ucp, api = _make(role=IT)
    events = []
    bus.subscribe(dto.EncoderRestartFailed, events.append)
    api.apply_encoder_now()
    bus.drain()
    assert len(events) == 1


def test_apply_encoder_now_runs_callback_and_publishes_lifecycle() -> None:
    bus, ucp, api = _make(role=IT)
    ucp.load().codec = "h264"
    ucp.load().driver = "nvidia"
    calls = []
    api.set_restart_encoder_cb(lambda codec, driver: calls.append((codec, driver)))
    # Run the "background thread" inline for deterministic assertions.
    api._run_restart_async = api._do_restart_encoder  # noqa: SLF001

    events = []
    bus.subscribe(dto.EncoderRestartStarted, events.append)
    bus.subscribe(dto.EncoderRestartFinished, events.append)
    api.apply_encoder_now()
    bus.drain()

    assert calls == [("h264", "nvidia")]
    assert [type(e).__name__ for e in events] == ["EncoderRestartStarted", "EncoderRestartFinished"]


def test_apply_encoder_now_callback_error_publishes_failed() -> None:
    bus, ucp, api = _make(role=IT)

    def _boom(codec, driver):
        raise RuntimeError("driver busy")

    api.set_restart_encoder_cb(_boom)
    api._run_restart_async = api._do_restart_encoder  # noqa: SLF001

    failed = []
    bus.subscribe(dto.EncoderRestartFailed, failed.append)
    api.apply_encoder_now()
    bus.drain()

    assert len(failed) == 1 and "driver busy" in failed[0].message
