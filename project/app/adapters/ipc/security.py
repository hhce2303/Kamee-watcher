"""Named-pipe security — restrict the pipe to the current user (ADR-0011).

The IPC channel is not a strong security boundary; it relies on OS user
isolation.  The goal is to close trivial access by *any* local process: the pipe
is created with a security descriptor granting full access only to the current
user's SID (plus SYSTEM), so a process running as a different user cannot open
it.  ``stopRecording`` from an unauthorized client is rejected by the OS at open
time — that is the ADR-0011 acceptance criterion.

pywin32 is imported lazily so this module (and its SDDL builder) import even
where pywin32 is absent; only :func:`make_security_attributes` requires it.
"""
from __future__ import annotations


def current_user_sid_string() -> str:
    """Return the current process user's SID as a string (e.g. ``S-1-5-21-...``)."""
    import win32security  # noqa: PLC0415
    import win32process   # noqa: PLC0415

    token = win32security.OpenProcessToken(
        win32process.GetCurrentProcess(), win32security.TOKEN_QUERY
    )
    sid, _attrs = win32security.GetTokenInformation(token, win32security.TokenUser)
    return win32security.ConvertSidToStringSid(sid)


def user_scoped_sddl(sid_string: str) -> str:
    """Build an SDDL granting full access to *sid_string* and SYSTEM only.

    ``D:`` = DACL; ``(A;;GA;;;<sid>)`` = Allow, Generic All, to the SID; plus
    ``SY`` (Local System).  Everyone else is denied by omission (no other ACE).
    """
    return f"D:(A;;GA;;;{sid_string})(A;;GA;;;SY)"


def make_security_attributes():
    """Build a pywin32 SECURITY_ATTRIBUTES with the user-scoped descriptor."""
    import win32security  # noqa: PLC0415

    sddl = user_scoped_sddl(current_user_sid_string())
    sd = win32security.ConvertStringSecurityDescriptorToSecurityDescriptor(
        sddl, win32security.SDDL_REVISION_1
    )
    sa = win32security.SECURITY_ATTRIBUTES()
    sa.SECURITY_DESCRIPTOR = sd
    sa.bInheritHandle = False
    return sa


def default_pipe_name() -> str:
    r"""Per-user pipe name: ``\\.\pipe\TheWatcher.<user>`` (scoped by name too)."""
    import getpass  # noqa: PLC0415

    try:
        user = getpass.getuser()
    except Exception:  # noqa: BLE001
        user = "default"
    return rf"\\.\pipe\TheWatcher.{user}"
