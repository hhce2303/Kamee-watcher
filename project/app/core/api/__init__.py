"""core/api — the input port of the hexagon (Fase 1, ADR-0009).

The facade layer that QML and ``adapters/ipc`` both drive. It knows **no Qt, no
WebSocket, no JSON** — facades accept command DTOs, call the existing core
services/ports, return DTOs, and publish typed events on a thread-safe
:class:`EventBus`.  Serialization lives only in ``adapters/ipc``.

Public surface::

    from app.core.api import EventBus, RecordingApi, SettingsApi, EditorApi
    from app.core.api import dto
"""
from __future__ import annotations

from app.core.api.editor_api import EditorApi
from app.core.api.events import EventBus, Subscription
from app.core.api.recording_api import RecordingApi
from app.core.api.settings_api import SettingsApi

__all__ = [
    "EventBus",
    "Subscription",
    "RecordingApi",
    "SettingsApi",
    "EditorApi",
]
