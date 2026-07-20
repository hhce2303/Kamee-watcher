"""OneDriveGraphAdapter — documented deferred stub (CloudSharePort).

Every method must raise NotImplementedError until Azure AD credentials exist
(see the class docstring's activation checklist) — accidental wiring should
fail loudly, never silently no-op. These tests lock down that contract so a
future edit can't accidentally turn a raise into a silent pass.
"""
from __future__ import annotations

import pytest

from app.adapters.cloud.onedrive_graph_adapter import OneDriveGraphAdapter


class TestOneDriveGraphAdapterIsADeferredStub:
    def _adapter(self) -> OneDriveGraphAdapter:
        return OneDriveGraphAdapter(client_id="client", tenant_id="tenant")

    def test_ensure_folder_raises_not_implemented(self) -> None:
        with pytest.raises(NotImplementedError):
            self._adapter().ensure_folder("SLC/clips-supervisor/2026-06")

    def test_create_share_link_raises_not_implemented(self) -> None:
        with pytest.raises(NotImplementedError):
            self._adapter().create_share_link("SLC/clips-supervisor/2026-06")

    def test_web_url_raises_not_implemented(self) -> None:
        with pytest.raises(NotImplementedError):
            self._adapter().web_url("SLC/clips-supervisor/2026-06")

    def test_stores_constructor_args_without_side_effects(self) -> None:
        token_provider = lambda: "token"  # noqa: E731
        adapter = OneDriveGraphAdapter(
            client_id="abc", tenant_id="def", token_provider=token_provider
        )
        assert adapter._client_id == "abc"
        assert adapter._tenant_id == "def"
        assert adapter._token_provider is token_provider
