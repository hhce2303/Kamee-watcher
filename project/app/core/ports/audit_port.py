"""AuditPort — record sensitive commands with origin + timestamp (ADR-0011).

`startRecording` / `stopRecording` / `unlockIT` / `setRole` must be auditable: who
issued them, from where, and when.  The facade calls :meth:`AuditPort.record`
before executing an audited command; the storage adapter persists it to the event
store.  Keeping this a port means ``core/api`` never touches SQLite directly.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime


class AuditPort(ABC):
    """Append-only audit log for security-sensitive commands."""

    @abstractmethod
    def record(
        self,
        command: str,
        origin: str,
        timestamp: datetime,
        detail: str = "",
        success: bool = True,
    ) -> None:
        """Append one audit entry.

        Args:
            command: the command name, e.g. ``"stopRecording"``.
            origin: who issued it, e.g. ``"ui"`` or ``"ipc:pid=1234"``.
            timestamp: when it was issued (timezone-aware UTC).
            detail: optional free-form context (e.g. the target role).
            success: whether the command was authorised/accepted.
        """
        raise NotImplementedError
