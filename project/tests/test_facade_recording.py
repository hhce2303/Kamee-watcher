"""RecordingApi facade — command→service delegation, events, and audit (ADR-0011)."""
from __future__ import annotations

from app.core.api import dto
from app.core.api.events import EventBus
from app.core.api.recording_api import RecordingApi
from app.core.recording_service.models import MonitorInfo


class FakeDetection:
    def __init__(self, monitors):
        self._monitors = monitors

    def get_monitors(self):
        return list(self._monitors)


class FakeRecording:
    def __init__(self):
        self.started = False
        self.selection = None

    def is_recording(self):
        return self.started

    def start(self):
        self.started = True

    def stop(self):
        self.started = False

    def total_stored_duration_seconds(self):
        return 12.0

    def change_monitors(self, monitors):
        self.selection = monitors


class FakeEventService:
    def __init__(self, accept=True):
        self._accept = accept
        self.calls = 0

    def trigger_manual_event(self):
        self.calls += 1
        return self._accept


class FakeAudit:
    def __init__(self):
        self.entries = []

    def record(self, command, origin, timestamp, detail="", success=True):
        self.entries.append((command, origin, detail, success))


class FakeUserConfigPort:
    def __init__(self):
        self._cfg = type("Cfg", (), {"selected_monitor_fingerprints": []})()

    def load(self):
        return self._cfg

    def save(self, cfg):
        self._cfg = cfg


def _monitors():
    return [
        MonitorInfo(name="\\\\.\\DISPLAY1", width=1920, height=1080, x=0, y=0, is_primary=True, index=0),
        MonitorInfo(name="\\\\.\\DISPLAY2", width=1280, height=1024, x=1920, y=0, index=1),
    ]


def _make_api(**kw):
    bus = EventBus()
    api = RecordingApi(
        event_bus=bus,
        detection_service=FakeDetection(_monitors()),
        recording_service=kw.get("recording", FakeRecording()),
        event_service=kw.get("events", FakeEventService()),
        user_config_port=kw.get("ucp", FakeUserConfigPort()),
        audit_port=kw.get("audit"),
    )
    return bus, api


def test_get_recording_state_reflects_service() -> None:
    rec = FakeRecording()
    _bus, api = _make_api(recording=rec)
    assert api.get_recording_state().is_recording is False
    rec.start()
    st = api.get_recording_state()
    assert st.is_recording is True
    assert st.record_seconds == 12


def test_start_stop_audited_and_publish_event() -> None:
    audit = FakeAudit()
    rec = FakeRecording()
    bus, api = _make_api(recording=rec, audit=audit)
    seen: list[object] = []
    bus.subscribe(dto.RecordingStateChanged, seen.append)

    api.start_recording(dto.StartRecording(origin="ipc:pid=7"))
    assert rec.started is True
    api.stop_recording(dto.StopRecording())
    assert rec.started is False
    bus.drain()

    assert len(seen) == 2
    commands = [(c, o) for (c, o, _d, _s) in audit.entries]
    assert ("startRecording", "ipc:pid=7") in commands
    assert ("stopRecording", "ui") in commands


def test_toggle_monitor_keeps_at_least_one_and_persists() -> None:
    ucp = FakeUserConfigPort()
    rec = FakeRecording()
    bus, api = _make_api(recording=rec, ucp=ucp)
    seen: list[object] = []
    bus.subscribe(dto.MonitorsChanged, seen.append)

    mons = _monitors()
    fp0, fp1 = mons[0].fingerprint, mons[1].fingerprint

    # Initially only the primary is selected; toggling it off is a no-op (keep ≥1).
    api.toggle_monitor(dto.ToggleMonitor(fingerprint=fp0))
    selected = [m for m in api.get_monitors() if m.selected]
    assert len(selected) >= 1

    # Add the second monitor → both selected, persisted, recording updated.
    api.toggle_monitor(dto.ToggleMonitor(fingerprint=fp1))
    selected_fps = {m.fingerprint for m in api.get_monitors() if m.selected}
    assert fp1 in selected_fps
    assert set(ucp.load().selected_monitor_fingerprints) == selected_fps
    assert rec.selection is not None
    bus.drain()
    assert len(seen) >= 1


def test_trigger_event_increments_count_when_accepted() -> None:
    ev = FakeEventService(accept=True)
    _bus, api = _make_api(events=ev)
    assert api.trigger_event(dto.TriggerEvent()) is True
    assert api.get_recording_state().event_count == 1

    ev2 = FakeEventService(accept=False)
    _bus2, api2 = _make_api(events=ev2)
    assert api2.trigger_event(dto.TriggerEvent()) is False
    assert api2.get_recording_state().event_count == 0


def test_supervisor_role_has_no_recording_stack() -> None:
    audit = FakeAudit()
    bus = EventBus()
    api = RecordingApi(
        event_bus=bus,
        detection_service=FakeDetection(_monitors()),
        recording_service=None,   # supervisor
        event_service=None,
        audit_port=audit,
    )
    # start/stop are audited as failures (nothing to act on), never crash.
    api.start_recording(dto.StartRecording())
    assert api.get_recording_state().is_recording is False
    assert api.trigger_event(dto.TriggerEvent()) is False
    assert audit.entries[0][3] is False  # success == False


def test_recording_and_clip_failure_callbacks_publish() -> None:
    bus, api = _make_api()
    fails: list[object] = []
    bus.subscribe(dto.RecordingFailed, fails.append)
    bus.subscribe(dto.ClipFailed, fails.append)
    api.on_recording_failed("recorder crashed")
    api.on_clip_failed("clip build failed")
    bus.drain()
    assert len(fails) == 2


def test_recording_degraded_summarizes_non_recording_workers() -> None:
    bus, api = _make_api()
    degraded: list[dto.RecordingDegraded] = []
    bus.subscribe(dto.RecordingDegraded, degraded.append)
    api.on_recording_degraded({"workers": {0: "RECOVERING", 1: "RECORDING"}})
    bus.drain()
    assert len(degraded) == 1
    assert "idx=0 RECOVERING" in degraded[0].message
    assert "idx=1" not in degraded[0].message


def test_recording_degraded_falls_back_to_generic_message_when_no_problems() -> None:
    bus, api = _make_api()
    degraded: list[dto.RecordingDegraded] = []
    bus.subscribe(dto.RecordingDegraded, degraded.append)
    api.on_recording_degraded({})
    api.on_recording_degraded({"workers": {0: "RECORDING"}})
    bus.drain()
    assert len(degraded) == 2
    assert degraded[0].message == "Recording degraded."
    assert degraded[1].message == "Recording degraded."


def test_recording_recovered_publishes() -> None:
    bus, api = _make_api()
    recovered: list[dto.RecordingRecovered] = []
    bus.subscribe(dto.RecordingRecovered, recovered.append)
    api.on_recording_recovered()
    bus.drain()
    assert len(recovered) == 1
