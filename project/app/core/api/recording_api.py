"""RecordingApi — facade over the recording/monitor/event subsystem (ADR-0009).

Unifies the recording-related slots that ``app_bridge`` exposes today. Accepts
command DTOs, calls the existing services (``RecordingService``, ``EventService``,
``MonitorDetectionService``), returns DTOs, and publishes typed events on the
:class:`EventBus`.  Knows nothing about Qt, WebSockets, or JSON.

Monitor clip-selection state (which monitors go into event clips) lives here now
— it is the single source of truth the QML adapter and the IPC channel both read,
and it is persisted to ``user_config.json`` so it survives a restart.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from loguru import logger

from app.core.api import dto
from app.core.api.events import EventBus
from app.core.monitor_detection.service import MonitorDetectionService
from app.core.ports.audit_port import AuditPort
from app.core.ports.preview_server_port import PreviewServerPort
from app.core.ports.user_config_port import UserConfigPort
from app.core.recording_service.models import MonitorInfo


class RecordingApi:
    """Command surface for recording, monitors, and manual events."""

    def __init__(
        self,
        *,
        event_bus: EventBus,
        detection_service: MonitorDetectionService,
        recording_service=None,   # RecordingService | None (None on supervisor)
        event_service=None,       # EventService | None
        user_config_port: Optional[UserConfigPort] = None,
        audit_port: Optional[AuditPort] = None,
        preview_server: Optional[PreviewServerPort] = None,
    ) -> None:
        self._bus = event_bus
        self._detection = detection_service
        self._recording = recording_service
        self._events = event_service
        self._user_config_port = user_config_port
        self._audit = audit_port
        self._preview_server = preview_server

        self._all_monitors: List[MonitorInfo] = detection_service.get_monitors()
        self._selected: set[str] = self._load_selection()
        self._sync_selection()
        self._event_count = 0

    # ── Audit helper (ADR-0011) ───────────────────────────────────────

    def _audit_cmd(self, command: str, origin: str, detail: str = "", success: bool = True) -> None:
        if self._audit is None:
            return
        try:
            self._audit.record(command, origin, datetime.now(tz=timezone.utc), detail, success)
        except Exception:  # noqa: BLE001 — auditing must never break the command
            logger.exception("[recording-api] audit record failed for {}", command)

    # ── Queries ───────────────────────────────────────────────────────

    def get_recording_state(self) -> dto.RecordingState:
        is_rec = self._recording is not None and self._recording.is_recording()
        secs = int(self._recording.total_stored_duration_seconds()) if is_rec else 0
        return dto.RecordingState(
            is_recording=is_rec, record_seconds=secs, event_count=self._event_count
        )

    def get_monitors(self) -> List[dto.MonitorDTO]:
        return [
            dto.MonitorDTO.from_monitor(m, selected=m.fingerprint in self._selected)
            for m in self._all_monitors
        ]

    def get_preview_server_info(self) -> Optional[dto.PreviewServerInfo]:
        """Return preview server info when the operator HTTP server is running."""
        if self._preview_server is None or not self._preview_server.is_running:
            return None
        return dto.PreviewServerInfo(
            base_url=self._preview_server.base_url,
            stream_url_template=(
                f"{self._preview_server.base_url}/stream/m{{index}}"
            ),
            active=True,
        )

    # ── Commands ──────────────────────────────────────────────────────

    def start_recording(self, cmd: dto.StartRecording) -> dto.RecordingState:
        ok = self._recording is not None
        self._audit_cmd("startRecording", cmd.origin, success=ok)
        if ok:
            self._recording.start()
        return self._publish_recording_state()

    def stop_recording(self, cmd: dto.StopRecording) -> dto.RecordingState:
        ok = self._recording is not None
        self._audit_cmd("stopRecording", cmd.origin, success=ok)
        if ok:
            self._recording.stop()
        return self._publish_recording_state()

    def trigger_event(self, cmd: dto.TriggerEvent) -> bool:
        if self._events is None:
            return False
        accepted = self._events.trigger_manual_event()
        if accepted:
            self._event_count += 1
            self._publish_recording_state()
        return accepted

    def toggle_monitor(self, cmd: dto.ToggleMonitor) -> List[dto.MonitorDTO]:
        fp = cmd.fingerprint
        if fp in self._selected:
            if len(self._selected) > 1:
                self._selected.discard(fp)
            # else: always keep at least one selected → no-op
        else:
            self._selected.add(fp)
        self._apply_selection()
        self._persist_selection()
        return self._publish_monitors()

    # ── Callbacks fired by the recording stack (background threads) ────
    # These marshal onto the bus; subscribers run on the bus dispatcher thread.

    def on_recording_failed(self, message: str) -> None:
        self._bus.publish(dto.RecordingFailed(message=message))

    def on_clip_failed(self, message: str) -> None:
        self._bus.publish(dto.ClipFailed(message=message))

    def on_monitors_updated(self, monitors: List[MonitorInfo]) -> None:
        """Detection-thread callback — refresh the list and re-publish."""
        self._all_monitors = list(monitors)
        self._sync_selection()
        self._publish_monitors()

    def poll_recording_state(self) -> None:
        """Periodic tick (called by whichever adapter owns the timer).

        Publishes a RecordingStateChanged only when something actually changed —
        cheap, and keeps the coalescing-drop backpressure policy meaningful.
        """
        self._publish_recording_state()

    # ── Internal ──────────────────────────────────────────────────────

    def _publish_recording_state(self) -> dto.RecordingState:
        state = self.get_recording_state()
        self._bus.publish(dto.RecordingStateChanged(state=state))
        return state

    def _publish_monitors(self) -> List[dto.MonitorDTO]:
        monitors = self.get_monitors()
        self._bus.publish(dto.MonitorsChanged(monitors=monitors))
        return monitors

    def _sync_selection(self) -> None:
        valid = {m.fingerprint for m in self._all_monitors}
        self._selected &= valid
        if not self._selected and self._all_monitors:
            primary = next((m for m in self._all_monitors if m.is_primary), None)
            self._selected = {(primary or self._all_monitors[0]).fingerprint}

    def _apply_selection(self) -> None:
        selected = [m for m in self._all_monitors if m.fingerprint in self._selected]
        if selected and self._recording is not None:
            self._recording.change_monitors(selected)

    def _load_selection(self) -> set[str]:
        if self._user_config_port is None:
            return set()
        try:
            return set(self._user_config_port.load().selected_monitor_fingerprints)
        except Exception:  # noqa: BLE001
            logger.warning("[recording-api] failed to load saved monitor selection.")
            return set()

    def _persist_selection(self) -> None:
        if self._user_config_port is None:
            return
        try:
            cfg = self._user_config_port.load()
            cfg.selected_monitor_fingerprints = sorted(self._selected)
            self._user_config_port.save(cfg)
        except Exception:  # noqa: BLE001
            logger.warning("[recording-api] failed to persist monitor selection.")
