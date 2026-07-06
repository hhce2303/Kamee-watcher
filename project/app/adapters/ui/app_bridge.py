"""AppBridge — Qt input adapter over the core/api facades (F1/ADR-0009).

Coexistence dual-path: every command slot delegates to a facade
(RecordingApi / ClipsApi / RequestsApi / DeliveryApi) — the single source of
logic — while the bridge keeps its Qt Signals/Properties so the QML surface is
unchanged.  The facades publish the same changes onto the EventBus for the future
``adapters/ipc`` consumer.  Only genuinely Qt-specific concerns stay here: the
preview-file poll timer, the QVideoSink registry, the screenshot image provider,
clipboard/URL helpers, and marshalling background results onto the Qt thread.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import List

from loguru import logger
from PySide6.QtCore import QObject, QTimer, Property, Signal, Slot

from app.core.api import dto
from app.core.api.clips_api import ClipsApi
from app.core.api.delivery_api import DeliveryApi
from app.core.api.events import EventBus
from app.core.api.recording_api import RecordingApi
from app.core.api.requests_api import RequestsApi
from app.core.monitor_detection.service import MonitorDetectionService
from app.core.recording_service.models import MonitorInfo
from app.core.ports.cloud_share_port import ShareResult
from app.core.ports.user_config_port import UserConfigPort
from app.adapters.ui.log_handler import emitter as log_emitter
from app.adapters.ui.screenshot_provider import MonitorScreenshotProvider


class AppBridge(QObject):
    """Single Python↔QML contract; delegates all logic to the core/api facades."""

    # ── Change notifications (QML-facing) ─────────────────────────────
    isRecordingChanged     = Signal()
    recordSecChanged       = Signal()
    monitorsChanged        = Signal()
    clipsChanged           = Signal()
    eventCountChanged      = Signal()
    currentClipPathChanged = Signal()
    currentClipInfoChanged = Signal()
    previewRevisionChanged = Signal()

    # ── One-way signals to QML ────────────────────────────────────────
    recordingFailed   = Signal(str)
    clipFailed        = Signal(str)
    logMessage        = Signal(str)
    requestShowWindow = Signal()

    # ── Request system ────────────────────────────────────────────────
    requestReceived      = Signal()
    requestStatusChanged = Signal(str, str)   # (id, status)
    requestSystemChanged = Signal()

    # ── OneDrive delivery ─────────────────────────────────────────────
    oneDriveChanged = Signal()
    oneDriveFailed  = Signal(str)

    # ── Private thread-bridge signals ─────────────────────────────────
    _monitors_from_service = Signal(object)   # List[MonitorInfo] — detection thread → main
    _share_done            = Signal(object)   # ShareResult | Exception — share thread → main

    def __init__(
        self,
        recording_service:  object = None,
        event_service:      object = None,
        detection_service:  MonitorDetectionService | None = None,
        player_service:     object = None,
        clips_dir:          Path | None = None,
        user_config_port:   UserConfigPort | None = None,
        cloud_share_service: object = None,
        parent: QObject | None = None,
        *,
        recording_api: RecordingApi | None = None,
        clips_api: ClipsApi | None = None,
        requests_api: RequestsApi | None = None,
        delivery_api: DeliveryApi | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        super().__init__(parent)

        self._detection_service = detection_service
        self._clips_dir = Path(clips_dir) if clips_dir else Path(".")

        # main.py injects the shared facades; standalone (tests) builds them over
        # a private bus from the passed-in services (coexistence dual-path).
        self._bus = event_bus or EventBus()
        self._recording = recording_api or RecordingApi(
            event_bus=self._bus,
            detection_service=detection_service,
            recording_service=recording_service,
            event_service=event_service,
            user_config_port=user_config_port,
        )
        self._clips = clips_api or ClipsApi(
            event_bus=self._bus,
            clips_dir=self._clips_dir,
            player_service=player_service,
            file_browser=self._default_file_browser(),
        )
        self._requests = requests_api or RequestsApi(event_bus=self._bus)
        self._delivery = delivery_api or DeliveryApi(
            event_bus=self._bus,
            cloud_share_service=cloud_share_service,
            onedrive_base_folder=self._onedrive_base(),
        )

        # ── Qt-facing cached state ────────────────────────────────────
        # Initialize from actual recording state so QML sees the correct value
        # on first read.  Without this, _is_recording starts False and
        # isRecordingChanged fires ~1 s after startup when the poll timer first
        # sees the already-running recorder — causing a False→True transition
        # that triggers cursor-flash side-effects (recLockOverlay, VU timer).
        _initial = self._recording.get_recording_state()
        self._is_recording = _initial.is_recording
        self._record_sec = _initial.record_seconds
        self._event_count = 0
        self._current_clip_path = ""
        self._current_clip_info: dict = {}
        self._preview_revision = 0
        self._clips_list: list[dict] = []
        self._last_list_failed = False

        # OneDrive Qt state
        self._one_drive_state = "idle"
        self._one_drive_folder = ""
        self._one_drive_link = ""

        # Preview polling (Qt, file-based — the recorder writes JPEGs at 2fps)
        self._video_sinks: dict[int, object] = {}
        self._preview_paths: dict[int, Path] = {}
        self._preview_mtimes: dict[int, float] = {}
        # Monotonic timestamp used to enforce a startup grace period before the
        # first preview read.  FFmpeg's gdigrab -update 1 writes JPEGs
        # non-atomically; reading too early yields a partially-written file
        # that QImage decodes as a corrupt frame, causing VideoOutput artifacts
        # that look like cursor flickering.  1 s gives FFmpeg time to produce
        # at least one complete preview frame.
        self._preview_ready_at: float = 0.0  # set in set_preview_paths()

        # Deduplicate monitor updates — only emit monitorsChanged when the set
        # of device names actually changes, preventing a Repeater rebuild every
        # 5 s from the detection service poll even when nothing changed.
        self._last_monitor_key: frozenset[str] = frozenset()

        self.screenshot_provider = MonitorScreenshotProvider()

        # Thread bridges (detection thread / share thread → Qt main thread)
        self._monitors_from_service.connect(self._apply_monitors_from_service)
        self._share_done.connect(self._apply_share_result)

        # Forward loguru → QML
        log_emitter.log_record.connect(self.logMessage)

        # Initial clip list
        self.refreshClips()

        # Timers
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(1000)
        self._poll_timer.timeout.connect(self._poll)
        self._poll_timer.start()

        self._preview_poll_timer = QTimer(self)
        self._preview_poll_timer.setInterval(500)
        self._preview_poll_timer.timeout.connect(self._poll_preview_files)
        self._preview_poll_timer.start()

    # ── Facade wiring helpers (build defaults for standalone/test use) ──

    @staticmethod
    def _default_file_browser():
        try:
            from app.adapters.filesystem.file_browser_adapter import WindowsFileBrowserAdapter  # noqa: PLC0415
            from app.infrastructure.config import get_settings  # noqa: PLC0415
            s = get_settings()
            return WindowsFileBrowserAdapter(
                nas_username=getattr(s, "nas_username", ""),
                nas_password=getattr(s, "nas_password", ""),
            )
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def _onedrive_base() -> str:
        try:
            from app.infrastructure.config import get_settings  # noqa: PLC0415
            return get_settings().onedrive_base_folder
        except Exception:  # noqa: BLE001
            return "SLC/clips-supervisor"

    # ── Detection callback (called from detection thread) ─────────────

    def on_monitors_updated(self, monitors: List[MonitorInfo]) -> None:
        """Detection-thread callback — marshal to the Qt main thread."""
        self._monitors_from_service.emit(monitors)

    def _apply_monitors_from_service(self, monitors: object) -> None:
        monitor_list = list(monitors)  # type: ignore[arg-type]
        self._recording.on_monitors_updated(monitor_list)
        new_key = frozenset(getattr(m, "device_name", str(m)) for m in monitor_list)
        if new_key != self._last_monitor_key:
            self._last_monitor_key = new_key
            self.monitorsChanged.emit()

    @Slot()
    def identifyMonitors(self) -> None:
        if self._detection_service is not None:
            self._apply_monitors_from_service(self._detection_service.get_monitors())

    # ── Polling (recording state) ─────────────────────────────────────

    def _poll(self) -> None:
        state = self._recording.get_recording_state()
        if state.is_recording != self._is_recording:
            self._is_recording = state.is_recording
            self.isRecordingChanged.emit()
        if state.is_recording and state.record_seconds != self._record_sec:
            self._record_sec = state.record_seconds
            self.recordSecChanged.emit()

    # ── Properties ────────────────────────────────────────────────────

    @Property(bool, notify=isRecordingChanged)
    def isRecording(self) -> bool:
        return self._is_recording

    @Property(int, notify=recordSecChanged)
    def recordSec(self) -> int:
        return self._record_sec

    @Property('QVariantList', notify=monitorsChanged)
    def monitors(self) -> list:
        from PySide6.QtGui import QGuiApplication  # noqa: PLC0415
        qt_screens = QGuiApplication.screens()

        def _qt_idx(mon_x: int, mon_y: int) -> int:
            for i, s in enumerate(qt_screens):
                g = s.geometry()
                if abs(g.x() - mon_x) < 8 and abs(g.y() - mon_y) < 8:
                    return i
            return -1

        result = []
        for m in self._recording.get_monitors():
            result.append({
                'name':        m.name,
                'deviceName':  m.device_name,
                'qtIdx':       _qt_idx(m.x, m.y),
                'res':         m.resolution,
                'active':      m.selected,
                'fingerprint': m.fingerprint,
                'idx':         m.index,
                'x':           m.x,
                'y':           m.y,
            })
        return result

    @Property('QVariantList', notify=clipsChanged)
    def clips(self) -> list:
        return self._clips_list

    @Property(int, notify=eventCountChanged)
    def eventCount(self) -> int:
        return self._event_count

    @Property(str, notify=currentClipPathChanged)
    def currentClipPath(self) -> str:
        return self._current_clip_path

    @Property('QVariantMap', notify=currentClipInfoChanged)
    def currentClipInfo(self) -> dict:
        return self._current_clip_info

    @Property(int, notify=previewRevisionChanged)
    def previewRevision(self) -> int:
        return self._preview_revision

    # ── Recording command slots ───────────────────────────────────────

    @Slot()
    def triggerEvent(self) -> None:
        if self._recording.trigger_event(dto.TriggerEvent()):
            self._event_count += 1
            self.eventCountChanged.emit()
            logger.info("Manual event accepted.")
        else:
            logger.info("Manual event rejected — cooldown active.")

    @Slot()
    def startRecording(self) -> None:
        self._recording.start_recording(dto.StartRecording())
        self._poll()

    @Slot()
    def stopRecording(self) -> None:
        self._recording.stop_recording(dto.StopRecording())
        self._poll()

    @Slot(str)
    def toggleMonitor(self, fingerprint: str) -> None:
        self._recording.toggle_monitor(dto.ToggleMonitor(fingerprint=fingerprint))
        self.monitorsChanged.emit()

    # ── Clip browser slots ────────────────────────────────────────────

    @Slot()
    def refreshClips(self) -> None:
        self._clips_list = [self._clip_to_qml(c) for c in self._clips.list_clips()]
        self.clipsChanged.emit()

    @staticmethod
    def _clip_to_qml(c: dto.ClipDTO) -> dict:
        return {
            'clipName': c.clip_name,
            'path':     c.path,
            'dur':      c.size_label,
            'date':     c.date_label,
            'isEvent':  c.is_event,
        }

    @Slot(str, result=str)
    def mediaUrl(self, path: str) -> str:
        from PySide6.QtCore import QUrl  # noqa: PLC0415
        return QUrl.fromLocalFile(path).toString()

    @Slot(str)
    def loadClip(self, path: str) -> None:
        loaded = self._clips.load_clip(dto.LoadClip(path=path))
        self._current_clip_path = loaded.path
        self.currentClipPathChanged.emit()
        if not loaded.ok:
            return
        if loaded.info is not None:
            self._current_clip_info = {
                'resolution':      loaded.info.resolution,
                'codec':           loaded.info.codec,
                'fps':             loaded.info.fps,
                'bitrate':         loaded.info.bitrate,
                'durationSeconds': loaded.info.duration_seconds,
            }
        else:
            self._current_clip_info = {}
        self.currentClipInfoChanged.emit()

    @Slot(str, result='QVariantList')
    def listDirectory(self, path: str) -> list:
        listing = self._clips.list_directory(dto.ListDirectory(path=path))
        self._last_list_failed = listing.failed
        return [self._entry_to_qml(e) for e in listing.entries]

    @staticmethod
    def _entry_to_qml(e) -> dict:
        return {
            "name":     e.name,
            "path":     e.path,
            "isDir":    e.is_dir,
            "modified": e.modified,
            "size":     e.size,
            "ext":      e.ext,
        }

    @Slot(result=bool)
    def lastListFailed(self) -> bool:
        return self._last_list_failed

    # ── Preview / video sinks (Qt-only) ───────────────────────────────

    @Slot(int, 'QObject*')
    def registerVideoSink(self, monitor_idx: int, sink: object) -> None:
        self._video_sinks[monitor_idx] = sink
        logger.debug("Preview VideoSink registered for monitor idx={}.", monitor_idx)

    def set_preview_paths(self, paths: dict) -> None:
        import time as _time
        self._preview_paths = {int(k): Path(v) for k, v in paths.items()}
        self._preview_ready_at = _time.monotonic() + 1.0  # 1 s grace for FFmpeg init
        logger.info("Preview paths set: {}", {k: str(v) for k, v in self._preview_paths.items()})

    def on_preview_frame(self, monitor_idx: int, jpeg_bytes: bytes) -> None:
        pass  # preview now comes from the file poll, not a callback

    def _poll_preview_files(self) -> None:
        import time as _time                      # noqa: PLC0415
        from PySide6.QtGui import QImage          # noqa: PLC0415
        from PySide6.QtMultimedia import QVideoFrame  # noqa: PLC0415

        # Honour the startup grace period: skip all reads until FFmpeg has had
        # time to write at least one complete preview frame.
        if _time.monotonic() < self._preview_ready_at:
            return

        for monitor_idx, path in self._preview_paths.items():
            try:
                if not path.exists():
                    continue
                st = path.stat()
                mtime = st.st_mtime
                if mtime == self._preview_mtimes.get(monitor_idx):
                    continue
                # Skip files modified within the last 120 ms: FFmpeg's -update 1
                # writes non-atomically, so a too-fresh mtime means the file is
                # still being written and will produce a corrupt JPEG.
                if (_time.time() - mtime) < 0.12:
                    continue
                self._preview_mtimes[monitor_idx] = mtime
                img = QImage(str(path))
                if img.isNull() or img.width() < 16 or img.height() < 16:
                    continue  # reject corrupt / truncated frames
                sink = self._video_sinks.get(monitor_idx)
                if sink is not None:
                    sink.setVideoFrame(QVideoFrame(img))
            except Exception:
                pass  # tolerate transient file-lock during FFmpeg write

    # ── Callbacks from the recording stack (main.py wires these) ───────

    def notify_recording_failed(self, msg: str) -> None:
        self._recording.on_recording_failed(msg)
        self.recordingFailed.emit(msg)

    def notify_clip_failed(self, msg: str) -> None:
        self._recording.on_clip_failed(msg)
        self.clipFailed.emit(msg)

    # ── Request system ────────────────────────────────────────────────

    def set_request_system(self, adapter, slc_storage_host: str, server=None, client=None) -> None:
        """Point the bridge at the request infrastructure main.py already wired
        into ``api.requests`` (server/client are Qt-free — ADR-0009/C1 — so
        their callbacks go straight to the facade; QML no longer gets a push
        signal here, it refreshes via its own "↺ Refrescar" button instead).
        """
        self._requests.configure(
            request_port=adapter, slc_storage_host=slc_storage_host, server=server, client=client
        )
        self._delivery.set_request_port(adapter)
        self.requestSystemChanged.emit()

    @Slot(result='QVariantList')
    def listStorages(self) -> list:
        return [
            {"name": s.name, "path": s.path, "operatorCount": s.operator_count}
            for s in self._requests.list_storages()
        ]

    @Slot(str, result='QVariantList')
    def listOperators(self, storage_path: str) -> list:
        return [{"name": o.name, "storage": o.storage} for o in self._requests.list_operators(storage_path)]

    @Slot(result='QVariantList')
    def listAllOperators(self) -> list:
        return [{"name": o.name, "storage": o.storage} for o in self._requests.list_all_operators()]

    @Slot(str)
    def sendClipRequest(self, request_json: str) -> None:
        self._requests.send_clip_request(dto.SendClipRequest(request_json=request_json))

    @Slot(result='QVariantList')
    def getMyRequests(self) -> list:
        return [r.to_dict() for r in self._requests.my_requests()]

    @Slot(result='QVariantList')
    def getInboxRequests(self) -> list:
        return [r.to_dict() for r in self._requests.inbox_requests()]

    @Slot(str, str)
    def updateRequestStatus(self, req_id: str, status: str) -> None:
        self._requests.update_request_status(dto.UpdateRequestStatus(request_id=req_id, status=status))
        self.requestReceived.emit()   # refresh inbox UI

    @Property(bool, notify=requestSystemChanged)
    def itServerActive(self) -> bool:
        return self._requests.server is not None

    @Property(int, notify=requestSystemChanged)
    def itServerPort(self) -> int:
        server = self._requests.server
        if server is None:
            return 0
        return int(getattr(server, "_port", 0))

    # ── OneDrive delivery ─────────────────────────────────────────────

    @Property(str, notify=oneDriveChanged)
    def oneDriveState(self) -> str:
        return self._one_drive_state

    @Property(str, notify=oneDriveChanged)
    def oneDriveFolder(self) -> str:
        return self._one_drive_folder

    @Property(str, notify=oneDriveChanged)
    def oneDriveLink(self) -> str:
        return self._one_drive_link

    @Slot()
    @Slot(str)
    def ensureFolderLink(self, folder_path: str = "") -> None:
        """Run the OneDrive flow off the UI thread; result marshalled via _share_done."""
        if not self._delivery.available:
            logger.warning("ensureFolderLink: no cloud share service wired.")
            self._set_one_drive_error("OneDrive no está configurado.")
            return
        path = (folder_path or "").strip() or self._delivery.compute_folder_path()
        self._one_drive_folder = path
        self._one_drive_link = ""
        self._one_drive_state = "working"
        self.oneDriveChanged.emit()
        logger.info("OneDrive: ensuring folder '{}'.", path)
        self._run_share_async(path)

    @Slot()
    def resetOneDrive(self) -> None:
        if (self._one_drive_state, self._one_drive_folder, self._one_drive_link) == ("idle", "", ""):
            return
        self._one_drive_state = "idle"
        self._one_drive_folder = ""
        self._one_drive_link = ""
        self.oneDriveChanged.emit()

    @Slot(str)
    def copyToClipboard(self, text: str) -> None:
        from PySide6.QtGui import QGuiApplication  # noqa: PLC0415
        app = QGuiApplication.instance()
        if isinstance(app, QGuiApplication):
            cb = app.clipboard()
            if cb is not None:
                cb.setText(text or "")

    def _run_share_async(self, folder_path: str) -> None:
        """Spawn a daemon thread; overridable in tests to run inline."""
        threading.Thread(
            target=self._do_share, args=(folder_path,), daemon=True, name="onedrive-share"
        ).start()

    def _do_share(self, folder_path: str) -> None:
        """Runs OFF the Qt main thread — marshals the outcome via _share_done."""
        try:
            result = self._delivery.ensure_folder_and_link(folder_path)
            self._share_done.emit(result)
        except Exception as exc:  # noqa: BLE001
            logger.exception("OneDrive share failed for '{}'.", folder_path)
            self._share_done.emit(exc)

    def _apply_share_result(self, payload: object) -> None:
        """Runs on the Qt main thread (queued) — safe to touch QML state."""
        if isinstance(payload, (dto.ShareResultDTO, ShareResult)):
            self._one_drive_folder = payload.folder_path
            self._one_drive_link = payload.share_link
            self._one_drive_state = "linked"
            self.oneDriveChanged.emit()
            logger.info("OneDrive: link ready for '{}'.", payload.folder_path)
        else:
            self._set_one_drive_error(str(payload) if payload else "Error desconocido.")

    def _set_one_drive_error(self, msg: str) -> None:
        self._one_drive_state = "error"
        self.oneDriveChanged.emit()
        self.oneDriveFailed.emit(msg)
