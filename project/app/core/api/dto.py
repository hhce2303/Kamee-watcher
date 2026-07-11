"""DTOs — the single source of the core/api contract (ADR-0009).

Pydantic v2 models grouped into three families:

* **Commands** — what a caller asks the facade to do (mirror the ~30 bridge slots).
* **State / responses** — what the facade returns (converted from core dataclasses,
  never re-implementing the domain).
* **Events** — what the facade pushes onto the :class:`~app.core.api.events.EventBus`;
  each maps 1:1 to a current Qt Signal so the QML adapter re-emits without loss.

These models carry **no Qt / WS / JSON knowledge** — serialization is the job of
``adapters/ipc``.  Events subclass :class:`BaseEvent`; the ``event`` discriminator
lets the IPC layer tag each frame and lets subscribers filter by class.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict

from app.core.recording_service.models import MonitorInfo

# ══════════════════════════════════════════════════════════════════════
# State / response DTOs
# ══════════════════════════════════════════════════════════════════════


class MonitorDTO(BaseModel):
    """A monitor as the UI sees it — mirrors AppBridge.monitors item shape."""

    model_config = ConfigDict(frozen=True)

    name: str
    device_name: str
    resolution: str
    fingerprint: str
    index: int
    x: int
    y: int
    is_primary: bool
    selected: bool

    @classmethod
    def from_monitor(cls, m: MonitorInfo, *, selected: bool) -> "MonitorDTO":
        return cls(
            name=m.display_name,
            device_name=m.name,
            resolution=f"{m.width}×{m.height}",
            fingerprint=m.fingerprint,
            index=m.index,
            x=m.x,
            y=m.y,
            is_primary=m.is_primary,
            selected=selected,
        )


class RecordingState(BaseModel):
    """Snapshot of the recording subsystem — replaces polled bridge properties."""

    model_config = ConfigDict(frozen=True)

    is_recording: bool = False
    record_seconds: int = 0
    event_count: int = 0


class ClipInfoDTO(BaseModel):
    """Media metadata for the currently loaded clip (from PlayerService)."""

    model_config = ConfigDict(frozen=True)

    resolution: str = ""
    codec: str = ""
    fps: str = ""
    bitrate: str = ""
    duration_seconds: float = 0.0


class ClipDTO(BaseModel):
    """A clip file listed in the clips browser."""

    model_config = ConfigDict(frozen=True)

    clip_name: str
    path: str
    size_label: str
    date_label: str
    is_event: bool


class ShareResultDTO(BaseModel):
    """Outcome of the OneDrive folder+link flow."""

    model_config = ConfigDict(frozen=True)

    folder_path: str
    share_link: str


class SettingsSnapshot(BaseModel):
    """Full settings/role state for the UI shell — replaces polled bridge getters."""

    model_config = ConfigDict(frozen=True)

    role: str
    clips_dir: str
    codec: str
    driver: str
    autorecord: bool
    autostart: bool
    it_unlocked: bool


class ClipEntryDTO(BaseModel):
    """One trimmed clip on the evidence reel — mirrors core/editor/models.ClipEntry."""

    model_config = ConfigDict(frozen=True)

    source_path: str
    source_duration_s: float
    in_point_s: float
    out_point_s: float


class MediaRoots(BaseModel):
    """Filesystem roots the UI's custom media protocol is allowed to serve from."""

    model_config = ConfigDict(frozen=True)

    segments_dir: str
    clips_dir: str
    storage_roots: list[str] = []


class PreviewServerInfo(BaseModel):
    """Info about the operator-only localhost MJPEG preview server."""

    model_config = ConfigDict(frozen=True)

    base_url: str
    stream_url_template: str  # e.g. "http://127.0.0.1:8787/stream/m{index}"
    active: bool


# ══════════════════════════════════════════════════════════════════════
# Command DTOs  (UI → facade).  Grouped by which bridge they came from.
# ══════════════════════════════════════════════════════════════════════

# Commands that mutate recording/role state are audited (ADR-0011); they carry an
# ``origin`` so the audit row records who issued them.


class _Command(BaseModel):
    model_config = ConfigDict(frozen=True)


# ── Recording / events (from app_bridge) ──────────────────────────────
class TriggerEvent(_Command):
    origin: str = "ui"


class StartRecording(_Command):
    origin: str = "ui"


class StopRecording(_Command):
    origin: str = "ui"


class ToggleMonitor(_Command):
    fingerprint: str


class LoadClip(_Command):
    path: str


class ListDirectory(_Command):
    path: str


class TranscodeClip(_Command):
    path: str


# ── Request system (from app_bridge) ──────────────────────────────────
class ListStorages(_Command):
    pass


class ListOperators(_Command):
    storage_path: str


