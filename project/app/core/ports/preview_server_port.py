from __future__ import annotations

from abc import ABC, abstractmethod


class PreviewServerPort(ABC):
    """
    Port for a local HTTP preview server that exposes MJPEG streams of the
    live recording previews.  Only the Operator role starts an implementation;
    all other roles leave this as None in the wiring root.
    """

    @abstractmethod
    def start(self) -> None:
        """Start the HTTP server (non-blocking — runs in a daemon thread)."""

    @abstractmethod
    def stop(self) -> None:
        """Stop the HTTP server and release the port."""

    @property
    @abstractmethod
    def base_url(self) -> str:
        """Base URL of the server, e.g. ``http://127.0.0.1:8787``."""

    @property
    @abstractmethod
    def is_running(self) -> bool:
        """True while the server thread is alive and serving requests."""
