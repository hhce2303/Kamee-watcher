"""ClipsApi facade — clip listing, load metadata, and token-resolved browsing."""
from __future__ import annotations

import threading
from datetime import date
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


class FakeConverter:
    """Runs synchronously (no thread) so tests don't need to wait/poll."""

    def __init__(self, output_suffix="_converted.mp4", fail=False):
        self._suffix = output_suffix
        self._fail = fail
        self.calls = []

    def convert(self, source, output=None, on_progress=None, cancel_event=None):
        self.calls.append(source)
        self.last_cancel_event = cancel_event
        if cancel_event is not None and cancel_event.is_set():
            raise RuntimeError("Conversión cancelada por el usuario.")
        if on_progress:
            on_progress(0.5)
            on_progress(1.0)
        if self._fail:
            raise RuntimeError("ffmpeg exploded")
        out = output or source.with_stem(source.stem + "_converted").with_suffix(".mp4")
        out.write_bytes(b"converted")
        return out


def _api(tmp_path, player=None, browser=None, converter=None, event_clips_dir=None):
    return ClipsApi(
        event_bus=EventBus(),
        clips_dir=tmp_path / "clips",
        event_clips_dir=event_clips_dir,
        player_service=player,
        file_browser=browser,
        mp4_converter=converter,
    )


def test_date_label_yesterday_across_month_boundary() -> None:
    # Regression test: today.replace(day=today.day - 1) used to break on the
    # 1st of the month, making "yesterday" collapse to "today" and losing the
    # "Ayer" label for the real previous day.
    today = date(2026, 7, 1)
    assert ClipsApi._date_label(date(2026, 6, 30), today) == "Ayer"
    assert ClipsApi._date_label(today, today) == "Hoy"


def test_date_label_yesterday_across_year_boundary() -> None:
    today = date(2026, 1, 1)
    assert ClipsApi._date_label(date(2025, 12, 31), today) == "Ayer"


def test_date_label_yesterday_mid_month() -> None:
    today = date(2026, 7, 15)
    assert ClipsApi._date_label(date(2026, 7, 14), today) == "Ayer"
    assert ClipsApi._date_label(date(2026, 7, 13), today) not in ("Hoy", "Ayer")


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


def test_list_clips_scans_both_dirs_with_directory_based_is_event(tmp_path) -> None:
    combined_dir = tmp_path / "clips"
    combined_dir.mkdir()
    events_dir = tmp_path / "clips_events"
    events_dir.mkdir()
    (combined_dir / "2026-07-03_00-00-00.mp4").write_bytes(b"x" * 1_000_000)
    (events_dir / "2026-07-03_00-05-00.mp4").write_bytes(b"y" * 500_000)

    api = _api(tmp_path, event_clips_dir=events_dir)
    clips = api.list_clips()

    assert len(clips) == 2
    by_name = {c.clip_name: c for c in clips}
    assert by_name["2026-07-03_00-00-00.mp4"].is_event is False
    # is_event is True purely because the file lives under event_clips_dir —
    # no "_event" substring in this filename.
    assert by_name["2026-07-03_00-05-00.mp4"].is_event is True


def test_list_clips_without_event_clips_dir_falls_back_to_substring(tmp_path) -> None:
    d = tmp_path / "clips"
    d.mkdir()
    (d / "2026-07-03_event.mp4").write_bytes(b"x" * 1_000_000)
    api = _api(tmp_path)  # no event_clips_dir configured
    clips = api.list_clips()
    assert len(clips) == 1
    assert clips[0].is_event is True


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


def test_list_directory_resolves_local_events_token(tmp_path) -> None:
    browser = FakeBrowser()
    events_dir = tmp_path / "clips_events"
    api = _api(tmp_path, browser=browser, event_clips_dir=events_dir)
    api.list_directory(dto.ListDirectory(path="LOCAL_EVENTS"))
    assert browser.last_path == str(events_dir)


def test_list_directory_local_events_token_empty_when_unconfigured(tmp_path) -> None:
    browser = FakeBrowser()
    api = _api(tmp_path, browser=browser)  # no event_clips_dir
    api.list_directory(dto.ListDirectory(path="LOCAL_EVENTS"))
    assert browser.last_path == ""


def test_list_directory_passthrough(tmp_path) -> None:
    browser = FakeBrowser()
    api = _api(tmp_path, browser=browser)
    result = api.list_directory(dto.ListDirectory(path=r"\\NAS\share"))
    assert browser.last_path == r"\\NAS\share"
    assert result.entries and result.entries[0].name == "x"


def test_list_directory_no_browser_flags_failed(tmp_path) -> None:
    result = _api(tmp_path).list_directory(dto.ListDirectory(path="LOCAL_CLIPS"))
    assert result.failed is True


