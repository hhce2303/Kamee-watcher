"""SqliteEventStoreAdapter as AuditPort — sensitive commands persist (ADR-0011)."""
from __future__ import annotations

from datetime import datetime, timezone

from app.adapters.storage.sqlite_event_store import SqliteEventStoreAdapter
from app.core.ports.audit_port import AuditPort


def test_store_implements_audit_port() -> None:
    store = SqliteEventStoreAdapter(":memory:")
    assert isinstance(store, AuditPort)


def test_audit_records_origin_and_timestamp() -> None:
    store = SqliteEventStoreAdapter(":memory:")
    ts = datetime(2026, 7, 2, 10, 30, tzinfo=timezone.utc)
    store.record("stopRecording", "ipc:pid=1234", ts, detail="", success=True)
    store.record("unlockIT", "ui", ts, detail="", success=False)

    rows = store.audit_entries()
    assert len(rows) == 2
    stop = store.audit_entries("stopRecording")
    assert len(stop) == 1
    assert stop[0]["origin"] == "ipc:pid=1234"
    assert stop[0]["success"] is True
    assert abs(stop[0]["ts"] - ts.timestamp()) < 1e-6

    unlock = store.audit_entries("unlockIT")
    assert unlock[0]["success"] is False
    store.close()


def test_audit_survives_reopen(tmp_path) -> None:
    db = tmp_path / "events.db"
    store = SqliteEventStoreAdapter(db)
    store.record("setRole", "ui", datetime.now(tz=timezone.utc), detail="it→operator")
    store.close()

    reopened = SqliteEventStoreAdapter(db)
    rows = reopened.audit_entries("setRole")
    assert len(rows) == 1
    assert rows[0]["detail"] == "it→operator"
    reopened.close()
