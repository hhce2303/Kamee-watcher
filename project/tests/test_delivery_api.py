"""DeliveryApi facade — folder derivation + share-link flow + OneDriveChanged."""
from __future__ import annotations

import pytest

from app.core.api import dto
from app.core.api.delivery_api import DeliveryApi
from app.core.api.events import EventBus
from app.adapters.cloud.local_share_adapter import LocalShareAdapter
from app.core.cloud_share_service import CloudShareService


class FakeRequestPort:
    def __init__(self, requests=None):
        self._all = requests or []

    def save(self, req):
        self._all.append(req)

    def load_all(self):
        return list(self._all)

    def update_status(self, req_id, status):
        pass


def _svc(tmp_path):
    return CloudShareService(LocalShareAdapter(root=tmp_path / "od"))


def test_success_publishes_linked_and_creates_folder(tmp_path) -> None:
    bus = EventBus()
    api = DeliveryApi(event_bus=bus, cloud_share_service=_svc(tmp_path))
    events = []
    bus.subscribe(dto.OneDriveChanged, events.append)

    result = api.ensure_folder_and_link("SLC/clips-supervisor/2026-07")
    bus.drain()

    assert result.folder_path == "SLC/clips-supervisor/2026-07"
    assert result.share_link.startswith("file:")
    assert (tmp_path / "od" / "SLC" / "clips-supervisor" / "2026-07").is_dir()
    assert events and events[0].state == "linked"


def test_empty_path_derived_from_config(tmp_path) -> None:
    api = DeliveryApi(
        event_bus=EventBus(),
        cloud_share_service=_svc(tmp_path),
        onedrive_base_folder="SLC/clips-supervisor",
    )
    result = api.ensure_folder_and_link("")
    assert result.folder_path.startswith("SLC/clips-supervisor/")


def test_folder_path_includes_active_operator(tmp_path) -> None:
    from app.core.ports.request_port import ClipRequest

    req = ClipRequest(id="1", created_at="", supervisor_host="", operator="Op-28",
                      storage="S", start_time="", end_time="", description="", status="pending")
    api = DeliveryApi(
        event_bus=EventBus(),
        cloud_share_service=_svc(tmp_path),
        onedrive_base_folder="SLC/clips-supervisor",
        request_port=FakeRequestPort([req]),
    )
    assert "Op-28" in api.compute_folder_path()


def test_no_service_raises() -> None:
    api = DeliveryApi(event_bus=EventBus(), cloud_share_service=None)
    assert api.available is False
    with pytest.raises(RuntimeError):
        api.ensure_folder_and_link("a/b")


def test_reset_onedrive_noop_when_already_idle() -> None:
    bus = EventBus()
    api = DeliveryApi(event_bus=bus, cloud_share_service=None)
    events = []
    bus.subscribe(dto.OneDriveChanged, events.append)
    api.reset_onedrive()
    bus.drain()
    assert events == []


def test_reset_onedrive_clears_linked_state(tmp_path) -> None:
    bus = EventBus()
    api = DeliveryApi(event_bus=bus, cloud_share_service=_svc(tmp_path))
    api.ensure_folder_and_link("SLC/clips-supervisor/2026-07")
    bus.drain()  # flush the "linked" event so only the reset's "idle" event is asserted below

    events = []
    bus.subscribe(dto.OneDriveChanged, events.append)
    api.reset_onedrive()
    bus.drain()

    assert len(events) == 1
    assert (events[0].state, events[0].folder, events[0].link) == ("idle", "", "")


class FakeEditor:
    """Stands in for EditorApi's export surface — completes inline/synchronously
    (like _run_export_async swapped for _do_export in test_facade_editor.py) so
    these tests stay deterministic without a background thread."""

    def __init__(self, bus: EventBus, fail: bool = False) -> None:
        self._bus = bus
        self.exporting = False
        self.fail = fail
        self.exported_to = None

    def export_timeline(self, output_path: str) -> None:
        self.exported_to = output_path
        if self.fail:
            self._bus.publish(dto.ExportFailed(message="boom"))
        else:
            self._bus.publish(dto.ExportFinished(output_path=output_path))


