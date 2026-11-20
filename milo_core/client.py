"""Instance-owned HTTP access, cache validation and market request pacing."""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any, Literal

import httpx

from .cache import CachedResponse, ResponseCache
from .errors import QueryError

_LOGGER = logging.getLogger("plugin.warframe.client")
PayloadKind = Literal["worldstate", "items", "orders", "alias", "detail"]
MARKET_URL = "https://api.warframe.market/v2"
ITEM_STATS_URL = "https://api.warframe.market/v1/items/{slug}/statistics"
DUCATS_URL = "https://api.warframe.market/v1/tools/ducats"
AUCTIONS_SEARCH_URL = "https://api.warframe.market/v1/auctions/search"
WORLDSTATE_URL = "https://api.warframe.com/cdn/worldState.php"
ALIAS_URL = "https://kingprimes.top/warframe/alias.json"
PUBLIC_EXPORT_INDEX_URL = "https://origin.warframe.com/PublicExport/index_zh.txt.lzma"
PUBLIC_EXPORT_MANIFEST_URL = "https://content.warframe.com/PublicExport/Manifest/"
ARBYS_URL = "https://browse.wf/arbys.txt"
CDN_MIRRORS: tuple[str, ...] = (
    "https://testingcf.jsdelivr.net/gh/KingPrimes/DataSource@latest/warframe/",
    "https://cdn.jsdelivr.net/gh/KingPrimes/DataSource@latest/warframe/",
    "https://jsd.onmicrosoft.cn/gh/KingPrimes/DataSource@latest/warframe/",
    "https://kingprimes.top/warframe/",
)


def validate_payload(kind: PayloadKind, body: Any) -> None:
    """Reject changed schemas before replacing a successful cached response."""
    if kind == "alias":
        valid = isinstance(body, list)
    elif kind == "worldstate":
        valid = isinstance(body, dict) and isinstance(body.get("SyndicateMissions"), list)
    else:
        expected = dict if kind == "detail" else list
        valid = (
            isinstance(body, dict)
            and not body.get("error")
            and isinstance(body.get("data"), expected)
        )
        if valid and kind == "items":
            valid = bool(body["data"])
    if not valid:
        raise QueryError(f"{kind} 数据格式已变化，暂时不能使用；请检查日志或更新插件。")


class DataClient:
    """Own one HTTP client and serialize concurrent requests for the same resource."""

    def __init__(self, cache: ResponseCache, http: httpx.AsyncClient) -> None:
        self.cache = cache
        self.http = http
        self._memory: dict[str, CachedResponse] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._market_lock = asyncio.Lock()
        self._last_market_at = 0.0

    async def close(self) -> None:
        """Release only the HTTP resources belonging to this plugin instance."""
        await self.http.aclose()
        self._memory.clear()

    async def get(self, url: str, kind: PayloadKind, ttl: float) -> CachedResponse:
        """Fetch validated JSON, using fresh cache and propagating upstream failures."""
        lock = self._locks.setdefault(url, asyncio.Lock())
        async with lock:
            cached = self._memory.get(url)
            persist = kind in {"worldstate", "items", "alias"}
            if cached is None and persist:
                cached = await asyncio.to_thread(self.cache.get, url)
            if cached is not None and 0 <= time.time() - cached.fetched_at < ttl:
                try:
                    validate_payload(kind, cached.body)
                except QueryError:
                    pass  # A cached response from an older schema is not usable.
                else:
                    self._memory[url] = cached
                    return cached
            if url.startswith("https://api.warframe.market/"):
                await self._pace_market()
            body = await self._request(url)
            validate_payload(kind, body)
            fresh = CachedResponse(body, time.time())
            if persist:
                await asyncio.to_thread(self.cache.put, url, body, fetched_at=fresh.fetched_at)
            self._memory[url] = fresh
            return fresh

    async def get_or_build(
        self,
        key: str,
        ttl: float,
        builder: Callable[[], Awaitable[Any]],
        *,
        persist: bool = True,
    ) -> CachedResponse:
        """Return a fresh cached value or compute, validate and persist it once."""
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            cached = self._memory.get(key)
            if cached is None and persist:
                cached = await asyncio.to_thread(self.cache.get, key)
            if cached is not None and 0 <= time.time() - cached.fetched_at < ttl:
                self._memory[key] = cached
                return cached
            value = await builder()
            fresh = CachedResponse(value, time.time())
            if persist:
                await asyncio.to_thread(self.cache.put, key, value, fetched_at=fresh.fetched_at)
            self._memory[key] = fresh
            return fresh

    async def fetch_bytes(self, url: str) -> bytes:
        """Fetch raw bytes from an upstream URL, turning network errors into QueryError."""
        return (await self._request_response(url)).content

    async def fetch_text(self, url: str) -> str:
        """Fetch UTF-8 text from an upstream URL, turning network errors into QueryError."""
        return (await self._request_response(url)).text

    async def fetch_json(self, url: str) -> Any:
        """Fetch and decode JSON from an arbitrary URL."""
        return await self._request(url)

    async def fetch_market_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Any:
        """Fetch Warframe Market JSON respecting the market rate limiter."""
        await self._pace_market()
        return await self._request(url, params=params, extra_headers=extra_headers)

    async def fetch_cdn_json(self, filename: str) -> Any:
        """Fetch JSON from KingPrimes DataSource mirrors with ordered fallback."""
        last_error: QueryError | None = None
        for base in CDN_MIRRORS:
            try:
                return await self._request(base + filename)
            except QueryError as exc:
                last_error = exc
        raise last_error or QueryError(f"无法获取 CDN 数据：{filename}")

    async def _pace_market(self) -> None:
        async with self._market_lock:
            loop = asyncio.get_running_loop()
            wait = self._last_market_at + 0.35 - loop.time()
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_market_at = loop.time()

    async def _request_response(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        try:
            response = await self.http.get(url, params=params, headers=extra_headers)
            if response.status_code == 429:
                raise QueryError("数据源暂时限流，请稍后再查询。")
            response.raise_for_status()
            return response
        except httpx.TimeoutException as exc:
            _LOGGER.warning("数据源请求超时: url=%s err=%s", url, type(exc).__name__)
            raise QueryError(
                "数据源请求超时，请检查网络代理（可在插件配置中设置 proxy_url）或稍后重试。"
            ) from exc
        except httpx.HTTPError as exc:
            _LOGGER.warning("无法访问数据源: url=%s err=%s", url, exc)
            raise QueryError(
                "无法访问数据源，请检查网络代理（可在插件配置中设置 proxy_url）或稍后重试。"
            ) from exc

    async def _request(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Any:
        response = await self._request_response(url, params=params, extra_headers=extra_headers)
        try:
            return response.json()
        except ValueError as exc:
            raise QueryError("数据源没有返回有效 JSON，请稍后重试。") from exc
