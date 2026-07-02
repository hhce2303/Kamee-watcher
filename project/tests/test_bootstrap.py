"""bootstrap.build_api_layer — one bus + three facades, degrades on supervisor."""
from __future__ import annotations

from app.core.api.bootstrap import build_api_layer
from app.core.api.editor_api import EditorApi
from app.core.api.recording_api import RecordingApi
from app.core.api.settings_api import SettingsApi
from app.core.recording_service.models import MonitorInfo


class FakeDetection:
    def get_monitors(self):
        return [MonitorInfo(name="\\\\.\\DISPLAY1", width=1920, height=1080, x=0, y=0, is_primary=True, index=0)]


class Cfg:
    role = ""
    selected_monitor_fingerprints: list = []


class FakeUserConfigPort:
    def load(self):
        return Cfg()

    def save(self, cfg):
        pass


class FakeSettings:
    it_pin = "0000"


def test_build_api_layer_wires_all_three_facades() -> None:
    layer = build_api_layer(
        detection_service=FakeDetection(),
        settings=FakeSettings(),
        user_config_port=FakeUserConfigPort(),
    )
    assert isinstance(layer.recording, RecordingApi)
    assert isinstance(layer.settings, SettingsApi)
    assert isinstance(layer.editor, EditorApi)
    # All three share the one bus.
    assert layer.recording._bus is layer.bus
    assert layer.settings._bus is layer.bus
    assert layer.editor._bus is layer.bus


def test_supervisor_layer_has_no_recording_stack() -> None:
    layer = build_api_layer(
        detection_service=FakeDetection(),
        settings=FakeSettings(),
        user_config_port=FakeUserConfigPort(),
        recording_service=None,
        event_service=None,
    )
    assert layer.recording.get_recording_state().is_recording is False


def test_start_stop_bus_lifecycle() -> None:
    layer = build_api_layer(
        detection_service=FakeDetection(),
        settings=FakeSettings(),
        user_config_port=FakeUserConfigPort(),
        start_bus=True,
    )
    assert layer.bus._running is True
    layer.stop()
    assert layer.bus._running is False