def _api_with_editor(tmp_path, fail: bool = False):
    bus = EventBus()
    editor = FakeEditor(bus, fail=fail)
    api = DeliveryApi(
        event_bus=bus,
        cloud_share_service=_svc(tmp_path),
        export_fn=editor.export_timeline,
        is_exporting=lambda: editor.exporting,
    )
    return bus, api, editor


class TestSaveReelPrivately:
    def test_success_ensures_folder_exports_and_publishes_saved(self, tmp_path) -> None:
        bus, api, editor = _api_with_editor(tmp_path)
        events: list[object] = []
        bus.subscribe(dto.OneDriveSaveStarted, events.append)
        bus.subscribe(dto.OneDriveSaved, events.append)

        api.save_reel_privately("SLC/clips-supervisor/2026-07")
        bus.drain()

        assert isinstance(events[0], dto.OneDriveSaveStarted)
        assert isinstance(events[-1], dto.OneDriveSaved)
        assert events[-1].folder_path == "SLC/clips-supervisor/2026-07"
        assert events[-1].output_path == editor.exported_to
        assert (tmp_path / "od" / "SLC" / "clips-supervisor" / "2026-07").is_dir()

    def test_never_publishes_a_link(self, tmp_path) -> None:
        bus, api, _editor = _api_with_editor(tmp_path)
        linked: list[object] = []
        bus.subscribe(dto.OneDriveChanged, linked.append)

        api.save_reel_privately("a/b")
        bus.drain()

        assert linked == []

    def test_rejects_when_export_already_running(self, tmp_path) -> None:
        bus, api, editor = _api_with_editor(tmp_path)
        editor.exporting = True
        fails: list[object] = []
        bus.subscribe(dto.OneDriveSaveFailed, fails.append)

        api.save_reel_privately("a/b")
        bus.drain()

        assert len(fails) == 1
        assert "exportación en curso" in fails[0].message
        assert not (tmp_path / "od" / "a" / "b").exists()  # never got as far as ensuring the folder

    def test_maps_export_failure_to_save_failed(self, tmp_path) -> None:
        bus, api, _editor = _api_with_editor(tmp_path, fail=True)
        fails: list[object] = []
        bus.subscribe(dto.OneDriveSaveFailed, fails.append)

        api.save_reel_privately("a/b")
        bus.drain()

        assert len(fails) == 1
        assert fails[0].message == "boom"

    def test_folder_error_is_reported_without_touching_export(self, tmp_path) -> None:
        bus, api, editor = _api_with_editor(tmp_path)
        fails: list[object] = []
        bus.subscribe(dto.OneDriveSaveFailed, fails.append)

        api.save_reel_privately("   ///   ")  # normalizes to empty -> ValueError in the service
        bus.drain()

        assert len(fails) == 1
        assert editor.exported_to is None

    def test_unrelated_export_finished_is_ignored(self, tmp_path) -> None:
        bus, api, _editor = _api_with_editor(tmp_path)
        saved: list[object] = []
        bus.subscribe(dto.OneDriveSaved, saved.append)

        # A plain export from ExportDialog, not started via save_reel_privately.
        bus.publish(dto.ExportFinished(output_path="/some/other/path.mp4"))
        bus.drain()

        assert saved == []

    def test_no_service_reports_failure_event_not_an_exception(self, tmp_path) -> None:
        bus = EventBus()
        editor = FakeEditor(bus)
        api = DeliveryApi(
            event_bus=bus,
            cloud_share_service=None,
            export_fn=editor.export_timeline,
            is_exporting=lambda: editor.exporting,
        )
        fails: list[object] = []
        bus.subscribe(dto.OneDriveSaveFailed, fails.append)

        api.save_reel_privately("a/b")  # must not raise
        bus.drain()

        assert len(fails) == 1
        assert editor.exported_to is None
