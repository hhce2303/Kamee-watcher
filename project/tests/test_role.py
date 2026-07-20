"""Tests for the role system — enforce_role(), SettingsBridge PIN validation."""
from __future__ import annotations

from unittest.mock import MagicMock


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
        auto.set_autostart.assert_called_once_with(True, launch_args=["--daemon"])

    def test_operator_falls_back_to_runkey_without_task_module(self):
        # No scheduled-task module injected → Run-key fallback (legacy contract).
        from app.core.role import enforce_role
        cfg = self._make_config(role="operator")
        auto = self._fake_autostart()
        status = enforce_role("operator", cfg, auto)
        assert status == "runkey"
        auto.set_autostart.assert_called_once_with(True, launch_args=["--daemon"])

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

