"""SQLite implementation of :class:`EventStorePort` (Fase 1, R-AI).

Stores each :class:`AnalyticEvent` as its canonical JSON payload (source of
truth) plus indexed columns for time/monitor/type filtering.  The editor queries
this store to paint timeline markers.

Thread-safe: a single connection (``check_same_thread=False``) guarded by a lock,
which is sufficient for the app's low event rate.
"""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from loguru import logger

from app.core.analytics.models import AnalyticEvent
from app.core.ports.audit_port import AuditPort
from app.core.ports.event_store_port import EventStorePort

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    event_id      TEXT PRIMARY KEY,
    type          TEXT NOT NULL,
    source        TEXT NOT NULL,
    start_ts      REAL NOT NULL,
    end_ts        REAL NOT NULL,
    monitor_index INTEGER,
    payload_json  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_start ON events(start_ts);

-- Audit trail for security-sensitive commands (ADR-0011): start/stop/unlock/setRole.
CREATE TABLE IF NOT EXISTS audit_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        REAL NOT NULL,
    command   TEXT NOT NULL,
    origin    TEXT NOT NULL,
    detail    TEXT NOT NULL DEFAULT '',
    success   INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(ts);
"""


class SqliteEventStoreAdapter(EventStorePort, AuditPort):
    """Persist/query analytic events and the security audit log in SQLite."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = Path(db_path)
        if self._db_path.parent and str(self._db_path) != ":memory:":
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._conn:
            self._conn.executescript(_SCHEMA)
        logger.info("[eventstore] SQLite ready at {}", self._db_path)

    def add(self, event: AnalyticEvent) -> None:
        row = (
            event.event_id,
            event.type,
            event.source,
            event.start.timestamp(),
            event.end.timestamp(),
            event.monitor_index,
            event.model_dump_json(),
        )
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO events "
                "(event_id, type, source, start_ts, end_ts, monitor_index, payload_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                row,
            )

    def query(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        monitor_index: Optional[int] = None,
        type: Optional[str] = None,
    ) -> List[AnalyticEvent]:
        clauses: list[str] = []
        params: list[object] = []
        # Overlap test: event_start <= window_end AND event_end >= window_start.
        if end is not None:
            clauses.append("start_ts <= ?")
            params.append(end.timestamp())
        if start is not None:
            clauses.append("end_ts >= ?")
            params.append(start.timestamp())
        if monitor_index is not None:
            clauses.append("monitor_index = ?")
            params.append(monitor_index)
        if type is not None:
            clauses.append("type = ?")
            params.append(type)

        sql = "SELECT payload_json FROM events"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY start_ts DESC"

        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [AnalyticEvent.model_validate_json(r["payload_json"]) for r in rows]

    def get(self, event_id: str) -> Optional[AnalyticEvent]:
        with self._lock:
            row = self._conn.execute(
                "SELECT payload_json FROM events WHERE event_id = ?", (event_id,)
            ).fetchone()
        if row is None:
            return None
        return AnalyticEvent.model_validate_json(row["payload_json"])

    # ── AuditPort ─────────────────────────────────────────────────────

    def record(
        self,
        command: str,
        origin: str,
        timestamp: datetime,
        detail: str = "",
        success: bool = True,
    ) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO audit_log (ts, command, origin, detail, success) "
                "VALUES (?, ?, ?, ?, ?)",
                (timestamp.timestamp(), command, origin, detail, 1 if success else 0),
            )

    def audit_entries(self, command: Optional[str] = None) -> List[dict]:
        """Return audit rows newest-first (optionally filtered by command)."""
        sql = "SELECT ts, command, origin, detail, success FROM audit_log"
        params: list[object] = []
        if command is not None:
            sql += " WHERE command = ?"
            params.append(command)
        sql += " ORDER BY ts DESC"
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [
            {
                "ts": r["ts"],
                "command": r["command"],
                "origin": r["origin"],
                "detail": r["detail"],
                "success": bool(r["success"]),
            }
            for r in rows
        ]

    def close(self) -> None:
        with self._lock:
            self._conn.close()
