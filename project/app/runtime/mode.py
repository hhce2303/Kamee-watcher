"""Startup mode resolution from the command line (ADR-0010)."""
from __future__ import annotations

from typing import Sequence

DAEMON = "daemon"
SIDECAR = "sidecar"
QML = "qml"


def resolve_mode(argv: Sequence[str]) -> str:
    """Pick the startup mode from argv.

    ``--daemon`` → daemon (Operator, headless).  ``--sidecar`` → sidecar
    (IT/Supervisor, headless, stdin shutdown).  Neither → the QML path.  If both
    are present, ``--daemon`` wins (an operator box is always the daemon).
    """
    args = set(argv or [])
    if "--daemon" in args:
        return DAEMON
    if "--sidecar" in args:
        return SIDECAR
    return QML
