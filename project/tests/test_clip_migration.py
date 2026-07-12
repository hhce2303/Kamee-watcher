"""migrate_legacy_event_clips — one-time cleanup moving event clips out of clips_dir."""
from __future__ import annotations

from app.infrastructure.clip_migration import migrate_legacy_event_clips


def test_moves_event_clip_and_sidecar(tmp_path):
    clips_dir = tmp_path / "clips"
    clips_dir.mkdir()
    events_dir = tmp_path / "clips_events"

    clip = clips_dir / "2026-07-03_00-00-00_event.mp4"
    clip.write_bytes(b"clip")
    sidecar = clips_dir / "2026-07-03_00-00-00_event.events.json"
    sidecar.write_text("{}")

    moved = migrate_legacy_event_clips(clips_dir, events_dir)

    assert moved == 1
    assert not clip.exists()
    assert not sidecar.exists()
    assert (events_dir / clip.name).exists()
    assert (events_dir / sidecar.name).exists()


def test_leaves_combined_clips_in_place(tmp_path):
    clips_dir = tmp_path / "clips"
    clips_dir.mkdir()
    events_dir = tmp_path / "clips_events"
    combined = clips_dir / "2026-07-03_00-00-00.mp4"
    combined.write_bytes(b"combined")

    moved = migrate_legacy_event_clips(clips_dir, events_dir)

    assert moved == 0
    assert combined.exists()
    assert not events_dir.exists() or not any(events_dir.iterdir())


def test_moves_transcode_fallback_sibling(tmp_path):
    """*_event_converted.mp4 must be caught too — substring match, not exact suffix."""
    clips_dir = tmp_path / "clips"
    clips_dir.mkdir()
    events_dir = tmp_path / "clips_events"
    (clips_dir / "2026-07-03_00-00-00_event.mp4").write_bytes(b"clip")
    (clips_dir / "2026-07-03_00-00-00_event_converted.mp4").write_bytes(b"converted")

    moved = migrate_legacy_event_clips(clips_dir, events_dir)

    assert moved == 2
    assert (events_dir / "2026-07-03_00-00-00_event.mp4").exists()
    assert (events_dir / "2026-07-03_00-00-00_event_converted.mp4").exists()


def test_idempotent_on_second_run(tmp_path):
    clips_dir = tmp_path / "clips"
    clips_dir.mkdir()
    events_dir = tmp_path / "clips_events"
    (clips_dir / "2026-07-03_00-00-00_event.mp4").write_bytes(b"clip")

    first = migrate_legacy_event_clips(clips_dir, events_dir)
    second = migrate_legacy_event_clips(clips_dir, events_dir)

    assert first == 1
    assert second == 0
    assert (events_dir / "2026-07-03_00-00-00_event.mp4").exists()


def test_missing_clips_dir_returns_zero(tmp_path):
    clips_dir = tmp_path / "does_not_exist"
    events_dir = tmp_path / "clips_events"
    assert migrate_legacy_event_clips(clips_dir, events_dir) == 0
