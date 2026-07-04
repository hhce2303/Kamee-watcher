"""RequestsApi facade — storages/operators enumeration + request lifecycle."""
from __future__ import annotations

import json

from app.core.api import dto
from app.core.api.events import EventBus
from app.core.api.requests_api import RequestsApi
from app.core.ports.file_browser_port import BrowseEntry, BrowseListing
from app.core.ports.request_port import ClipRequest


class FakeBrowser:
    def __init__(self, shares=None, operators=None):
        self._shares = shares or []
        self._operators = operators or []

    def connect(self, server):
        return True

    def list_shares(self, server):
        return self._shares

    def list_directory(self, path):
        return BrowseListing(entries=self._operators)

    def count_dirs(self, path):
        return sum(1 for e in self._operators if e.is_dir)


class FakeRequestPort:
    def __init__(self):
        self.saved = []
        self.status_updates = []
        self._all = []

    def save(self, req):
        self.saved.append(req)
        self._all.append(req)

    def load_all(self):
        return list(self._all)

    def update_status(self, req_id, status):
        self.status_updates.append((req_id, status))


class FakeServer:
    def __init__(self):
        self.updates = []

    def send_status_update(self, req_id, status):
        self.updates.append((req_id, status))


class FakeClient:
    def __init__(self):
        self.sent = []

    def send_request(self, req):
        self.sent.append(req)


def _api(**kw):
    return RequestsApi(event_bus=EventBus(), **kw)


def test_list_storages_with_operator_count() -> None:
    shares = [BrowseEntry(name="Storage1", path=r"\\NAS\Storage1", is_dir=True)]
    ops = [BrowseEntry(name="Op-1", path="p1", is_dir=True), BrowseEntry(name="Op-2", path="p2", is_dir=True)]
    api = _api(file_browser=FakeBrowser(shares=shares, operators=ops), slc_storage_host=r"\\NAS")
    storages = api.list_storages()
    assert len(storages) == 1
    assert storages[0].name == "Storage1"
    assert storages[0].operator_count == 2


def test_list_operators_drops_path() -> None:
    ops = [BrowseEntry(name="Op-1", path="secret", is_dir=True), BrowseEntry(name="f.txt", path="f", is_dir=False)]
    api = _api(file_browser=FakeBrowser(operators=ops))
    result = api.list_operators(r"\\NAS\Storage1")
    assert [o.name for o in result] == ["Op-1"]   # files excluded
    assert result[0].storage == "Storage1"
    assert not hasattr(result[0], "path")  # security contract: no navigable path


def test_send_clip_request_persists_and_sends() -> None:
    port = FakeRequestPort()
    client = FakeClient()
    api = _api(request_port=port, client=client)
    payload = json.dumps({
        "operator": "Op-28", "storage": "Storage1",
        "start_time": "2026-07-03 10:00", "end_time": "2026-07-03 10:05",
        "description": "incident",
    })
    assert api.send_clip_request(dto.SendClipRequest(request_json=payload)) is True
    assert len(port.saved) == 1
    assert port.saved[0].id  # id generated
    assert port.saved[0].status == "pending"
    assert len(client.sent) == 1


def test_send_clip_request_invalid_json() -> None:
    port = FakeRequestPort()
    api = _api(request_port=port)
    assert api.send_clip_request(dto.SendClipRequest(request_json="{not json")) is False
    assert port.saved == []


def test_update_status_broadcasts_and_publishes() -> None:
    port = FakeRequestPort()
    server = FakeServer()
    api = _api(request_port=port, server=server)
    changed, received = [], []
    api._bus.subscribe(dto.RequestStatusChanged, changed.append)
    api._bus.subscribe(dto.RequestReceived, received.append)

    api.update_request_status(dto.UpdateRequestStatus(request_id="r1", status="done"))
    api._bus.drain()

    assert port.status_updates == [("r1", "done")]
    assert server.updates == [("r1", "done")]
    assert changed and changed[0].status == "done"
    assert len(received) == 1


def test_inbox_and_my_requests() -> None:
    port = FakeRequestPort()
    port.save(ClipRequest(id="1", created_at="", supervisor_host="", operator="Op", storage="S",
                          start_time="", end_time="", description=""))
    api = _api(request_port=port)
    assert len(api.inbox_requests()) == 1
    assert len(api.my_requests()) == 1


def test_on_request_received_publishes() -> None:
    port = FakeRequestPort()
    api = _api(request_port=port)
    got = []
    api._bus.subscribe(dto.RequestReceived, got.append)
    api.on_request_received("r9")
    api._bus.drain()
    assert port.status_updates == [("r9", "pending")]
    assert len(got) == 1


def test_no_request_port_degrades() -> None:
    api = _api()
    assert api.inbox_requests() == []
    assert api.send_clip_request(dto.SendClipRequest(request_json="{}")) is False
