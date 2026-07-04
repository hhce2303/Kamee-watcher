"""WindowsFileBrowserAdapter — UNC auth caching + local listing (F1).

Replaces the AppBridge NAS tests: the net use / net view / scandir logic moved
out of the bridge into this adapter (ADR-0009). We exercise the real methods,
patching only the subprocess boundary.
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.adapters.filesystem.file_browser_adapter import WindowsFileBrowserAdapter
from app.core.ports.file_browser_port import FileBrowserPort


def test_implements_port() -> None:
    assert isinstance(WindowsFileBrowserAdapter(), FileBrowserPort)


class TestConnect:
    def test_returns_true_on_success(self) -> None:
        a = WindowsFileBrowserAdapter(nas_username="csoperator", nas_password="pw")
        with patch("subprocess.run", return_value=SimpleNamespace(returncode=0, stderr=b"")):
            assert a.connect(r"\\SERVER") is True

    def test_returns_false_on_failure(self) -> None:
        a = WindowsFileBrowserAdapter(nas_username="csoperator", nas_password="pw")
        with patch("subprocess.run", return_value=SimpleNamespace(returncode=2, stderr=b"System error 53")):
            assert a.connect(r"\\SERVER") is False

    def test_returns_false_on_timeout(self) -> None:
        a = WindowsFileBrowserAdapter(nas_username="csoperator", nas_password="pw")
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("net", 5)):
            assert a.connect(r"\\SERVER") is False

    def test_no_credentials_skips_net_use(self) -> None:
        a = WindowsFileBrowserAdapter(nas_username="")
        with patch("subprocess.run") as run:
            assert a.connect(r"\\SERVER") is True
            run.assert_not_called()


class TestListDirectoryAuthCache:
    def test_failed_auth_not_cached_and_flags_failure(self) -> None:
        a = WindowsFileBrowserAdapter(nas_username="u", nas_password="p")
        a.connect = lambda server: False  # simulate auth failure
        listing = a.list_directory(r"\\DEADHOST\share")
        assert listing.entries == []
        assert r"\\DEADHOST" not in a._authenticated  # retry can re-auth
        assert listing.failed is True

    def test_successful_auth_is_cached(self) -> None:
        a = WindowsFileBrowserAdapter(nas_username="u", nas_password="p")
        a.connect = lambda server: True
        a.list_shares = lambda server: []  # bare-server enumeration stub
        a.list_directory(r"\\LIVEHOST")
        assert r"\\LIVEHOST" in a._authenticated

    def test_local_dir_lists_entries_without_failure(self) -> None:
        a = WindowsFileBrowserAdapter()
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "clip_a.mp4").write_text("x")
            (Path(tmp) / "sub").mkdir()
            listing = a.list_directory(tmp)
        names = sorted(e.name for e in listing.entries)
        assert names == ["clip_a.mp4", "sub"]
        assert listing.failed is False

    def test_missing_local_dir_flags_failure(self) -> None:
        a = WindowsFileBrowserAdapter()
        listing = a.list_directory(str(Path(tempfile.gettempdir()) / "no_such_dir_xyz_123"))
        assert listing.entries == []
        assert listing.failed is True

    def test_bare_server_with_no_shares_flags_failure(self) -> None:
        a = WindowsFileBrowserAdapter()
        a.connect = lambda server: True
        a.list_shares = lambda server: []
        listing = a.list_directory(r"\\EMPTYHOST")
        assert listing.failed is True


class TestCountDirs:
    def test_counts_subdirs(self) -> None:
        a = WindowsFileBrowserAdapter()
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "a").mkdir()
            (Path(tmp) / "b").mkdir()
            (Path(tmp) / "$hidden").mkdir()
            (Path(tmp) / "file.txt").write_text("x")
            assert a.count_dirs(tmp) == 2

    def test_bad_path_returns_zero(self) -> None:
        a = WindowsFileBrowserAdapter()
        assert a.count_dirs(str(Path(tempfile.gettempdir()) / "nope_xyz")) == 0
