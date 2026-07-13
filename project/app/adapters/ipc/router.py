"""IpcRouter — dispatch command frames to the core/api facades (ADR-0009/0011).

Transport-agnostic: it takes a decoded request envelope and returns a response
envelope, so it is fully unit-testable without a real pipe.  Audited commands
(start/stop/unlock/setRole) are constructed with ``origin="ipc"`` — a client
cannot spoof ``"ui"`` — and the facades' AuditPort records them automatically.
"""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict

from loguru import logger
from pydantic import BaseModel

from app.core.api import dto
from app.core.api.bootstrap import ApiLayer


def _ser(obj: Any) -> Any:
    """Best-effort JSON-ready serialization of a facade return value."""
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    if isinstance(obj, (list, tuple)):
        return [_ser(x) for x in obj]
    if is_dataclass(obj) and not isinstance(obj, type):
        return {k: _ser(v) for k, v in asdict(obj).items()}
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    return obj


class IpcRouter:
    """Maps command names to facade calls over an :class:`ApiLayer`."""

    def __init__(self, api: ApiLayer, origin: str = "ipc") -> None:
        self._api = api
        self._origin = origin
        self._handlers: Dict[str, Callable[[dict], Any]] = self._build_handlers()

    @property
    def commands(self) -> list[str]:
        return sorted(self._handlers)

    def handle(self, request: dict) -> dict:
        """Dispatch a request envelope; always returns a response envelope."""
        req_id = request.get("id", "")
        cmd = request.get("cmd", "")
        payload = request.get("payload") or {}
        handler = self._handlers.get(cmd)
        if handler is None:
            return {"id": req_id, "ok": False, "error": f"unknown command: {cmd}"}
        try:
            result = handler(payload)
            return {"id": req_id, "ok": True, "result": _ser(result)}
        except Exception as exc:  # noqa: BLE001 — never let one bad frame kill the loop
            logger.exception("[ipc] command '{}' failed", cmd)
            return {"id": req_id, "ok": False, "error": f"{type(exc).__name__}: {exc}"}

    # ── Handler registry ──────────────────────────────────────────────

    @staticmethod
    def _parse_dt(value: str) -> datetime:
        """Parse an ISO-8601 string (including JS Date.toISOString() 'Z' suffix)."""
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)

    def _build_handlers(self) -> Dict[str, Callable[[dict], Any]]:
        r = self._api.recording
        s = self._api.settings
        e = self._api.editor
        c = self._api.clips
        q = self._api.requests
        d = self._api.delivery
        a = self._api.analytics
        o = self._origin

        return {
            # ── Recording (audited: start/stop) ──
            "get_recording_state": lambda p: r.get_recording_state(),
            "get_monitors":        lambda p: r.get_monitors(),
            "get_preview_server_info": lambda p: r.get_preview_server_info(),
            "trigger_event":       lambda p: {"accepted": r.trigger_event(dto.TriggerEvent(origin=o))},
            "start_recording":     lambda p: r.start_recording(dto.StartRecording(origin=o)),
            "stop_recording":      lambda p: r.stop_recording(dto.StopRecording(origin=o)),
            "toggle_monitor":      lambda p: r.toggle_monitor(dto.ToggleMonitor(fingerprint=p["fingerprint"])),
            # ── Settings (audited: set_role/unlock_it) ──
            "get_settings":        lambda p: s.get_settings(),
            "get_media_roots":     lambda p: s.get_media_roots(),
            "set_clips_dir":       lambda p: s.set_clips_dir(dto.SetClipsDir(path=p["path"])),
            "set_driver_index":    lambda p: s.set_driver_index(dto.SetDriverIndex(index=p["index"])),
            "set_codec":           lambda p: s.set_codec(dto.SetCodec(codec=p["codec"])),
            "set_autorecord":      lambda p: s.set_autorecord(dto.SetAutorecord(enabled=p["enabled"])),
            "set_autostart":       lambda p: s.set_autostart(dto.SetAutostart(enabled=p["enabled"])),
            "apply_encoder_now":   lambda p: s.apply_encoder_now(),
            "set_role":            lambda p: {"applied": s.set_role(dto.SetRole(role=p["role"], origin=o))},
            "unlock_it":           lambda p: {"ok": s.unlock_it(dto.UnlockIT(pin=p["pin"], origin=o))},
            # ── Editor ──
            "add_clip":            lambda p: e.add_clip(dto.AddClip(**p)),
            "add_clip_trimmed":    lambda p: e.add_clip_trimmed(dto.AddClipTrimmed(**p)),
            "add_files_from_urls": lambda p: e.add_files_from_urls(dto.AddFilesFromUrls(urls=p.get("urls", []))),
            "remove_clip":         lambda p: e.remove_clip(p["index"]),
            "move_clip":           lambda p: e.move_clip(p["src"], p["dst"]),
            "set_trim":            lambda p: e.set_trim(p["index"], p["in_point_s"], p["out_point_s"]),
            "clear_timeline":      lambda p: e.clear(),
            "export_timeline":     lambda p: e.export_timeline(dto.ExportTimeline(output_path=p["output_path"])),
            "editor_clip_count":   lambda p: {"count": e.clip_count()},
            "get_timeline":        lambda p: e.get_timeline(),
            # ── Clips / browsing ──
            "list_clips":          lambda p: c.list_clips(),
            "load_clip":           lambda p: c.load_clip(dto.LoadClip(path=p["path"])),
            "list_directory":      lambda p: c.list_directory(dto.ListDirectory(path=p["path"])),
            "transcode_clip":      lambda p: c.transcode_clip(dto.TranscodeClip(path=p["path"])),
            # ── Requests ──
            "list_storages":       lambda p: q.list_storages(),
            "list_operators":      lambda p: q.list_operators(p["storage_path"]),
            "list_all_operators":  lambda p: q.list_all_operators(),
            "send_clip_request":   lambda p: {"ok": q.send_clip_request(dto.SendClipRequest(request_json=p["request_json"]))},
            "inbox_requests":      lambda p: q.inbox_requests(),
            "my_requests":         lambda p: q.my_requests(),
            "update_request_status": lambda p: q.update_request_status(
                dto.UpdateRequestStatus(request_id=p["request_id"], status=p["status"])
            ),
            # ── Delivery ──
            "compute_folder_path": lambda p: {"path": d.compute_folder_path()},
            "ensure_folder_and_link": lambda p: d.ensure_folder_and_link(p.get("folder_path", "")),
            "reset_onedrive":      lambda p: d.reset_onedrive(),
            "save_reel_privately": lambda p: d.save_reel_privately(p.get("folder_path", "")),
            # ── Analytics (F5) — read-only queries over the event store ──
            "analytics_counts": lambda p: (
                a.count_by_class(
                    since=self._parse_dt(p["since"]),
                    until=self._parse_dt(p["until"]),
                    monitor_index=p.get("monitor_index"),
                ) if a is not None else []
            ),
            "analytics_dwell": lambda p: (
                a.dwell_by_track(
                    since=self._parse_dt(p["since"]),
                    until=self._parse_dt(p["until"]),
                    monitor_index=p.get("monitor_index"),
                ) if a is not None else []
            ),
            "analytics_zone_events": lambda p: (
                a.events_in_zone(
                    zone_name=p["zone_name"],
                    since=self._parse_dt(p["since"]),
                    until=self._parse_dt(p["until"]),
                ) if a is not None else []
            ),
        }