class ListAllOperators(_Command):
    pass


class SendClipRequest(_Command):
    request_json: str


class UpdateRequestStatus(_Command):
    request_id: str
    status: str


class EnsureFolderLink(_Command):
    folder_path: str = ""


# ── Settings (from settings_bridge) ───────────────────────────────────
class SetClipsDir(_Command):
    path: str


class SetDriverIndex(_Command):
    index: int


class SetCodec(_Command):
    codec: str


class SetAutostart(_Command):
    enabled: bool


class SetAutorecord(_Command):
    enabled: bool


class SetRole(_Command):
    role: str
    origin: str = "ui"


class UnlockIT(_Command):
    pin: str
    origin: str = "ui"


class OpenItWsPort(_Command):
    pass


# ── Editor (from editor_bridge) ───────────────────────────────────────
class AddClip(_Command):
    path: str
    duration_s: float


class AddClipTrimmed(_Command):
    path: str
    duration_s: float
    in_frac: float
    out_frac: float


class AddFilesFromUrls(_Command):
    urls: list[str]


class ExportTimeline(_Command):
    output_path: str


# ══════════════════════════════════════════════════════════════════════
# Event DTOs  (facade → subscribers).  One per current Qt Signal.
# ══════════════════════════════════════════════════════════════════════


class BaseEvent(BaseModel):
    """Base for every bus event. ``event`` is the wire discriminator."""

    model_config = ConfigDict(frozen=True)
    event: str


class RecordingStateChanged(BaseEvent):
    event: Literal["recording_state_changed"] = "recording_state_changed"
    state: RecordingState


class MonitorsChanged(BaseEvent):
    event: Literal["monitors_changed"] = "monitors_changed"
    monitors: list[MonitorDTO]


class ClipsChanged(BaseEvent):
    event: Literal["clips_changed"] = "clips_changed"
    clips: list[ClipDTO]


class RecordingFailed(BaseEvent):
    event: Literal["recording_failed"] = "recording_failed"
    message: str


class ClipFailed(BaseEvent):
    event: Literal["clip_failed"] = "clip_failed"
    message: str


class RecordingDegraded(BaseEvent):
    event: Literal["recording_degraded"] = "recording_degraded"
    message: str


class RecordingRecovered(BaseEvent):
    event: Literal["recording_recovered"] = "recording_recovered"


class LogMessage(BaseEvent):
    event: Literal["log_message"] = "log_message"
    message: str


class RequestShowWindow(BaseEvent):
    event: Literal["request_show_window"] = "request_show_window"


class TimelineChanged(BaseEvent):
    event: Literal["timeline_changed"] = "timeline_changed"


class ExportStarted(BaseEvent):
    event: Literal["export_started"] = "export_started"


class ExportProgress(BaseEvent):
    event: Literal["export_progress"] = "export_progress"
    fraction: float


class ExportFinished(BaseEvent):
    event: Literal["export_finished"] = "export_finished"
    output_path: str


class ExportFailed(BaseEvent):
    event: Literal["export_failed"] = "export_failed"
    message: str


class OneDriveChanged(BaseEvent):
    event: Literal["onedrive_changed"] = "onedrive_changed"
    state: str  # idle | working | linked | error
    folder: str = ""
    link: str = ""


class OneDriveFailed(BaseEvent):
    event: Literal["onedrive_failed"] = "onedrive_failed"
    message: str


class RequestReceived(BaseEvent):
    event: Literal["request_received"] = "request_received"


class RequestStatusChanged(BaseEvent):
    event: Literal["request_status_changed"] = "request_status_changed"
    request_id: str
    status: str


class RoleChanged(BaseEvent):
    event: Literal["role_changed"] = "role_changed"
    role: str
    it_unlocked: bool = False


class TranscodeStarted(BaseEvent):
    """HEVC→H.264 on-demand transcode for playback (TD-1: WebView2 has no SW HEVC)."""

    event: Literal["transcode_started"] = "transcode_started"
    path: str


class TranscodeProgress(BaseEvent):
    event: Literal["transcode_progress"] = "transcode_progress"
    path: str
    fraction: float


class TranscodeFinished(BaseEvent):
    event: Literal["transcode_finished"] = "transcode_finished"
    path: str
    output_path: str


class TranscodeFailed(BaseEvent):
    event: Literal["transcode_failed"] = "transcode_failed"
    path: str
    message: str


class EncoderRestartStarted(BaseEvent):
    event: Literal["encoder_restart_started"] = "encoder_restart_started"


class EncoderRestartFinished(BaseEvent):
    event: Literal["encoder_restart_finished"] = "encoder_restart_finished"


class EncoderRestartFailed(BaseEvent):
    event: Literal["encoder_restart_failed"] = "encoder_restart_failed"
    message: str