def _sync(api) -> None:
    """Make transcode run inline instead of on a background thread."""
    api._run_transcode_async = api._do_transcode  # noqa: SLF001


def test_transcode_clip_success_publishes_started_progress_finished(tmp_path) -> None:
    clip = tmp_path / "c.mp4"
    clip.write_bytes(b"x")
    converter = FakeConverter()
    api = _api(tmp_path, converter=converter)
    _sync(api)
    events = []
    api._bus.subscribe(dto.TranscodeStarted, events.append)
    api._bus.subscribe(dto.TranscodeProgress, events.append)
    api._bus.subscribe(dto.TranscodeFinished, events.append)

    api.transcode_clip(dto.TranscodeClip(path=str(clip)))
    api._bus.drain()

    kinds = [type(e).__name__ for e in events]
    assert kinds == ["TranscodeStarted", "TranscodeProgress", "TranscodeProgress", "TranscodeFinished"]
    assert converter.calls == [clip]
    assert str(clip) not in api._transcoding


def test_transcode_clip_failure_publishes_failed(tmp_path) -> None:
    clip = tmp_path / "c.mp4"
    clip.write_bytes(b"x")
    api = _api(tmp_path, converter=FakeConverter(fail=True))
    _sync(api)
    failed = []
    api._bus.subscribe(dto.TranscodeFailed, failed.append)

    api.transcode_clip(dto.TranscodeClip(path=str(clip)))
    api._bus.drain()

    assert len(failed) == 1
    assert "ffmpeg exploded" in failed[0].message
    assert str(clip) not in api._transcoding


def test_transcode_clip_no_converter_configured(tmp_path) -> None:
    clip = tmp_path / "c.mp4"
    clip.write_bytes(b"x")
    api = _api(tmp_path)
    failed = []
    api._bus.subscribe(dto.TranscodeFailed, failed.append)

    api.transcode_clip(dto.TranscodeClip(path=str(clip)))
    api._bus.drain()

    assert len(failed) == 1


def test_transcode_clip_missing_file(tmp_path) -> None:
    api = _api(tmp_path, converter=FakeConverter())
    failed = []
    api._bus.subscribe(dto.TranscodeFailed, failed.append)

    api.transcode_clip(dto.TranscodeClip(path=str(tmp_path / "nope.mp4")))
    api._bus.drain()

    assert len(failed) == 1


def test_transcode_clip_rejects_concurrent_duplicate(tmp_path) -> None:
    clip = tmp_path / "c.mp4"
    clip.write_bytes(b"x")
    converter = FakeConverter()
    api = _api(tmp_path, converter=converter)
    api._transcoding.add(str(clip))  # simulate an in-flight transcode

    api.transcode_clip(dto.TranscodeClip(path=str(clip)))

    assert converter.calls == []


def test_transcode_clip_passes_a_cancel_event_to_the_converter(tmp_path) -> None:
    clip = tmp_path / "c.mp4"
    clip.write_bytes(b"x")
    converter = FakeConverter()
    api = _api(tmp_path, converter=converter)
    _sync(api)

    api.transcode_clip(dto.TranscodeClip(path=str(clip)))
    api._bus.drain()

    assert isinstance(converter.last_cancel_event, threading.Event)
    assert not converter.last_cancel_event.is_set()


def test_cancel_transcode_sets_the_event_and_converter_reports_failed(tmp_path) -> None:
    """cancel_transcode() only sets a flag — it's the converter's own poll
    loop that notices and kills the process; here that's simulated by
    FakeConverter checking the event itself before "succeeding"."""
    clip = tmp_path / "c.mp4"
    clip.write_bytes(b"x")
    converter = FakeConverter()
    api = _api(tmp_path, converter=converter)

    # Don't use _sync() here — cancel before the (still-async) transcode
    # thread gets to check the event, mirroring the real race the feature
    # exists for. Instead, drive it manually: start, cancel, then run the
    # "background" work inline once the event is already set.
    api._run_transcode_async = lambda path, cancel_event: None  # swallow the real thread
    api.transcode_clip(dto.TranscodeClip(path=str(clip)))
    assert str(clip) in api._cancel_events

    api.cancel_transcode(str(clip))
    assert api._cancel_events[str(clip)].is_set()

    failed = []
    api._bus.subscribe(dto.TranscodeFailed, failed.append)
    api._do_transcode(str(clip), api._cancel_events[str(clip)])
    api._bus.drain()

    assert len(failed) == 1
    assert "ancel" in failed[0].message
    assert str(clip) not in api._transcoding
    assert str(clip) not in api._cancel_events


def test_cancel_transcode_no_op_when_nothing_running(tmp_path) -> None:
    api = _api(tmp_path, converter=FakeConverter())
    api.cancel_transcode(str(tmp_path / "nope.mp4"))  # must not raise
