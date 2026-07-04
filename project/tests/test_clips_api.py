"""ClipsApi facade — clip listing, load metadata, and token-resolved browsing."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.core.api import dto
from app.core.api.clips_api import ClipsApi
from app.core.api.events import EventBus
from app.core.ports.file_browser_port import BrowseEntry, BrowseListing


class FakeBrowser:
    def __init__(self):
        self.last_path = None

    def connect(self, server):
        return True

    def list_directory(self, path):
        self.last_path = path
        return BrowseListing(entries=[BrowseEntry(name="x", path=path + "\\x", is_dir=False)])

    def list_shares(self, server):
        return []

    def count_dirs(self, path):
        return 0


class FakePlayer:
    def load(self, path):
        return SimpleNamespace(
            video_stream=SimpleNamespace(width=1920, height=1080, bitrate_kbps=8000),
            video_codec="hevc",
            fps=30.0,
            duration_seconds=42.0,
        )


def _api(tmp_path, player=None, browser=None):
    return ClipsApi(
        event_bus=EventBus(),
        clips_dir=tmp_path / "clips",
        player_service=player,
        file_browser=browser,
    )


def test_list_clips_newest_first_with_labels(tmp_path) -> None:
    d = tmp_path / "clips"
    d.mkdir()
    (d / "2026-07-03_event.mp4").write_bytes(b"x" * 2_000_000)
    (d / "plain.mp4").write_bytes(b"y" * 1_000_000)
    api = _api(tmp_path)
    clips = api.list_clips()
    assert len(clips) == 2
    ev = [c for c in clips if c.is_event]
    assert ev and ev[0].clip_name == "2026-07-03_event.mp4"
    assert all(c.date_label for c in clips)
    assert all(c.size_label.endswith("MB") for c in clips)


def test_list_clips_missing_dir_returns_empty(tmp_path) -> None:
    assert _api(tmp_path).list_clips() == []


def test_publish_clips_emits_event(tmp_path) -> None:
    (tmp_path / "clips").mkdir()
    api = _api(tmp_path)
    seen = []
    api._bus.subscribe(dto.ClipsChanged, seen.append)
    api.publish_clips()
    api._bus.drain()
    assert len(seen) == 1


def test_load_clip_builds_info(tmp_path) -> None:
    clip = tmp_path / "c.mp4"
    clip.write_bytes(b"x")
    api = _api(tmp_path, player=FakePlayer())
    loaded = api.load_clip(dto.LoadClip(path=str(clip)))
    assert loaded.ok is True
    assert loaded.info.resolution == "1920×1080"
    assert loaded.info.codec == "hevc"
    assert loaded.info.fps == "30"
    assert loaded.info.bitrate == "8000 kbps"
    assert loaded.info.duration_seconds == 42.0


def test_load_clip_empty_path(tmp_path) -> None:
    loaded = _api(tmp_path, player=FakePlayer()).load_clip(dto.LoadClip(path=""))
    assert loaded.ok is False and loaded.path == ""


def test_load_clip_missing_local_file(tmp_path) -> None:
    loaded = _api(tmp_path, player=FakePlayer()).load_clip(
        dto.LoadClip(path=str(tmp_path / "nope.mp4"))
    )
    assert loaded.ok is False


def test_list_directory_resolves_local_clips_token(tmp_path) -> None:
    browser = FakeBrowser()
    api = _api(tmp_path, browser=browser)
    api.list_directory(dto.ListDirectory(path="LOCAL_CLIPS"))
    assert browser.last_path == str(tmp_path / "clips")


def test_list_directory_resolves_local_raw_token(tmp_path) -> None:
    browser = FakeBrowser()
    api = _api(tmp_path, browser=browser)
    api.list_directory(dto.ListDirectory(path="LOCAL_RAW"))
    assert browser.last_path == str(tmp_path / "clips_raw")


def test_list_directory_passthrough(tmp_path) -> None:
    browser = FakeBrowser()
    api = _api(tmp_path, browser=browser)
    result = api.list_directory(dto.ListDirectory(path=r"\\NAS\share"))
    assert browser.last_path == r"\\NAS\share"
    assert result.entries and result.entries[0].name == "x"


def test_list_directory_no_browser_flags_failed(tmp_path) -> None:
    result = _api(tmp_path).list_directory(dto.ListDirectory(path="LOCAL_CLIPS"))
    assert result.failed is True
