"""runtime — role-conditional startup topology (ADR-0010).

One entrypoint, two headless modes plus the existing QML mode:

* ``--daemon`` (Operator): headless, no Qt; launched by the scheduled-task
  watchdog; survives the client window closing.
* ``--sidecar`` (IT/Supervisor): headless, launched by the Tauri process; exits
  cleanly on a stdin shutdown command (TD-3 — ``process.kill()`` cannot reach the
  Python process behind the PyInstaller bootloader, so we shut down via stdin).
* no flag: the current QML path (unchanged in F1).
"""
from __future__ import annotations

from app.runtime.mode import DAEMON, QML, SIDECAR, resolve_mode

__all__ = ["resolve_mode", "DAEMON", "SIDECAR", "QML"]
