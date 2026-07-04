r"""WindowsFileBrowserAdapter — FileBrowserPort via net use / net view / scandir.

Moved out of ``app_bridge`` unchanged in behaviour: UNC servers are authenticated
through ``\\server\IPC$`` with the configured NAS credentials, a **failed** auth
is never cached (so the UI's Retry button can re-auth), bare-server paths are
enumerated with ``net view``, and hidden/admin shares (``name$``) are hidden.
"""
from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone
from typing import List, Set

from loguru import logger

from app.core.ports.file_browser_port import BrowseEntry, BrowseListing, FileBrowserPort


def _fmt_size(size_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.0f} {unit}"
        size_bytes //= 1024
    return f"{size_bytes:.0f} TB"


class WindowsFileBrowserAdapter(FileBrowserPort):
    """Windows-native browsing for the clip browser (local + UNC shares)."""

    def __init__(self, nas_username: str = "", nas_password: str = "") -> None:
        self._nas_username = nas_username
        self._nas_password = nas_password
        # Servers authenticated this session — cached ONLY on success.
        self._authenticated: Set[str] = set()

    # ── Auth ──────────────────────────────────────────────────────────

    def connect(self, server: str) -> bool:
        """Authenticate a UNC server via IPC$ using stored NAS credentials.

        Returns True on success or when no credentials are configured (let the OS
        use the current user's token); False on a real ``net use`` failure/timeout
        so the caller does NOT cache a failed server.
        """
        if not self._nas_username:
            logger.debug("No NAS_USERNAME configured — skipping net use for {}", server)
            return True
        try:
            ipc = f"{server}\\IPC$"
            cmd = [
                "net", "use", ipc,
                f"/user:{self._nas_username}",
                self._nas_password,
                "/persistent:no",
            ]
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if result.returncode == 0:
                logger.info("ClipBrowser: authenticated {} as '{}'.", server, self._nas_username)
                return True
            err = result.stderr.decode("utf-8", errors="replace").strip()
            logger.warning(
                "ClipBrowser: net use {} failed (rc={}) — {}", ipc, result.returncode, err[:300]
            )
            return False
        except Exception:
            logger.exception("ClipBrowser: error connecting to {}.", server)
            return False

    def _ensure_authenticated(self, server: str) -> bool:
        """Connect + cache on success only. Returns False if auth failed."""
        if not server or server in self._authenticated:
            return True
        if self.connect(server):
            self._authenticated.add(server)
            return True
        return False

    # ── Listing ───────────────────────────────────────────────────────

    def list_shares(self, server: str) -> List[BrowseEntry]:
        """Enumerate shares on a UNC server using ``net view`` (hidden shares excluded)."""
        try:
            result = subprocess.run(
                ["net", "view", server],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if result.returncode != 0:
                err = result.stderr.decode("utf-8", errors="replace").strip()
                logger.warning("ClipBrowser: net view {} failed — {}", server, err[:200])
                return []

            shares: List[BrowseEntry] = []
            in_list = False
            for line in result.stdout.decode("utf-8", errors="replace").splitlines():
                stripped = line.strip()
                if not stripped:
                    continue
                if stripped.startswith("---"):
                    in_list = True
                    continue
                if not in_list:
                    continue
                parts = stripped.split()
                if not parts:
                    continue
                share_name = parts[0]
                if share_name.endswith("$"):
                    continue  # skip hidden/admin shares
                shares.append(
                    BrowseEntry(
                        name=share_name,
                        path=f"{server}\\{share_name}",
                        is_dir=True,
                    )
                )
            logger.info("ClipBrowser: {} shares found on {}", len(shares), server)
            return shares
        except Exception:
            logger.exception("ClipBrowser: error enumerating shares on {}.", server)
            return []

    def list_directory(self, path: str) -> BrowseListing:
        """List a resolved local or UNC path.

        Handles UNC authentication and bare-server (``\\\\server``) share
        enumeration.  ``BrowseListing.failed`` is True on a connection/permission
        failure (vs. an empty-but-reachable directory).
        """
        listing = BrowseListing()
        resolved = path

        if resolved.startswith("\\\\") or resolved.startswith("//"):
            normed = resolved.replace("/", "\\").rstrip("\\")
            parts = normed.lstrip("\\").split("\\")
            server = f"\\\\{parts[0]}" if parts else ""
            if server:
                if not self._ensure_authenticated(server):
                    listing.failed = True
                    return listing
                # Bare server path (no share) — enumerate shares via net view.
                if len(parts) <= 1:
                    shares = self.list_shares(server)
                    listing.entries = shares
                    if not shares:
                        listing.failed = True
                    return listing

        try:
            with os.scandir(resolved) as it:
                entries = sorted(
                    it, key=lambda e: (not e.is_dir(follow_symlinks=False), e.name.lower())
                )
                for entry in entries:
                    if entry.name.startswith("$") or entry.name.startswith("."):
                        continue
                    try:
                        is_dir = entry.is_dir(follow_symlinks=False)
                        stat = entry.stat(follow_symlinks=False)
                        mtime = datetime.fromtimestamp(
                            stat.st_mtime, tz=timezone.utc
                        ).astimezone()
                        size_b = 0 if is_dir else stat.st_size
                        ext = "" if is_dir else os.path.splitext(entry.name)[1].lstrip(".").upper()
                        listing.entries.append(
                            BrowseEntry(
                                name=entry.name,
                                path=entry.path,
                                is_dir=is_dir,
                                modified=mtime.strftime("%m/%d/%Y  %I:%M %p"),
                                size=_fmt_size(size_b) if size_b else "",
                                ext=ext,
                            )
                        )
                    except OSError:
                        pass
        except (OSError, PermissionError) as exc:
            logger.warning("ClipBrowser: cannot list '{}': {}", resolved, exc)
            listing.failed = True
        return listing

    def count_dirs(self, path: str) -> int:
        try:
            with os.scandir(path) as it:
                return sum(
                    1
                    for e in it
                    if e.is_dir(follow_symlinks=False)
                    and not e.name.startswith("$")
                    and not e.name.startswith(".")
                )
        except (OSError, PermissionError):
            return 0
