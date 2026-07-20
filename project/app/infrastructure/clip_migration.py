"""One-time migration: move legacy event clips out of clips_dir.

Event clips used to share clips_dir with combined recordings, distinguished
only by an "_event" filename substring. Now that event clips get their own
directory (event_clips_dir), this moves any pre-existing ones (and their
.events.json sidecars) so the old mixed folder gets cleaned up automatically.
Idempotent: once a file has been moved, a second run finds nothing to do.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from loguru import logger


def migrate_legacy_event_clips(clips_dir: Path, event_clips_dir: Path) -> int:
    """Move any ``*_event*.mp4`` (and matching ``.events.json`` sidecar) from
    ``clips_dir`` into ``event_clips_dir``. Returns the number of clips moved.

    The substring check (not an exact ``*_event.mp4`` glob) also catches the
    on-demand transcode fallback's ``*_event_converted.mp4`` sibling, so it
    isn't left behind in the old folder.
    """
    if not clips_dir.exists():
        return 0

    event_clips_dir.mkdir(parents=True, exist_ok=True)
    moved = 0
    for clip in sorted(clips_dir.glob("*.mp4")):
        if "_event" not in clip.stem:
            continue
        destination = event_clips_dir / clip.name
        try:
            shutil.move(str(clip), str(destination))
        except OSError:
            logger.warning("[clip-migration] could not move {} — left in place", clip.name)
            continue

        sidecar = clip.with_suffix(".events.json")
        if sidecar.exists():
            try:
                shutil.move(str(sidecar), str(event_clips_dir / sidecar.name))
            except OSError:
                logger.warning(
                    "[clip-migration] could not move sidecar {} — left in place", sidecar.name
                )

        moved += 1
        logger.info("[clip-migration] moved {} → {}", clip.name, event_clips_dir)

    if moved:
        logger.info(
            "[clip-migration] migrated {} legacy event clip(s) from {} to {}",
            moved, clips_dir, event_clips_dir,
        )
    return moved
