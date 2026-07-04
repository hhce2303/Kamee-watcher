from __future__ import annotations

import subprocess
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Optional

from loguru import logger
from PySide6.QtCore import QObject, Property, Signal, Slot

from app.adapters.ffmpeg import encoder_selector
from app.core.api import dto
from app.core.api.events import EventBus
from app.core.api.settings_api import SettingsApi
from app.core.ports.user_config_port import UserConfigPort
from app.infrastructure import autostart
from app.infrastructure.config import Settings

# Canonical driver order — index matches the UI dropdown model.
_DRIVERS = ["auto", "nvidia", "intel", "amd", "cpu"]

# Restart states surfaced to QML for UI feedback.
_RESTART_IDLE    = "idle"
_RESTART_RUNNING = "restarting"
_RESTART_DONE    = "done"
_RESTART_ERROR   = "error"

# Windows Firewall rule name prefix for the IT WebSocket server port.
_FW_RULE_PREFIX = "TheWatcher-IT-WS"


class SettingsBridge(QObject):
    """
    Exposes persisted per-PC user config and read-only app settings to QML.

    Writable (persisted to user_config.json immediately):
    - clipsDir            — output directory for combined clips
    - driverIndex         — encoder hardware: auto / nvidia / intel / amd / cpu
    - codec               — "h264" | "hevc"
    - autostart           — launch with Windows (Run registry key)
    - autorecord          — begin the rolling buffer on launch
    - role                — "operator" | "supervisor" | "it" | "" (not configured)

    Read-only (from Settings / .env):
    - captureFramerate, outputResolution, segmentDuration, retentionHours, …

    Role system:
    - ``role == ""`` → first-run wizard shown by QML (RoleSetupWizard.qml)
    - ``isITUnlocked`` → transient session flag; set via ``unlockIT(pin)``
    - ``setRole`` only allowed if role==IT or isITUnlocked
    - PIN is validated against ``settings.it_pin`` (from IT_PIN in .env)
    """

    clipsDirChanged      = Signal()
    encoderInfoChanged   = Signal()
    encoderChanged       = Signal()
    systemChanged        = Signal()
    restartStateChanged  = Signal()
    roleChanged          = Signal()
    itWsHostsChanged     = Signal(list)
    itWsPortStatusChanged = Signal()

    def __init__(
        self,
        user_config_port: UserConfigPort,
        settings: Settings,
        parent: QObject | None = None,
        *,
        settings_api: SettingsApi | None = None,
    ) -> None:
        super().__init__(parent)
        self._port = user_config_port
        self._settings = settings
        self._restart_cb: Optional[Callable[[str, str], None]] = None
        self._relaunch_cb: Optional[Callable[[], None]] = None
        self._autorecord_cb: Optional[Callable[[bool], None]] = None
        # main.py injects the shared facade (with audit + process callbacks wired);
        # standalone (tests) builds its own over a private bus. The facade owns
        # persistence, validation, authorization and audit — the bridge only caches
        # display state and emits Qt signals (coexistence dual-path, ADR-0009).
        self._api = settings_api or SettingsApi(
            event_bus=EventBus(),
            user_config_port=user_config_port,
            settings=settings,
            audit_port=None,
            # Late-bound so main.py can register the callbacks after construction.
            relaunch_cb=lambda: self._relaunch_cb() if self._relaunch_cb else None,
            autorecord_cb=lambda enabled: (
                self._autorecord_cb(enabled) if self._autorecord_cb else None
            ),
        )
        cfg = self._port.load()
        self._clips_dir: str = cfg.clips_dir or str(settings.clips_dir)
        self._driver: str = cfg.driver if cfg.driver in _DRIVERS else "auto"
        self._codec: str = (cfg.codec or settings.video_codec or "hevc").lower()
        self._autorecord: bool = cfg.autorecord
        self._it_ws_hosts: list = list(cfg.it_ws_hosts)
        self._restart_state: str = _RESTART_IDLE
        self._it_ws_port_status: str = "unknown"  # unknown | open | closed | opening | error

    def set_restart_callback(self, callback: Callable[[str, str], None]) -> None:
        """Register the restart function from main.py.

        Signature: ``callback(codec: str, driver: str) -> None``
        Called in a background thread — must be thread-safe and not touch Qt directly.
        """
        self._restart_cb = callback

    def set_relaunch_callback(self, callback: Callable[[], None]) -> None:
        """Register the process-relaunch function from main.py.

        Invoked from ``setRole`` after a role change is persisted.  main()
        re-runs in a fresh process so the backend re-wires for the new role.
        Called on the Qt main thread.
        """
        self._relaunch_cb = callback

    def set_autorecord_callback(self, callback: Callable[[bool], None]) -> None:
        """Register the live autorecord start/stop function from main.py.

        Signature: ``callback(enabled: bool) -> None``.  Lets IT turn recording
        on/off without a restart (the stack is already built, just parked).
        Called on the Qt main thread.
        """
        self._autorecord_cb = callback

    # ── Read-only Settings (from .env) ────────────────────────────────

    @Property(str, notify=clipsDirChanged)
    def clipsDir(self) -> str:
        return self._clips_dir

    @Property(str, notify=encoderInfoChanged)
    def captureFramerate(self) -> str:
        return str(self._settings.capture_framerate)

    @Property(str, notify=encoderInfoChanged)
    def outputResolution(self) -> str:
        return f'{self._settings.output_width}×{self._settings.output_height}'

    @Property(int, notify=encoderInfoChanged)
    def outputWidth(self) -> int:
        return self._settings.output_width

    @Property(int, notify=encoderInfoChanged)
    def outputHeight(self) -> int:
        return self._settings.output_height

    @Property(str, notify=encoderInfoChanged)
    def slcStorageHost(self) -> str:
        """UNC root of the shared NAS (SLC_STORAGE_HOST in .env).

        Single source of truth for QML browsers — no hardcoded ``\\\\server``
        literals in the .qml files.
        """
        return self._settings.slc_storage_host

    @Property(int, notify=encoderInfoChanged)
    def segmentDuration(self) -> int:
        return self._settings.segment_duration

    @Property(int, notify=encoderInfoChanged)
    def retentionHours(self) -> int:
        return self._settings.retention_hours

    @Property(int, notify=encoderInfoChanged)
    def eventPreSeconds(self) -> int:
        return self._settings.event_pre_seconds

    @Property(int, notify=encoderInfoChanged)
    def eventPostSeconds(self) -> int:
        return self._settings.event_post_seconds

    @Property(int, notify=encoderInfoChanged)
    def eventCooldownSeconds(self) -> int:
        return self._settings.event_cooldown_seconds

    # ── Encoder / driver (persisted) ──────────────────────────────────

    @Property(int, notify=encoderChanged)
    def driverIndex(self) -> int:
        return _DRIVERS.index(self._driver)

    @Property(str, notify=encoderChanged)
    def codec(self) -> str:
        return self._codec

    @Property(str, notify=restartStateChanged)
    def restartState(self) -> str:
        return self._restart_state

    # ── Role (persisted) ──────────────────────────────────────────────

    @Property(str, notify=roleChanged)
    def role(self) -> str:
        return self._api.role

    @Property(bool, notify=roleChanged)
    def isITUnlocked(self) -> bool:
        return self._api.is_it_unlocked

    # ── System (persisted / registry) ─────────────────────────────────

    @Property(bool, notify=systemChanged)
    def autostart(self) -> bool:
        return autostart.is_autostart_enabled()

    @Property(bool, notify=systemChanged)
    def autorecord(self) -> bool:
        return self._autorecord

    # ── Slots ─────────────────────────────────────────────────────────

    @Slot(str)
    def setClipsDir(self, path: str) -> None:
        if path == self._clips_dir:
            return
        self._api.set_clips_dir(dto.SetClipsDir(path=path))
        self._clips_dir = path
        self.clipsDirChanged.emit()

    @Slot(int)
    def setDriverIndex(self, index: int) -> None:
        if not (0 <= index < len(_DRIVERS)):
            return
        driver = _DRIVERS[index]
        if driver == self._driver:
            return
        self._api.set_driver_index(dto.SetDriverIndex(index=index))
        self._driver = driver
        # Encoder-selector cache is a live recording concern owned by the adapter.
        encoder_selector.set_preferences(driver=driver)
        logger.info("Encoder driver set to '{}' (live recording applies on restart).", driver)
        self.encoderChanged.emit()

    @Slot(str)
    def setCodec(self, codec: str) -> None:
        codec = (codec or "").lower()
        if codec not in ("h264", "hevc") or codec == self._codec:
            return
        self._api.set_codec(dto.SetCodec(codec=codec))
        self._codec = codec
        logger.info("Codec set to '{}' (applies to new recordings/clips).", codec)
        self.encoderChanged.emit()

    @Slot()
    def applyEncoderNow(self) -> None:
        """Restart the live recording with the current driver and codec."""
        if self._restart_cb is None:
            logger.warning("applyEncoderNow: no restart callback registered.")
            return
        if self._restart_state == _RESTART_RUNNING:
            return

        codec  = self._codec
        driver = self._driver

        def _run() -> None:
            self._set_restart_state(_RESTART_RUNNING)
            try:
                self._restart_cb(codec, driver)
                self._set_restart_state(_RESTART_DONE)
                threading.Timer(3.0, lambda: self._set_restart_state(_RESTART_IDLE)).start()
            except Exception:
                logger.exception("applyEncoderNow: restart callback raised.")
                self._set_restart_state(_RESTART_ERROR)
                threading.Timer(4.0, lambda: self._set_restart_state(_RESTART_IDLE)).start()

        threading.Thread(target=_run, daemon=True, name="encoder-restart").start()

    @Slot(bool)
    def setAutostart(self, enabled: bool) -> None:
        autostart.set_autostart(enabled)
        self.systemChanged.emit()

    @Slot(bool)
    def setAutorecord(self, enabled: bool) -> None:
        if enabled == self._autorecord:
            return
        self._autorecord = enabled
        # Facade persists + invokes the live autorecord callback (start/stop).
        self._api.set_autorecord(dto.SetAutorecord(enabled=enabled))
        self.systemChanged.emit()

    # ── Role slots ────────────────────────────────────────────────────

    @Slot(str)
    def setRole(self, role: str) -> None:
        """Persist a role change and relaunch to apply it.

        Delegates authorization (policy + IT unlock), persistence, audit
        (ADR-0011) and the relaunch request to :class:`SettingsApi`.  The bridge
        only refreshes its Qt-facing caches and emits signals if it succeeded.
        """
        prev_role = self._api.role
        applied = self._api.set_role(dto.SetRole(role=(role or "").lower()))
        if not applied or self._api.role == prev_role:
            return
        # Facade already persisted the role's default autorecord; refresh cache.
        self._autorecord = self._port.load().autorecord
        self.roleChanged.emit()
        self.systemChanged.emit()  # autorecord property may have changed

    @Slot(str, result=bool)
    def unlockIT(self, pin: str) -> bool:
        """Validate the IT PIN via the facade (audited). Emits roleChanged on unlock."""
        was_unlocked = self._api.is_it_unlocked
        correct = self._api.unlock_it(dto.UnlockIT(pin=pin))
        if correct and not was_unlocked:
            self.roleChanged.emit()
        return correct

    # ── IT WS hosts (Supervisor config) ──────────────────────────────

    @Property('QVariantList', notify=systemChanged)
    def itWsHosts(self) -> list:
        return list(self._it_ws_hosts)

    @Slot(str)
    def addItWsHost(self, host: str) -> None:
        host = host.strip()
        if not host or host in self._it_ws_hosts:
            return
        self._it_ws_hosts.append(host)
        self._persist(lambda c: setattr(c, "it_ws_hosts", list(self._it_ws_hosts)))
        self.systemChanged.emit()
        self.itWsHostsChanged.emit(list(self._it_ws_hosts))

    @Slot(str)
    def removeItWsHost(self, host: str) -> None:
        if host not in self._it_ws_hosts:
            return
        self._it_ws_hosts.remove(host)
        self._persist(lambda c: setattr(c, "it_ws_hosts", list(self._it_ws_hosts)))
        self.systemChanged.emit()
        self.itWsHostsChanged.emit(list(self._it_ws_hosts))

    @Slot()
    def lockIT(self) -> None:
        """Re-lock IT access for this session."""
        if self._api.is_it_unlocked:
            self._api.lock_it()
            self.roleChanged.emit()

    # ── IT WS port / firewall ─────────────────────────────────────────

    @Property(str, notify=itWsPortStatusChanged)
    def itWsPortStatus(self) -> str:
        return self._it_ws_port_status

    @Property(int, notify=encoderInfoChanged)
    def itWsPort(self) -> int:
        return self._settings.it_ws_port

    @Slot()
    def checkItWsPortStatus(self) -> None:
        """Check whether the Windows Firewall inbound rule for the IT WS port exists."""
        def _run() -> None:
            port = self._settings.it_ws_port
            rule = f"{_FW_RULE_PREFIX}-{port}"
            try:
                result = subprocess.run(
                    ["netsh", "advfirewall", "firewall", "show", "rule", f"name={rule}"],
                    capture_output=True, text=True, timeout=8,
                )
                open_ = result.returncode == 0 and "No rules match" not in result.stdout
                self._it_ws_port_status = "open" if open_ else "closed"
            except Exception:
                self._it_ws_port_status = "unknown"
            self.itWsPortStatusChanged.emit()

        threading.Thread(target=_run, daemon=True, name="fw-check").start()

    @Slot()
    def openItWsPort(self) -> None:
        """Add a Windows Firewall inbound TCP rule for the IT WS port.

        Requires the process to have Administrator privileges.
        Sets itWsPortStatus to 'error' and logs a warning if it fails.
        """
        self._it_ws_port_status = "opening"
        self.itWsPortStatusChanged.emit()

        def _run() -> None:
            port = self._settings.it_ws_port
            rule = f"{_FW_RULE_PREFIX}-{port}"
            try:
                # Remove stale rule first (ignore errors)
                subprocess.run(
                    ["netsh", "advfirewall", "firewall", "delete", "rule", f"name={rule}"],
                    capture_output=True, timeout=8,
                )
                result = subprocess.run(
                    [
                        "netsh", "advfirewall", "firewall", "add", "rule",
                        f"name={rule}",
                        "dir=in", "action=allow", "protocol=TCP",
                        f"localport={port}",
                        "profile=any",
                    ],
                    capture_output=True, text=True, timeout=8,
                )
                if result.returncode == 0:
                    self._it_ws_port_status = "open"
                    logger.info("Firewall rule added for IT WS port {}.", port)
                else:
                    self._it_ws_port_status = "error"
                    logger.warning(
                        "Failed to add firewall rule for port {}: {}",
                        port, result.stderr.strip() or result.stdout.strip(),
                    )
            except Exception:
                self._it_ws_port_status = "error"
                logger.exception("openItWsPort: subprocess error.")
            self.itWsPortStatusChanged.emit()

        threading.Thread(target=_run, daemon=True, name="fw-open").start()

    # ── Helpers ───────────────────────────────────────────────────────

    def _set_restart_state(self, state: str) -> None:
        self._restart_state = state
        self.restartStateChanged.emit()

    def _persist(self, mutate) -> None:
        """Load → mutate → save the user config (single source of truth on disk)."""
        cfg = self._port.load()
        mutate(cfg)
        self._port.save(cfg)
