"""IPC named-pipe security — user-scoped SDDL (ADR-0011)."""
from __future__ import annotations

import pytest

from app.adapters.ipc import security


def test_user_scoped_sddl_grants_only_user_and_system() -> None:
    sddl = security.user_scoped_sddl("S-1-5-21-1-2-3-1001")
    assert sddl == "D:(A;;GA;;;S-1-5-21-1-2-3-1001)(A;;GA;;;SY)"
    # Exactly two ACEs — the user and SYSTEM; no "everyone" (WD) ACE.
    assert sddl.count("(A;;GA;;;") == 2
    assert ";;;WD)" not in sddl and ";;;AU)" not in sddl


def test_default_pipe_name_is_per_user() -> None:
    name = security.default_pipe_name()
    assert name.startswith(r"\\.\pipe\TheWatcher.")


pywin32 = pytest.importorskip("win32security")


def test_current_user_sid_is_a_real_sid() -> None:
    sid = security.current_user_sid_string()
    assert sid.startswith("S-1-")


def test_make_security_attributes_builds_descriptor() -> None:
    sa = security.make_security_attributes()
    assert sa.SECURITY_DESCRIPTOR is not None
