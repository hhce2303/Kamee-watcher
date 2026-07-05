from __future__ import annotations
import sys
import os
import pathlib
# Ensure the app package is discoverable when running main.py directly
sys.path.append(str(pathlib.Path(__file__).parent.parent))

# Ensure Qt can find its platform plugins (dev venv and PyInstaller frozen builds)
try:
    import PySide6
    _pyside6_dir     = pathlib.Path(PySide6.__file__).parent
    _pyside6_plugins = _pyside6_dir / "plugins"
    _qt_platforms    = _pyside6_plugins / "platforms"

    # Python 3.8+ on Windows uses a restricted DLL search path.
    # Register the PySide6 root so that plugin DLLs (e.g. ffmpegmediaplugin.dll,
    # windowsmediaplugin.dll) can resolve their Qt6*.dll dependencies at load time.
    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(str(_pyside6_dir))

    if _qt_platforms.exists():
        os.environ.setdefault("QT_QPA_PLATFORM_PLUGIN_PATH", str(_qt_platforms))
    elif getattr(sys, "frozen", False):
        # PyInstaller may unpack PySide6 one level up inside _MEIPASS
        _frozen_plugins = pathlib.Path(sys._MEIPASS) / "PySide6" / "plugins" / "platforms"  # type: ignore[attr-defined]
        if _frozen_plugins.exists():
            os.environ.setdefault("QT_QPA_PLATFORM_PLUGIN_PATH", str(_frozen_plugins))

    # QT_PLUGIN_PATH must point to the *parent* of the multimedia/ sub-directory
    # so that Qt's plugin loader finds ffmpegmediaplugin / windowsmediaplugin.
    if _pyside6_plugins.exists():
        _cur = os.environ.get("QT_PLUGIN_PATH", "")
        _pp  = str(_pyside6_plugins)
        if _pp not in _cur:
            os.environ["QT_PLUGIN_PATH"] = _pp + (os.pathsep + _cur if _cur else "")
except ImportError:
    pass

import atexit
import os
import signal
import sys
import time
from typing import List

from loguru import logger
from pathlib import Path

from app.infrastructure.config import get_settings
from app.infrastructure.logging_setup import configure_logging
from app.core.recording_service.buffer_manager import BufferManager
from app.core.recording_service.clip_builder import ClipBuilder
from app.core.recording_service.models import MonitorInfo, Segment
from app.core.recording_service.monitor_worker import MonitorWorker
from app.core.recording_service.service import RecordingService
from app.core.event_service import EventService
from app.core.cloud_share_service import CloudShareService
from app.adapters.cloud.local_share_adapter import LocalShareAdapter
from app.core.player.player_service import PlayerService
from app.core.role import (
    OPERATOR,
    SUPERVISOR,
    enforce_role,
    is_recording_role,
    should_autorecord_on_launch,
)
from app.adapters.ffmpeg import encoder_selector
from app.adapters.ffmpeg.recorder_adapter import FFmpegRecorderAdapter
from app.adapters.ffmpeg.trim_adapter import FFmpegTrimAdapter
from app.adapters.ffmpeg.timestamp_adapter import FFmpegTimestampAdapter
from app.adapters.ffmpeg.clip_inspector_adapter import FFprobeClipInspectorAdapter
from app.adapters.ffmpeg.mp4_converter_adapter import FFmpegMp4ConverterAdapter
from app.adapters.ffmpeg.hourly_recording_builder import HourlyRecordingBuilder
from app.adapters.ffmpeg.combined_clip_builder import CombinedClipBuilder
from app.adapters.ffmpeg.editor_export_adapter import FFmpegEditorExportAdapter
from app.adapters.native import make_segment_compiler
from app.adapters.storage.sqlite_event_store import SqliteEventStoreAdapter
from app.adapters.filesystem.file_browser_adapter import WindowsFileBrowserAdapter
from app.core.api.bootstrap import build_api_layer
from app.runtime.backend import build_recording_backend
from app.runtime.mode import DAEMON, SIDECAR, resolve_mode
from app.core.analytics.manual_event import analytic_event_from_context
from app.core.analytics.sidecar import write_sidecar
from app.adapters.filesystem.storage_adapter import FilesystemStorageAdapter
from app.adapters.filesystem.user_config_adapter import JsonUserConfigAdapter
from app.adapters.monitor.screeninfo_adapter import ScreeninfoMonitorAdapter
from app.adapters.ui import tray_icon as tray_module
from app.adapters.filesystem.request_adapter import JsonRequestAdapter
from app.core.recording_service.supervisor import RecorderSupervisor
from app.core.role import IT, SUPERVISOR
from app.core.disk_monitor import DiskSpaceMonitor
from app.core.monitor_detection.service import MonitorDetectionService
from app.core.recording_health.service import RecordingHealthService
# LivePreviewService removed — preview is now embedded in the recorder FFmpeg process


