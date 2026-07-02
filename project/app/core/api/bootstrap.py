"""bootstrap — assemble the core/api layer from built services (ADR-0009).

``build_api_layer`` wires one :class:`EventBus` and the three facades over the
services that ``main.py`` already constructs, and returns them in an
:class:`ApiLayer`.  Both the QML adapter (M2) and the ``adapters/ipc`` channel
(M3) drive this exact object — one facade, interchangeable adapters.

The heavier "build the whole recording stack headless, by role" belongs to the
daemon entrypoint (M4); this module deliberately takes already-built services so
it introduces zero behaviour change to the running app when M2 adopts it.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from app.core.api.editor_api import EditorApi
from app.core.api.events import EventBus
from app.core.api.recording_api import RecordingApi
from app.core.api.settings_api import SettingsApi
from app.core.monitor_detection.service import MonitorDetectionService
from app.core.ports.audit_port import AuditPort
from app.core.ports.clip_inspector_port import ClipInspectorPort
from app.core.ports.editor_export_port import EditorExportPort
from app.core.ports.user_config_port import UserConfigPort


@dataclass
class ApiLayer:
    """The wired input port — everything an entry adapter needs, and nothing Qt."""

    bus: EventBus
    recording: RecordingApi
    settings: SettingsApi
    editor: EditorApi

    def start(self) -> None:
        self.bus.start()

    def stop(self) -> None:
        self.bus.stop()


def build_api_layer(
    *,
    detection_service: MonitorDetectionService,
    settings,
    user_config_port: UserConfigPort,
    audit_port: Optional[AuditPort] = None,
    recording_service=None,
    event_service=None,
    export_port: Optional[EditorExportPort] = None,
    inspector: Optional[ClipInspectorPort] = None,
    clips_dir: Optional[Path] = None,
    relaunch_cb: Optional[Callable[[], None]] = None,
    autorecord_cb: Optional[Callable[[bool], None]] = None,
    start_bus: bool = False,
) -> ApiLayer:
    """Assemble the EventBus + the three facades over the given services.

    ``recording_service`` / ``event_service`` are ``None`` on non-recording roles
    (supervisor / unconfigured) — the facades degrade gracefully.
    """
    bus = EventBus()

    recording = RecordingApi(
        event_bus=bus,
        detection_service=detection_service,
        recording_service=recording_service,
        event_service=event_service,
        user_config_port=user_config_port,
        audit_port=audit_port,
    )
    settings_api = SettingsApi(
        event_bus=bus,
        user_config_port=user_config_port,
        settings=settings,
        audit_port=audit_port,
        relaunch_cb=relaunch_cb,
        autorecord_cb=autorecord_cb,
    )
    editor = EditorApi(
        event_bus=bus,
        export_port=export_port,
        clips_dir=clips_dir,
        inspector=inspector,
    )

    layer = ApiLayer(bus=bus, recording=recording, settings=settings_api, editor=editor)
    if start_bus:
        layer.start()
    return layer
