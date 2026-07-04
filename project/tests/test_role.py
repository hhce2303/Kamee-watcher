"""Tests for the role system — enforce_role(), SettingsBridge PIN validation."""
from __future__ import annotations

from unittest.mock import MagicMock, patch


# ── enforce_role ──────────────────────────────────────────────────────────────

class TestEnforceRole:
    """enforce_role() applies per-role constraints to user_config in-place."""

    def _make_config(self, **kwargs):
        from app.core.ports.user_config_port import UserConfig
        return UserConfig(**kwargs)

    def _fake_autostart(self, enabled_at_start: bool = False):
        m = MagicMock()
        m.is_enabled = enabled_at_start
        return m

    def _fake_task(self, registered: bool = True, raises: bool = False):
        m = MagicMock()
        if raises:
            m.ensure_registered.side_effect = RuntimeError("GPO blocked")
        else:
            m.ensure_registered.return_value = registered
        return m

    def test_operator_forces_autorecord(self):
        from app.core.role import enforce_role
        cfg = self._make_config(autorecord=False, role="operator")
        auto = self._fake_autostart()
        enforce_role("operator", cfg, auto)
        assert cfg.autorecord is True

    def test_operator_registers_task_and_drops_runkey(self):
        # New contract: with a working scheduled-task module, the task becomes
        # the sole launcher and the Run key is removed (set_autostart(False)).
        from app.core.role import enforce_role
        cfg = self._make_config(role="operator")
        auto = self._fake_autostart()
        task = self._fake_task(registered=True)
        status = enforce_role("operator", cfg, auto, task)
        assert status == "task"
        task.ensure_registered.assert_called_once_with()
        auto.set_autostart.assert_called_once_with(False)

    def test_operator_falls_back_to_runkey_when_task_fails(self):
        # Task registration fails (e.g. corporate GPO) → keep the Run key so
        # login autostart still works; report the degraded "runkey" status.
        from app.core.role import enforce_role
        cfg = self._make_config(role="operator")
        auto = self._fake_autostart()
        task = self._fake_task(raises=True)
        status = enforce_role("operator", cfg, auto, task)
        assert status == "runkey"
        auto.set_autostart.assert_called_once_with(True)

    def test_operator_falls_back_to_runkey_without_task_module(self):
        # No scheduled-task module injected → Run-key fallback (legacy contract).
        from app.core.role import enforce_role
        cfg = self._make_config(role="operator")
        auto = self._fake_autostart()
        status = enforce_role("operator", cfg, auto)
        assert status == "runkey"
        auto.set_autostart.assert_called_once_with(True)

    def test_supervisor_forces_autorecord_off(self):
        from app.core.role import enforce_role
        cfg = self._make_config(autorecord=True, role="supervisor")
        auto = self._fake_autostart()
        enforce_role("supervisor", cfg, auto)
        assert cfg.autorecord is False

    def test_supervisor_does_not_touch_autostart(self):
        from app.core.role import enforce_role
        cfg = self._make_config(role="supervisor")
        auto = self._fake_autostart()
        enforce_role("supervisor", cfg, auto)
        auto.set_autostart.assert_not_called()

    def test_it_leaves_autorecord_unchanged(self):
        from app.core.role import enforce_role
        cfg = self._make_config(autorecord=False, role="it")
        auto = self._fake_autostart()
        enforce_role("it", cfg, auto)
        assert cfg.autorecord is False

    def test_it_does_not_touch_autostart(self):
        from app.core.role import enforce_role
        cfg = self._make_config(role="it")
        auto = self._fake_autostart()
        enforce_role("it", cfg, auto)
        auto.set_autostart.assert_not_called()

    def test_empty_role_disables_autorecord(self):
        # Unconfigured machine must never record until the role wizard runs.
        from app.core.role import enforce_role
        cfg = self._make_config(autorecord=True, role="")
        auto = self._fake_autostart()
        enforce_role("", cfg, auto)
        assert cfg.autorecord is False
        auto.set_autostart.assert_not_called()


# ── role helpers ──────────────────────────────────────────────────────────────

class TestRoleHelpers:
    def test_role_label(self):
        from app.core.role import role_label
        assert role_label("operator")  == "Operador"
        assert role_label("supervisor") == "Supervisor"
        assert role_label("it")        == "IT"
        assert "Desconocido" in role_label("unknown")

    def test_role_description_not_empty(self):
        from app.core.role import role_description, VALID_ROLES
        for r in VALID_ROLES:
            assert len(role_description(r)) > 10

    def test_valid_roles_set(self):
        from app.core.role import VALID_ROLES, OPERATOR, SUPERVISOR, IT
        assert OPERATOR in VALID_ROLES
        assert SUPERVISOR in VALID_ROLES
        assert IT in VALID_ROLES
        assert "" not in VALID_ROLES


# ── recording gates ────────────────────────────────────────────────────────────