def _register_ffmpeg_cleanup() -> None:
    """Register an atexit hook that kills any child ffmpeg processes on exit.

    This is the last-resort safety net: the job objects (process_guard) handle
    forceful kills, while this handles the race window where a supervisor thread
    spawns a new FFmpeg process after recording_service.stop() returns.
    """
    import psutil  # noqa: PLC0415

    def _cleanup() -> None:
        try:
            me = psutil.Process(os.getpid())
            for child in me.children(recursive=True):
                if "ffmpeg" in child.name().lower():
                    try:
                        child.kill()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
        except Exception:  # noqa: BLE001
            pass

    atexit.register(_cleanup)


def _acquire_single_instance_lock(operator_silent: bool = False) -> object:
    """Return a Windows named mutex that prevents a second instance from starting.

    Returns the mutex handle (must stay in scope for the life of the process).
    Exits if another instance already holds the mutex.

    Retries briefly on ERROR_ALREADY_EXISTS: a role change relaunches the app,
    spawning the replacement while the outgoing instance is still releasing the
    mutex.  That transient collision is expected, so we wait for the old handle
    to drop before deciding a genuine second instance is running.

    ``operator_silent`` (operator box): on contention, exit **0** with no dialog.
    The operator's restart watchdog (a Scheduled Task) relaunches on a non-zero
    result, so a benign collision must not read as a crash — otherwise the
    scheduler would spin-loop relaunching.  And a kiosk operator must never see
    a tkinter error box.
    """
    import ctypes
    ERROR_ALREADY_EXISTS = 183
    deadline = time.monotonic() + 3.0
    while True:
        mutex = ctypes.windll.kernel32.CreateMutexW(None, True, "TheWatcher_SingleInstance")
        if ctypes.windll.kernel32.GetLastError() != ERROR_ALREADY_EXISTS:
            return mutex  # keep alive
        # We got a handle to the *existing* mutex; drop it before retrying.
        ctypes.windll.kernel32.CloseHandle(mutex)
        if time.monotonic() >= deadline:
            break
        time.sleep(0.2)

    if operator_silent:
        # Benign collision on an operator box: exit cleanly, no dialog, exit 0.
        logger.info("Another instance already running (operator) — exiting quietly.")
        sys.exit(0)

    import tkinter, tkinter.messagebox  # noqa: PLC0415
    try:
        root = tkinter.Tk(); root.withdraw()
        tkinter.messagebox.showerror(
            "The Watcher",
            "Another instance is already running.\nClose it before starting a new one.",
        )
        root.destroy()
    except Exception:
        pass
    sys.exit(1)


def _peek_role() -> str:
    """Best-effort read of the persisted role BEFORE the single-instance lock.

    Needed so an operator box can suppress the contention dialog and exit 0.
    Cheap (one JSON read); any failure falls back to "" (non-operator behaviour).
    """
    try:
        from app.adapters.filesystem.user_config_adapter import JsonUserConfigAdapter  # noqa: PLC0415
        return JsonUserConfigAdapter().load().role or ""
    except Exception:  # noqa: BLE001
        return ""


def _release_single_instance_lock(mutex: object) -> None:
    """Release and close the single-instance mutex.

    Called right before a relaunch so the replacement instance can acquire it.
    """
    try:
        import ctypes
        ctypes.windll.kernel32.ReleaseMutex(mutex)
        ctypes.windll.kernel32.CloseHandle(mutex)
    except Exception:  # noqa: BLE001
        pass


