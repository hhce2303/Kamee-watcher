"""bootstrap.build_api_layer — one bus + three facades, degrades on supervisor."""
from __future__ import annotations

from app.adapters.cloud.local_share_adapter import LocalShareAdapter
from app.core.api import dto
from app.core.api.bootstrap import build_api_layer
from app.core.api.editor_api import EditorApi
from app.core.api.recording_api import RecordingApi
from app.core.api.settings_api import SettingsApi
from app.core.cloud_share_service import CloudShareService
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


class FakeExportPort:
    def __init__(self):
        self.exported_to = None

    def export(self, timeline, output_path, on_progress=None):
        self.exported_to = output_path


def test_delivery_save_reel_privately_reaches_editor_export(tmp_path) -> None:
    """Wiring test: DeliveryApi.save_reel_privately must reach all the way
    through to EditorApi's real export — no direct facade-to-facade import,
    only the export_fn/is_exporting closures bootstrap.py wires between them."""
    export_port = FakeExportPort()
    layer = build_api_layer(
        detection_service=FakeDetection(),
        settings=FakeSettings(),
        user_config_port=FakeUserConfigPort(),
        export_port=export_port,
        cloud_share_service=CloudShareService(LocalShareAdapter(root=tmp_path / "od")),
    )
    layer.editor._run_export_async = layer.editor._do_export  # run inline, deterministic

    layer.editor.add_clip(dto.AddClip(path="/a.mp4", duration_s=10.0))
    layer.delivery.save_reel_privately("SLC/clips-supervisor/2026-07")
    layer.bus.drain()

    assert export_port.exported_to is not None
    assert export_port.exported_to.name.startswith("reel_")
    assert export_port.exported_to.name.endswith(".mp4")
    assert (tmp_path / "od" / "SLC" / "clips-supervisor" / "2026-07").is_dir()