class TestRecordingGates:
    """Pure helpers that decide whether a machine builds/starts recording."""

    def test_is_recording_role(self):
        from app.core.role import is_recording_role
        assert is_recording_role("operator") is True
        assert is_recording_role("it") is True
        assert is_recording_role("supervisor") is False
        assert is_recording_role("") is False

    def test_default_autorecord_for_role(self):
        from app.core.role import default_autorecord_for_role
        assert default_autorecord_for_role("operator") is True
        assert default_autorecord_for_role("it") is False
        assert default_autorecord_for_role("supervisor") is False
        assert default_autorecord_for_role("") is False

    def test_should_autorecord_operator_always(self):
        from app.core.role import should_autorecord_on_launch
        assert should_autorecord_on_launch("operator", True) is True
        assert should_autorecord_on_launch("operator", False) is True

    def test_should_autorecord_it_honours_toggle(self):
        from app.core.role import should_autorecord_on_launch
        assert should_autorecord_on_launch("it", True) is True
        assert should_autorecord_on_launch("it", False) is False

    def test_should_autorecord_never_for_supervisor_or_unconfigured(self):
        from app.core.role import should_autorecord_on_launch
        assert should_autorecord_on_launch("supervisor", True) is False
        assert should_autorecord_on_launch("", True) is False


# ── SettingsBridge PIN ────────────────────────────────────────────────────────

class TestSettingsBridgePin:
    """SettingsBridge.unlockIT / setRole — delegates to SettingsApi (F1/ADR-0009).

    The role-change/unlock LOGIC now lives in SettingsApi (see
    test_facade_settings.py). These tests verify the bridge's observable Qt
    surface: the ``role``/``isITUnlocked`` properties, the ``unlockIT`` return
    value, and that the injected relaunch/autorecord callbacks fire.
    """

    def _make_bridge(self, role="operator", it_pin="4321"):
        from types import SimpleNamespace
        from app.core.ports.user_config_port import UserConfig
        from app.adapters.ui.settings_bridge import SettingsBridge

        settings = SimpleNamespace(
            it_pin=it_pin,
            clips_dir="/tmp/clips",
            video_codec="h264",
            capture_framerate=30,
            output_width=1920,
            output_height=1080,
            segment_duration=300,
            retention_hours=8,
            event_pre_seconds=120,
            event_post_seconds=120,
            event_cooldown_seconds=30,
            slc_storage_host=r"\\NAS",
            it_ws_port=8765,
        )
        # A real, mutable UserConfig so the facade's load→mutate→save round-trips.
        cfg = UserConfig(role=role)

        class _Port:
            def load(self_inner):
                return cfg

            def save(self_inner, c):
                nonlocal cfg
                cfg = c

        return SettingsBridge(_Port(), settings)

    def test_correct_pin_unlocks(self, qt_app):
        bridge = self._make_bridge(it_pin="4321")
        assert bridge.unlockIT("4321") is True
        assert bridge.isITUnlocked is True

    def test_wrong_pin_does_not_unlock(self, qt_app):
        bridge = self._make_bridge(it_pin="4321")
        assert bridge.unlockIT("0000") is False
        assert bridge.isITUnlocked is False

    def test_set_role_blocked_without_unlock(self, qt_app):
        bridge = self._make_bridge(role="operator")
        bridge.setRole("it")
        assert bridge.role == "operator"   # unchanged — operator cannot self-change

    def test_set_role_allowed_when_unlocked(self, qt_app):
        bridge = self._make_bridge(role="operator", it_pin="4321")
        assert bridge.unlockIT("4321") is True
        bridge.setRole("it")
        assert bridge.role == "it"

    def test_set_role_allowed_for_first_run(self, qt_app):
        bridge = self._make_bridge(role="")
        bridge.setRole("supervisor")
        assert bridge.role == "supervisor"

    def test_set_role_rejects_invalid(self, qt_app):
        bridge = self._make_bridge(role="it")
        bridge.setRole("admin")
        assert bridge.role == "it"

    def test_set_role_initializes_autorecord_default(self, qt_app):
        # First-run IT → autorecord off (opt-in); first-run operator → on.
        for role, expected in (("it", False), ("operator", True), ("supervisor", False)):
            bridge = self._make_bridge(role="")
            bridge.setRole(role)
            assert bridge.role == role
            assert bridge.autorecord is expected

    def test_set_role_triggers_relaunch(self, qt_app):
        bridge = self._make_bridge(role="")
        relaunch = MagicMock()
        bridge.set_relaunch_callback(relaunch)
        bridge.setRole("operator")
        relaunch.assert_called_once_with()

    def test_set_role_no_relaunch_when_unchanged(self, qt_app):
        bridge = self._make_bridge(role="operator")
        relaunch = MagicMock()
        bridge.set_relaunch_callback(relaunch)
        bridge.setRole("operator")
        relaunch.assert_not_called()

    def test_set_autorecord_invokes_callback(self, qt_app):
        bridge = self._make_bridge(role="it")  # UserConfig default autorecord=True
        cb = MagicMock()
        bridge.set_autorecord_callback(cb)
        bridge.setAutorecord(False)  # toggle off → live stop callback fires
        assert bridge.autorecord is False
        cb.assert_called_once_with(False)
