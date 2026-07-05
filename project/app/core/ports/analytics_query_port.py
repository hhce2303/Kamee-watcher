"""Port: analytics queries over the event store (Fase 4).

Read-only view of aggregated detection data: counts per class, dwell times
per track, events filtered by zone.  Implementations query the existing SQLite
event store — no new database schema required.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel

from app.core.analytics.models import AnalyticEvent


class CountByClass(BaseModel):
    """Aggregate detection count for one object class in a time window."""

    class_name: str
    count: int


class DwellRecord(BaseModel):
    """Total on-screen time for one track in a time window."""

    track_id: int
    class_name: str
    total_seconds: float
    first_seen: datetime
    last_seen: datetime


class AnalyticsQueryPort(ABC):
    """Read-only analytics queries over the persisted event store."""

    @abstractmethod
    def count_by_class(
        self,
        since: datetime,
        until: datetime,
        monitor_index: Optional[int] = None,
    ) -> List[CountByClass]:
        """Return per-class event counts in *[since, until]*."""

    @abstractmethod
    def dwell_by_track(
        self,
        since: datetime,
        until: datetime,
        monitor_index: Optional[int] = None,
    ) -> List[DwellRecord]:
        """Return cumulative dwell time per track_id in *[since, until]*."""

    @abstractmethod
    def events_in_zone(
        self,
        zone_name: str,
        since: datetime,
        until: datetime,
    ) -> List[AnalyticEvent]:
        """Return all events whose *zone* field equals *zone_name*."""
