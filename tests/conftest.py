import importlib.util
import ssl
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from types import ModuleType
from typing import Any

import httpx
import pytest
from maibot_sdk.context import PluginContext, PluginPaths

_ORIGINAL_ASYNC_CLIENT = httpx.AsyncClient
_SHARED_TEST_SSL = ssl.create_default_context()


class _FastTestAsyncClient(_ORIGINAL_ASYNC_CLIENT):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("verify", _SHARED_TEST_SSL)
        kwargs.setdefault("trust_env", False)
        super().__init__(*args, **kwargs)


@pytest.fixture(autouse=True)
def _fast_test_httpx_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "AsyncClient", _FastTestAsyncClient)


@pytest.fixture
def plugin_module(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    root = Path(__file__).resolve().parents[1]
    name = "milobot_sdk_test_package"
    spec = importlib.util.spec_from_file_location(
        name, root / "plugin.py", submodule_search_locations=[str(root)]
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
async def loaded_plugin(
    plugin_module: ModuleType, tmp_path: Path
) -> AsyncIterator[tuple[Any, list[dict[str, Any]]]]:
    calls: list[dict[str, Any]] = []

    async def rpc(
        method: str, plugin_id: str, payload: dict[str, Any] | None, **kwargs: Any
    ) -> Any:
        del kwargs
        assert method == "cap.call" and plugin_id == "local.milobot-warframe"
        assert payload is not None
        calls.append(payload)
        return {"success": True}

    plugin = plugin_module.create_plugin()
    plugin.set_plugin_config({})
    plugin._set_context(
        PluginContext(
            "local.milobot-warframe", rpc, PluginPaths(tmp_path / "data", tmp_path / "temp")
        )
    )
    await plugin.on_load()
    try:
        yield plugin, calls
    finally:
        await plugin.on_unload()
