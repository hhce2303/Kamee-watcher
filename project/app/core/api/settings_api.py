"""SettingsApi — facade over persisted config + role management (ADR-0009).

Unifies ``settings_bridge``'s command surface without Qt.  Role changes and IT
unlock are security-sensitive → audited (ADR-0011).  The process-level side
effects that used to be Qt callbacks (relaunch on role change, live autorecord
toggle, encoder restart) are injected as plain callables so this facade stays
transport-agnostic.
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from loguru import logger

from app.core.api import dto
from app.core.api.events import EventBus
from app.core.ports.audit_port import AuditPort
from app.core.ports.user_config_port import UserConfigPort
from app.core.policy import policy_for
from app.core.role import VALID_ROLES, default_autorecord_for_role
from app.infrastructure import autostart

_DRIVERS = ["auto", "nvidia", "intel", "amd", "cpu"]


class SettingsApi:
    """Command surface for encoder, system, and role settings."""

    def __init__(
        self,
        *,
        event_bus: EventBus,
        user_config_port: UserConfigPort,
        settings,
        audit_port: Optional[AuditPort] = None,
        relaunch_cb: Optional[Callable[[], None]] = None,
        autorecord_cb: Optional[Callable[[bool], None]] = None,
    ) -> None:
        self._bus = event_bus
        self._port = user_config_port
        self._settings = settings
        self._audit = audit_port
        self._relaunch_cb = relaunch_cb
        self._autorecord_cb = autorecord_cb
        self._restart_encoder_cb: Optional[Callable[[str, str], None]] = None
        self._restarting_encoder = False

        cfg = self._port.load()
        self._role: str = cfg.role
        self._it_unlocked: bool = False

    def set_relaunch_cb(self, cb: Optional[Callable[[], None]]) -> None:
        """Register the process-relaunch callback (main.py wires it post-build)."""
        self._relaunch_cb = cb

    def set_autorecord_cb(self, cb: Optional[Callable[[bool], None]]) -> None:
        """Register the live autorecord start/stop callback (main.py wires it)."""
        self._autorecord_cb = cb

    def set_restart_encoder_cb(self, cb: Optional[Callable[[str, str], None]]) -> None:
        """Register the live encoder-restart callback: ``cb(codec, driver)``.

        Called from a background thread — must not touch Qt directly.
        """
        self._restart_encoder_cb = cb

    # ── Audit helper ──────────────────────────────────────────────────

    def _audit_cmd(self, command: str, origin: str, detail: str = "", success: bool = True) -> None:
        if self._audit is None:
            return
        try:
            self._audit.record(command, origin, datetime.now(tz=timezone.utc), detail, success)
        except Exception:  # noqa: BLE001
            logger.exception("[settings-api] audit record failed for {}", command)

    # ── Queries ───────────────────────────────────────────────────────

    @property
    def role(self) -> str:
        return self._role

    @property
    def is_it_unlocked(self) -> bool:
        return self._it_unlocked

    def get_settings(self) -> dto.SettingsSnapshot:
        """Full settings/role snapshot for the UI shell on connect."""
        cfg = self._port.load()
        return dto.SettingsSnapshot(
            role=self._role,
            clips_dir=cfg.clips_dir or str(self._settings.clips_dir),
            codec=cfg.codec or self._settings.video_codec,
            driver=cfg.driver,
            autorecord=cfg.autorecord,
            autostart=autostart.is_autostart_enabled(),
            it_unlocked=self._it_unlocked,
        )

    def get_media_roots(self) -> dto.MediaRoots:
        """Filesystem roots the UI's custom media protocol may serve from."""
        return dto.MediaRoots(
            segments_dir=str(self._settings.segment_dir),
            clips_dir=str(self._settings.clips_dir),
            storage_roots=[self._settings.slc_storage_host] if self._settings.slc_storage_host else [],
        )

    # ── Encoder / system commands ─────────────────────────────────────

    def set_clips_dir(self, cmd: dto.SetClipsDir) -> None:
        Path(cmd.path).mkdir(parents=True, exist_ok=True)
        self._persist(lambda c: setattr(c, "clips_dir", cmd.path))

    def set_driver_index(self, cmd: dto.SetDriverIndex) -> None:
        if not (0 <= cmd.index < len(_DRIVERS)):
            return
        self._persist(lambda c: setattr(c, "driver", _DRIVERS[cmd.index]))

    def set_codec(self, cmd: dto.SetCodec) -> None:
        codec = (cmd.codec or "").lower()
        if codec not in ("h264", "hevc"):
            return
        self._persist(lambda c: setattr(c, "codec", codec))

    def set_autorecord(self, cmd: dto.SetAutorecord) -> None:
        self._persist(lambda c: setattr(c, "autorecord", cmd.enabled))
        if self._autorecord_cb is not None:
            self._autorecord_cb(cmd.enabled)

    def set_autostart(self, cmd: dto.SetAutostart) -> None:
        autostart.set_autostart(cmd.enabled)

    def apply_encoder_now(self) -> None:
        """Restart the live recording with the currently persisted codec/driver."""
        if self._restart_encoder_cb is None:
            logger.warning("[settings-api] applyEncoderNow: no restart callback registered.")
            self._bus.publish(dto.EncoderRestartFailed(message="No hay callback de reinicio configurado."))
            return
        if self._restarting_encoder:
            return
        cfg = self._port.load()
        codec = cfg.codec or self._settings.video_codec
        driver = cfg.driver
        self._restarting_encoder = True
        self._bus.publish(dto.EncoderRestartStarted())
        self._run_restart_async(codec, driver)

    def _run_restart_async(self, codec: str, driver: str) -> None:
        """Overridable in tests so the restart can run inline for determinism."""
        threading.Thread(
            target=self._do_restart_encoder, args=(codec, driver), daemon=True, name="encoder-restart"
        ).start()

    def _do_restart_encoder(self, codec: str, driver: str) -> None:
        try:
            self._restart_encoder_cb(codec, driver)
            self._bus.publish(dto.EncoderRestartFinished())
        except Exception as exc:  # noqa: BLE001
            logger.exception("[settings-api] applyEncoderNow: restart callback raised.")
            self._bus.publish(dto.EncoderRestartFailed(message=str(exc)))
        finally:
            self._restarting_encoder = False

    # ── Role commands (audited) ───────────────────────────────────────

    def set_role(self, cmd: dto.SetRole) -> bool:
        """Persist a role change and request a relaunch. Returns True if applied."""
        role = (cmd.role or "").lower()
        if role not in VALID_ROLES:
            logger.warning("[settings-api] setRole: invalid role '{}'.", role)
            self._audit_cmd("setRole", cmd.origin, detail=f"invalid:{role}", success=False)
            return False
        authorised = policy_for(self._role).can_change_role or self._it_unlocked
        if not authorised:
            logger.warning("[settings-api] setRole: not authorised (role={}).", self._role)
            self._audit_cmd("setRole", cmd.origin, detail=f"unauthorised→{role}", success=False)
            return False
        if role == self._role:
            return True

        self._audit_cmd("setRole", cmd.origin, detail=f"{self._role}→{role}", success=True)
        self._role = role
        autorecord = default_autorecord_for_role(role)

        def _mutate(c) -> None:
            c.role = role
            c.autorecord = autorecord

        self._persist(_mutate)
        self._bus.publish(dto.RoleChanged(role=role, it_unlocked=self._it_unlocked))
        if self._relaunch_cb is not None:
            self._relaunch_cb()
        else:
            logger.warning("[settings-api] setRole: no relaunch callback — backend not re-wired.")
        return True

    def unlock_it(self, cmd: dto.UnlockIT) -> bool:
        correct = cmd.pin == self._settings.it_pin
        self._audit_cmd("unlockIT", cmd.origin, success=correct)
        if correct and not self._it_unlocked:
            self._it_unlocked = True
            self._bus.publish(dto.RoleChanged(role=self._role, it_unlocked=True))
        elif not correct:
            logger.warning("[settings-api] unlockIT: wrong PIN attempt.")
        return correct

    def lock_it(self) -> None:
        if self._it_unlocked:
            self._it_unlocked = False
            self._bus.publish(dto.RoleChanged(role=self._role, it_unlocked=False))

    # ── Internal ──────────────────────────────────────────────────────

    def _persist(self, mutate: Callable[[object], None]) -> None:
        cfg = self._port.load()
        mutate(cfg)
        self._port.save(cfg)
