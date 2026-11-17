import json
import sqlite3
from contextlib import closing
from pathlib import Path

import httpx
import pytest

from milo_core.cache import ResponseCache
from milo_core.client import MARKET_URL, DataClient
from milo_core.errors import QueryError


def cache_at(path: Path) -> ResponseCache:
    cache = ResponseCache(path)
    cache.initialize()
    return cache


async def test_restart_reuses_persisted_catalogue_without_network(tmp_path: Path) -> None:
    cache = cache_at(tmp_path)
    url = MARKET_URL + "/items"
    cache.put(url, {"data": [{"id": "a", "slug": "a"}]})

    def no_network(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"Unexpected request: {request.url}")

    client = DataClient(cache, httpx.AsyncClient(transport=httpx.MockTransport(no_network)))
    try:
        assert (await client.get(url, "items", 86400)).body["data"][0]["id"] == "a"
    finally:
        await client.close()


async def test_invalid_schema_cannot_replace_last_successful_cache(tmp_path: Path) -> None:
    cache = cache_at(tmp_path)
    url = MARKET_URL + "/items"
    good = {"data": [{"id": "a", "slug": "a"}]}
    cache.put(url, good, fetched_at=1)
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json={"data": "changed"}))
    client = DataClient(cache, httpx.AsyncClient(transport=transport))
    try:
        with pytest.raises(QueryError, match="格式"):
            await client.get(url, "items", 1)
        saved = cache.get(url)
        assert saved is not None and saved.body == good
    finally:
        await client.close()


@pytest.mark.parametrize("status", [429, 500])
async def test_failed_upstream_is_not_an_empty_success(tmp_path: Path, status: int) -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(status, json={"data": []}))
    client = DataClient(cache_at(tmp_path), httpx.AsyncClient(transport=transport))
    try:
        with pytest.raises(QueryError):
            await client.get(MARKET_URL + "/orders/item/a", "orders", 60)
    finally:
        await client.close()


def test_corrupt_cache_is_removed_without_destroying_other_entries(tmp_path: Path) -> None:
    cache = cache_at(tmp_path)
    cache.put("good", {"data": []})
    with closing(sqlite3.connect(cache.path)) as connection:
        connection.execute("INSERT INTO responses VALUES ('broken', ?, 1)", ("not-json",))
        connection.commit()
    assert cache.get("broken") is None
    good = cache.get("good")
    assert good is not None and json.dumps(good.body) == '{"data": []}'
