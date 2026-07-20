"""DTO contract tests — round-trip serialization + conversion from core models.

``adapters/ipc`` will serialize these with Pydantic's JSON, so every DTO must
round-trip losslessly, and events must carry their ``event`` discriminator.
"""
from __future__ import annotations

from app.core.api import dto
from app.core.recording_service.models import MonitorInfo


def test_monitor_dto_from_core_model() -> None:
    m = MonitorInfo(name="\\\\.\\DISPLAY1", width=1920, height=1080, x=0, y=0, is_primary=True, index=0)
    d = dto.MonitorDTO.from_monitor(m, selected=True)
    assert d.resolution == "1920×1080"
    assert d.fingerprint == m.fingerprint
    assert d.is_primary is True
    assert d.selected is True
    # Round-trip through JSON (what the IPC layer will do).
    again = dto.MonitorDTO.model_validate_json(d.model_dump_json())
    assert again == d


def test_recording_state_defaults() -> None:
    s = dto.RecordingState()
    assert s.is_recording is False
    assert s.record_seconds == 0
    assert s.event_count == 0


def test_command_round_trip() -> None:
    cmd = dto.ToggleMonitor(fingerprint="abc_1920x1080_0_0")
    again = dto.ToggleMonitor.model_validate_json(cmd.model_dump_json())
    assert again == cmd


def test_audited_commands_default_origin() -> None:
    # Sensitive commands carry an origin for the audit row (ADR-0011).
    assert dto.StartRecording().origin == "ui"
    assert dto.StopRecording(origin="ipc:pid=42").origin == "ipc:pid=42"
    assert dto.SetRole(role="it").origin == "ui"
    assert dto.UnlockIT(pin="0000").origin == "ui"


def test_event_discriminator_present() -> None:
    ev = dto.RecordingStateChanged(state=dto.RecordingState(is_recording=True, record_seconds=5))
    payload = ev.model_dump_json()
    assert '"event":"recording_state_changed"' in payload
    again = dto.RecordingStateChanged.model_validate_json(payload)
    assert again.state.is_recording is True
    assert again.state.record_seconds == 5


def test_all_events_have_unique_discriminators() -> None:
    event_classes = [
        obj
        for obj in vars(dto).values()
        if isinstance(obj, type)
        and issubclass(obj, dto.BaseEvent)
        and obj is not dto.BaseEvent
    ]
    discriminators = []
    for cls in event_classes:
        # The literal default is on the field.
        default = cls.model_fields["event"].default
        assert isinstance(default, str) and default, f"{cls.__name__} missing discriminator"
        discriminators.append(default)
    assert len(discriminators) == len(set(discriminators)), "duplicate event discriminators"


def test_export_progress_carries_fraction() -> None:
    ev = dto.ExportProgress(fraction=0.42)
    again = dto.ExportProgress.model_validate_json(ev.model_dump_json())
    assert abs(again.fraction - 0.42) < 1e-9
