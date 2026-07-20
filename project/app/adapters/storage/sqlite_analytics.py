"""SQLite analytics query adapter (Fase 4): counts, dwell times, zone events.

Read-only — queries the event store populated by :class:`SqliteEventStoreAdapter`.
All heavy lifting (time-range filtering, monitor filtering) is delegated to
the existing :meth:`SqliteEventStoreAdapter.query` method; aggregation is done
in Python because the event rate is low (< 1000s events per day in practice).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional

from app.adapters.storage.sqlite_event_store import SqliteEventStoreAdapter
from app.core.analytics.models import AnalyticEvent
from app.core.ports.analytics_query_port import (
    AnalyticsQueryPort,
    CountByClass,
    DwellRecord,
)


class SqliteAnalyticsAdapter(AnalyticsQueryPort):
    """Analytics queries backed by the existing :class:`SqliteEventStoreAdapter`.

    Reuses the store's connection + lock — no second SQLite connection needed.
    """

    def __init__(self, event_store: SqliteEventStoreAdapter) -> None:
        self._store = event_store

    # ── AnalyticsQueryPort ───────────────────────────────────────────────────

    def count_by_class(
        self,
        since: datetime,
        until: datetime,
        monitor_index: Optional[int] = None,
    ) -> List[CountByClass]:
        events = self._store.query(
            start=since, end=until, monitor_index=monitor_index
        )
        counts: Dict[str, int] = defaultdict(int)
        for ev in events:
            counts[ev.type] += 1
        return [
            CountByClass(class_name=k, count=v)
            for k, v in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        ]

    def dwell_by_track(
        self,
        since: datetime,
        until: datetime,
        monitor_index: Optional[int] = None,
    ) -> List[DwellRecord]:
        events = self._store.query(
            start=since, end=until, monitor_index=monitor_index
        )
        dwell: Dict[int, dict] = {}
        for ev in events:
            if ev.track_id is None:
                continue
            tid = ev.track_id
            if tid not in dwell:
                dwell[tid] = {
                    "class_name": ev.type,
                    "total": ev.duration_seconds,
                    "first": ev.start,
                    "last": ev.end,
                }
            else:
                d = dwell[tid]
                d["total"] += ev.duration_seconds
                if ev.start < d["first"]:
                    d["first"] = ev.start
                if ev.end > d["last"]:
                    d["last"] = ev.end
        return [
            DwellRecord(
                track_id=tid,
                class_name=d["class_name"],
                total_seconds=d["total"],
                first_seen=d["first"],
                last_seen=d["last"],
            )
            for tid, d in sorted(dwell.items())
        ]

    def events_in_zone(
        self,
        zone_name: str,
        since: datetime,
        until: datetime,
    ) -> List[AnalyticEvent]:
        events = self._store.query(start=since, end=until)
        return [ev for ev in events if ev.zone == zone_name]
