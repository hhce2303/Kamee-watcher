"""runtime — role-conditional startup topology (ADR-0010).

One entrypoint, two headless modes (QML is gone — F3):

* ``--daemon`` (Operator): headless, launched by the scheduled-task watchdog;
  survives the Tauri client window closing.
* ``--sidecar`` (IT/Supervisor/unconfigured): headless, launched by the Tauri
  process; exits cleanly on a stdin shutdown command (TD-3 —
  ``process.kill()`` cannot reach the Python process behind the PyInstaller
  bootloader, so we shut down via stdin).
"""
from __future__ import annotations

from app.runtime.mode import DAEMON, SIDECAR, resolve_mode

__all__ = ["resolve_mode", "DAEMON", "SIDECAR"]