def main() -> None:
    # Peek the role before the lock so an operator box exits 0 (no dialog) on a
    # benign contention — its restart watchdog must not read that as a crash.
    _instance_lock = _acquire_single_instance_lock(operator_silent=_peek_role() == OPERATOR)
    # Set by the role-change relaunch callback; checked after app.exec() returns
    # so the existing teardown runs once before we spawn the replacement.
    _relaunch_flag = {"requested": False}
    _register_ffmpeg_cleanup()
    configure_logging()
    settings = get_settings()

    # ── User config (persisted preferences) ──────────────────────────
    user_config_port = JsonUserConfigAdapter()
    user_config = user_config_port.load()

    # Override clips_dir with user-chosen path if one was saved.
    clips_dir = (
        Path(user_config.clips_dir) if user_config.clips_dir else settings.clips_dir
    )

    # ── Role enforcement ──────────────────────────────────────────────
    # Applies per-role constraints (forced autorecord, autostart registry)
    # before any service is started.  enforce_role() mutates user_config
    # in-place but does NOT re-persist — autorecord/autostart for operator
    # are always overridden at startup without changing the stored value.
    from app.infrastructure import autostart as _autostart_mod  # noqa: PLC0415
    from app.infrastructure import scheduled_task as _scheduled_task_mod  # noqa: PLC0415
    # Operator: a Scheduled Task is the sole launcher (restart-on-failure);
    # returns "task" (registered) or "runkey" (degraded fallback). Non-operator
    # roles return None and we remove any stale watchdog left from a prior role.
    watchdog_status = enforce_role(
        user_config.role, user_config, _autostart_mod, _scheduled_task_mod
    )
    if user_config.role != OPERATOR:
        _scheduled_task_mod.remove_task()
    logger.info(
        "Role: {} | watchdog: {}",
        user_config.role or "(not configured)",
        watchdog_status or "n/a",
    )

    # ── Per-PC encoder selection ──────────────────────────────────────
    # driver: auto/nvidia/intel/amd/cpu (RTX machines can force NVENC).
    # codec:  user override of the .env VIDEO_CODEC default.
    # Mutating settings.video_codec here means every adapter built below
    # (recorder + clip builders) picks up the resolved codec uniformly.
    encoder_selector.set_preferences(driver=user_config.driver)
    if user_config.codec:
        settings.video_codec = user_config.codec.lower()
    logger.info(
        "Encoder config: driver={} codec={}", user_config.driver, settings.video_codec
    )

    logger.info("The Watcher starting...")
    logger.info(
        "Config: segment_dir={} clips_dir={} retention={}h segment_duration={}s",
        settings.segment_dir,
        clips_dir,
        settings.retention_hours,
        settings.segment_duration,
    )

    # ── Ensure output directories exist from the very first second ────
    # clips_dir is normally created lazily (on first clip build) which means
    # the folder wouldn't appear until an event is triggered.  Create it now
    # so the user can confirm the correct output location immediately.
    clips_dir.mkdir(parents=True, exist_ok=True)
    settings.segment_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Output directories ready: segments={} | clips={}", settings.segment_dir, clips_dir)

    # ── Infrastructure ────────────────────────────────────────────────
    storage         = FilesystemStorageAdapter()
    monitor_adapter = ScreeninfoMonitorAdapter()

    # ── Phase 1: MonitorDetectionService — source of truth for monitors ──
    # detect_now() runs synchronously so we have confirmed monitors before
    # creating workers. start() then polls in background, auto-adding/removing
    # workers as monitors are connected or disconnected.
    detection_service = MonitorDetectionService(
        monitor_port=monitor_adapter,
        poll_interval_seconds=5.0,
    )
    all_monitors = detection_service.detect_now()
    # Only recording roles (operator / IT) need a monitor.  Supervisor and the
    # unconfigured first-run state launch without one (clips-only / role wizard).
    if not all_monitors and is_recording_role(user_config.role):
        logger.critical("No monitors detected — cannot start recording.")
        sys.exit(1)
    elif not all_monitors:
        logger.info("Non-recording role — no monitors required, skipping recording setup.")

    # ── Directory layout ──────────────────────────────────────────────
    # WatcherData/
    #   clips/          ← combined multi-monitor MP4 + timestamp overlay
    #   clips_raw/      ← individual per-monitor raw clips (one file per screen)
    #   segments/       ← rolling MPEG-TS segments (buffer, auto-pruned)
    raw_clips_dir = settings.raw_clips_dir
    raw_clips_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Directory layout: combined={} | raw={} | segments={}",
                clips_dir, raw_clips_dir, settings.segment_dir)

    # ── Recording stack (skipped for Supervisor role) ────────────────
    # Built by the shared, Qt-free factory so the headless daemon/sidecar
    # (ADR-0010) construct the same backend. Unpacked into locals so the rest
    # of the Qt startup below is unchanged.
    backend = build_recording_backend(
        settings=settings,
        user_config=user_config,
        storage=storage,
        all_monitors=all_monitors,
        clips_dir=clips_dir,
        raw_clips_dir=raw_clips_dir,
    )
    combined_builder     = backend.combined_builder
    per_monitor_builders = backend.per_monitor_builders
    workers              = backend.workers
    preview_paths        = backend.preview_paths
    recording_service    = backend.recording_service
    clip_builder         = backend.clip_builder
    event_service        = backend.event_service
    disk_monitor         = backend.disk_monitor
    health_service       = backend.health_service
    event_store          = backend.event_store
    auto_event_service   = backend.auto_event_service

    # ── Phase 4: Preview paths (embedded in recorder, no separate process) ──
    # preview_paths already populated above in the worker-building loop.
    # AppBridge will poll these files every 500 ms from its QTimer.

    # ── Start recording ───────────────────────────────────────────────
    # Operator always records; IT only if its autorecord toggle is on;
    # supervisor / unconfigured never start here (and have no stack anyway).
    if recording_service is not None and should_autorecord_on_launch(
        user_config.role, user_config.autorecord
    ):
        recording_service.start()
        tray_module.set_recording_active(True)
    elif recording_service is not None:
        logger.info("Auto-record off for this role/config — buffer not started at launch.")
        tray_module.set_recording_active(False)
    else:
        tray_module.set_recording_active(False)
    if health_service is not None:
        health_service.start()
    if disk_monitor is not None:
        disk_monitor.start()
    detection_service.start()
    if auto_event_service is not None:
        auto_event_service.start()

    # ── Startup recovery: rebuild clips from existing segments ────────
    for w in workers:
        b = per_monitor_builders[w.monitor.index]
        all_segs = list(w.buffer.all_segments())
        if all_segs:
            logger.info(
                "Starting clip recovery for m{} — {} segment(s) in buffer.",
                w.monitor.index, len(all_segs),
            )
            b.recover_from_segments(all_segs)
        else:
            logger.info(
                "No existing segments for m{} — starting fresh.",
                w.monitor.index,
            )

    # ── Combined clip recovery ────────────────────────────────────────
    if combined_builder is not None:
        combined_builder.recover(backfill_hours=settings.retention_hours)

    # ── Player / Editor / OneDrive services (no Qt) ───────────────────
    inspector      = FFprobeClipInspectorAdapter()
    player_service = PlayerService(inspector=inspector)
    # Rust segment engine when available, FFmpeg fallback otherwise (ADR-0006).
    segment_compiler = make_segment_compiler(codec=settings.video_codec)
    # reencode=True: frame-exact cuts + normalize every clip to one format, so
    # mixed-codec/resolution reels just work (evidence reel favors precision).
    editor_export    = FFmpegEditorExportAdapter(
        segment_compiler, inspector=inspector, reencode=True
    )
    # Local adapter today (real folders under the OneDrive sync root, file:// links);
    # swap to OneDriveGraphAdapter once Azure AD creds exist — adapter-agnostic.
    cloud_share_service = CloudShareService(
        LocalShareAdapter(root=settings.onedrive_root)
    )

    # ── core/api layer (F1, ADR-0009) ─────────────────────────────────
    # One EventBus + the facades over every built service. The QML bridges and
    # the IPC channel are interchangeable input adapters over this layer.
    # event_store doubles as the AuditPort so start/stop/unlock/setRole are
    # audited on every path (ADR-0011); it is None on non-recording roles.
    file_browser = WindowsFileBrowserAdapter(
        nas_username=settings.nas_username, nas_password=settings.nas_password
    )
    api = build_api_layer(
        detection_service=detection_service,
        settings=settings,
        user_config_port=user_config_port,
        audit_port=event_store,
        recording_service=recording_service,
        event_service=event_service,
        player_service=player_service,
        export_port=editor_export,
        inspector=inspector,
        file_browser=file_browser,
        cloud_share_service=cloud_share_service,
        clips_dir=clips_dir,
        slc_storage_host=settings.slc_storage_host,
        onedrive_base_folder=settings.onedrive_base_folder,
        analytics_query=backend.analytics,
    )
    api.start()

    def _stop_backend() -> None:
        """Stop the whole recording stack — kills FFmpeg, no orphans (TD-3)."""
        if auto_event_service is not None:
            auto_event_service.stop()
        if health_service is not None:
            health_service.stop()
        detection_service.stop()
        if disk_monitor is not None:
            disk_monitor.stop()
        if event_service is not None:
            event_service.stop()
        if recording_service is not None:
            recording_service.stop()
        for b in per_monitor_builders.values():
            b.shutdown()
        if combined_builder is not None:
            combined_builder.shutdown()

    # ── Role-conditional topology (ADR-0010): headless daemon / sidecar ──
    # Operator = --daemon (decoupled, survives window close); IT/Supervisor =
    # --sidecar (launched by Tauri, stops on stdin shutdown). Same IPC contract,
    # no Qt. No flag → the QML path below (unchanged in F1).
    mode = resolve_mode(sys.argv)
    if mode in (DAEMON, SIDECAR):
        from app.adapters.ipc.pipe_server import NamedPipeIpcServer  # noqa: PLC0415
        from app.adapters.ipc.router import IpcRouter                # noqa: PLC0415
        from app.runtime.headless import HeadlessRuntime             # noqa: PLC0415

        # Hot-plug wiring without a UI bridge: add/remove recording workers.
        if recording_service is not None and backend.build_worker_for is not None:
            def _hot_add(monitor: MonitorInfo) -> None:
                w = backend.build_worker_for(monitor)
                w.segment_dir.mkdir(parents=True, exist_ok=True)
                recording_service.add_worker(w)
            detection_service._on_monitor_added   = _hot_add                         # noqa: SLF001
            detection_service._on_monitor_removed = recording_service.remove_worker  # noqa: SLF001

        pipe_server = NamedPipeIpcServer(IpcRouter(api), api.bus)
        runtime = HeadlessRuntime(api, pipe_server, on_stop=_stop_backend)
        logger.info("Headless '{}' mode — serving IPC contract, no Qt UI.", mode)
        code = runtime.serve_daemon() if mode == DAEMON else runtime.serve_sidecar()
        _release_single_instance_lock(_instance_lock)
        sys.exit(code)

    def _shutdown(signum: int, frame: object) -> None:
        logger.info("Shutdown signal received (signal={}).", signum)
        tray_module.set_recording_active(False)
        _stop_backend()
        api.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # ── Launch UI ─────────────────────────────────────────────────────
    from PySide6.QtWidgets import QApplication          # noqa: PLC0415
    from PySide6.QtQml import QQmlApplicationEngine     # noqa: PLC0415
    from PySide6.QtCore import QUrl, QTimer             # noqa: PLC0415
    from app.adapters.ui.app_bridge import AppBridge    # noqa: PLC0415
    from app.adapters.ui.settings_bridge import SettingsBridge  # noqa: PLC0415
    from app.adapters.ui.editor_bridge import EditorBridge  # noqa: PLC0415
    from app.adapters.ui.tray_icon import TrayIcon      # noqa: PLC0415

    app = QApplication(sys.argv)   # keep QApplication — QSystemTrayIcon requires it
    app.setQuitOnLastWindowClosed(False)

    editor_bridge = EditorBridge(editor_api=api.editor)

    # ── Bridge objects ────────────────────────────────────────────────
    bridge = AppBridge(
        detection_service=detection_service,
        clips_dir=clips_dir,
        recording_api=api.recording,
        clips_api=api.clips,
        requests_api=api.requests,
        delivery_api=api.delivery,
        event_bus=api.bus,
    )
    # ── Wire detection → recording + UI (bridge is now in scope) ────────
    def _on_monitor_added(monitor: MonitorInfo) -> None:
        worker = backend.build_worker_for(monitor)
        worker.segment_dir.mkdir(parents=True, exist_ok=True)
        recording_service.add_worker(worker)
        worker.set_on_recording_failed(bridge.notify_recording_failed)

    # Hot-plug → recording callbacks only apply when a recording stack exists
    # (operator / IT).  Supervisor and unconfigured machines have no
    # recording_service; they only refresh the UI monitor list.
    if recording_service is not None:
        detection_service._on_monitor_added    = _on_monitor_added              # noqa: SLF001
        detection_service._on_monitor_removed  = recording_service.remove_worker  # noqa: SLF001
    detection_service._on_monitors_changed = bridge.on_monitors_updated  # noqa: SLF001
    settings_bridge = SettingsBridge(
        user_config_port=user_config_port,
        settings=settings,
        settings_api=api.settings,
    )

    # ── "Apply encoder now" callback ──────────────────────────────────
    # Called from a background thread when the user clicks "Aplicar ahora".
    # Stops the live recording, applies the new codec/driver to every recorder
    # adapter, then restarts. Takes ~2 s; must not touch Qt from this thread.
    def _restart_recording(codec: str, driver: str) -> None:
        if recording_service is None:
            return
        logger.info("Restarting recording: codec={} driver={}", codec, driver)
        was_running = recording_service.is_recording()
        recording_service.stop()
        # Apply encoder preference and clear the probe cache.
        encoder_selector.set_preferences(driver=driver)
        # Push the new codec to every recorder adapter so it takes effect
        # when start() is called below.  settings.video_codec is the live
        # value used by adapters not yet instantiated (e.g. hot-added monitors).
        settings.video_codec = codec
        for worker in list(recording_service._workers.values()):  # noqa: SLF001
            if hasattr(worker._recorder, "update_codec"):          # noqa: SLF001
                worker._recorder.update_codec(codec)               # noqa: SLF001
        if was_running:
            recording_service.start()
            tray_module.set_recording_active(True)
            logger.info("Recording restarted with codec={} driver={}.", codec, driver)
        else:
            logger.info("Recording was stopped — not restarting (autorecord=off).")

    settings_bridge.set_restart_callback(_restart_recording)

    # ── Role-change relaunch ──────────────────────────────────────────
    # The whole backend is wired at startup from the role, so a role change
    # (first-run wizard or an IT-initiated change) is applied by re-running
    # main() in a fresh process.  We flag the request and quit the event loop;
    # the post-exec teardown below stops everything once, then we spawn.
    # QTimer defers quit() so the QML slot that called setRole() returns first
    # and the config write flushes.
    def _request_relaunch() -> None:
        if _relaunch_flag["requested"]:
            return
        _relaunch_flag["requested"] = True
        logger.info("Role change — scheduling relaunch.")
        QTimer.singleShot(0, app.quit)

    # Role change / autorecord side effects live on the shared settings facade
    # (so the IPC path triggers them too); the encoder restart stays bridge-side.
    api.settings.set_relaunch_cb(_request_relaunch)

    # ── Live autorecord toggle (IT) ───────────────────────────────────
    # IT records optionally: the stack is built but parked.  Toggling the
    # setting starts/stops the existing workers in-process (no restart).
    def _apply_autorecord(enabled: bool) -> None:
        if recording_service is None:
            return
        if enabled:
            recording_service.start()
            tray_module.set_recording_active(True)
            logger.info("Autorecord enabled — recording started.")
        else:
            recording_service.stop()
            tray_module.set_recording_active(False)
            logger.info("Autorecord disabled — recording stopped.")

    api.settings.set_autorecord_cb(_apply_autorecord)

    # ── QML engine ────────────────────────────────────────────────────
    engine = QQmlApplicationEngine()
    # Surface QML load/binding errors to the log. Without this, a failed
    # engine.load() only yields a generic "QML failed to load" with no cause —
    # critical for diagnosing frozen builds where stderr is unavailable.
    engine.warnings.connect(
        lambda warns: [logger.error("QML: {}", w.toString()) for w in warns]
    )
    ui_dir = Path(__file__).parent / "adapters" / "ui"
    # Add the PySide6 qml/ directory so QtQuick, QtQuick.Controls,
    # QtMultimedia, etc. are resolvable at runtime.
    try:
        import PySide6 as _PySide6
        _pyside6_qml = Path(_PySide6.__file__).parent / "qml"
        if _pyside6_qml.exists():
            engine.addImportPath(str(_pyside6_qml))
    except ImportError:
        pass
    engine.addImportPath(str(ui_dir))
    # GDI-based monitor screenshot provider — works on all monitors/GPUs
    engine.addImageProvider("monitor_preview", bridge.screenshot_provider)
    engine.rootContext().setContextProperty("AppBridge", bridge)
    engine.rootContext().setContextProperty("SettingsBridge", settings_bridge)
    engine.rootContext().setContextProperty("EditorBridge", editor_bridge)
    # Role capability policy — constant for the life of the process (role only
    # changes via relaunch). QML reads e.g. Policy.canMinimizeWindow. The one
    # thing that changes at runtime, the IT unlock, stays on SettingsBridge.
    from app.core.policy import policy_for  # noqa: PLC0415
    engine.rootContext().setContextProperty(
        "Policy", policy_for(user_config.role).as_dict()
    )
    qml_path = ui_dir / "Main.qml"
    logger.info("Loading QML: {} (exists={})", qml_path, qml_path.exists())
    engine.load(QUrl.fromLocalFile(str(qml_path.resolve())))
    if not engine.rootObjects():
        logger.critical("QML failed to load — stopping recording and exiting.")
        tray_module.set_recording_active(False)
        if auto_event_service is not None:
            auto_event_service.stop()
        if health_service is not None:
            health_service.stop()
        detection_service.stop()
        if disk_monitor is not None:
            disk_monitor.stop()
        if event_service is not None:
            event_service.stop()
        if recording_service is not None:
            recording_service.stop()
        for b in per_monitor_builders.values():
            b.shutdown()
        sys.exit(-1)

    # Wire failure callbacks through bridge signals
    for w in workers:
        w.set_on_recording_failed(bridge.notify_recording_failed)
    if event_service is not None:
        event_service._on_clip_failed = bridge.notify_clip_failed  # noqa: SLF001

    # ── Request system (IT server / Supervisor client) ────────────────
    # Both roles share the same JsonRequestAdapter (same filesystem schema).
    # IT starts a WS server; Supervisor starts a WS client.
    _req_adapter = JsonRequestAdapter()
    _req_server  = None
    _req_client  = None

    if user_config.role == IT:
        from app.adapters.ws.request_server import ClipRequestServer  # noqa: PLC0415
        _req_server = ClipRequestServer(
            port=settings.it_ws_port,
            request_adapter=_req_adapter,
            parent=app,
        )
        _req_server.start()

    elif user_config.role == SUPERVISOR:
        from app.adapters.ws.request_client import ClipRequestClient  # noqa: PLC0415
        _req_client = ClipRequestClient(
            hosts=user_config.it_ws_hosts,
            port=settings.it_ws_port,
            parent=app,
        )

    bridge.set_request_system(
        adapter=_req_adapter,
        slc_storage_host=settings.slc_storage_host,
        server=_req_server,
        client=_req_client,
    )

    if _req_client is not None:
        settings_bridge.itWsHostsChanged.connect(_req_client.set_hosts)

    # ── Phase 4: Tell AppBridge where to find the preview JPEGs ─────────
    bridge.set_preview_paths(preview_paths)

    tray = TrayIcon(
        show_fn=lambda: bridge.requestShowWindow.emit(),
        app=app,
        role=user_config.role,
        watchdog_status=watchdog_status,
    )  # noqa: F841

    logger.info("UI ready. Role: {}.", user_config.role or "not configured")

    exit_code = app.exec()

    api.stop()
    tray_module.set_recording_active(False)
    if auto_event_service is not None:
        auto_event_service.stop()
    if health_service is not None:
        health_service.stop()
    detection_service.stop()
    if disk_monitor is not None:
        disk_monitor.stop()
    if event_service is not None:
        event_service.stop()
    if recording_service is not None:
        recording_service.stop()
    for b in per_monitor_builders.values():
        b.shutdown()
    if combined_builder is not None:
        combined_builder.shutdown()
    if _req_server is not None:
        _req_server.stop()
    if _req_client is not None:
        _req_client.disconnect_all()

    if _relaunch_flag["requested"]:
        # The teardown above already stopped every service (including FFmpeg),
        # so we only need to free the single-instance mutex and spawn the
        # replacement, which re-runs main() with the new role.
        from app.infrastructure.relaunch import relaunch_and_exit  # noqa: PLC0415
        relaunch_and_exit(
            teardown=lambda: None,
            release_lock=lambda: _release_single_instance_lock(_instance_lock),
        )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
