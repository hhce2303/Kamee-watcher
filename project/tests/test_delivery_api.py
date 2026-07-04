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
