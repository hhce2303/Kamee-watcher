"""FileBrowserPort — browse local/UNC directories for the clip browser (F1).

Extracted from ``app_bridge`` so the UI no longer shells out to ``net use`` /
``net view`` or touches ``os.scandir`` directly (ADR-0009: adapters know their
transport, the core/UI does not).  ``ClipsApi`` and ``RequestsApi`` drive this
port; the Windows implementation lives in ``adapters/filesystem``.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class BrowseEntry:
    """One row in a directory listing."""

    name: str
    path: str
    is_dir: bool
    modified: str = ""
    size: str = ""
    ext: str = ""


@dataclass
class BrowseListing:
    """Result of a directory listing.

    ``failed`` distinguishes a real connection/permission failure (dead share,
    failed UNC auth) from an empty-but-reachable directory, so the UI can show an
    honest "Sin conexión · Reintentar" row instead of a blank folder.
    """

    entries: List[BrowseEntry] = field(default_factory=list)
    failed: bool = False


class FileBrowserPort(ABC):
    """Browse directories and UNC shares with credential-based authentication."""

    @abstractmethod
    def connect(self, server: str) -> bool:
        """Authenticate a UNC server (e.g. ``\\\\SERVER``). True on success/no-creds."""
        raise NotImplementedError

    @abstractmethod
    def list_directory(self, path: str) -> BrowseListing:
        """List a resolved local or UNC path (handles UNC auth + share enumeration)."""
        raise NotImplementedError

    @abstractmethod
    def list_shares(self, server: str) -> List[BrowseEntry]:
        """Enumerate the shares on a bare UNC server via ``net view``."""
        raise NotImplementedError

    @abstractmethod
    def count_dirs(self, path: str) -> int:
        """Count immediate subdirectories of *path* (0 on error)."""
        raise NotImplementedError
