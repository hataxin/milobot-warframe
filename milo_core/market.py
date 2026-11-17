"""Item lookup and Warframe Market v2 order filtering for Milo bot."""

import re
import unicodedata
from dataclasses import dataclass, replace
from typing import Any

from .errors import QueryError


@dataclass(frozen=True)
class Item:
    """The market fields required by item matching and rank filtering."""

    item_id: str
    slug: str
    name: str
    english_name: str
    max_rank: int | None = None


@dataclass(frozen=True)
class MarketQuery:
    """A PC order query after removing standalone flags."""

    keyword: str
    buyer: bool = False
    max_rank: bool = False


@dataclass(frozen=True)
class Order:
    """A visible order from an online player."""

    player: str
    price: int
    quantity: int
    status: str
    rank: int | None
    locale: str = "en"


def normalize(text: str) -> str:
    """Normalize names and Chinese Prime shorthand without damaging English names."""
    text = unicodedata.normalize("NFKC", text).casefold().strip()
    text = re.sub(r"(?<=[\u3400-\u9fff])p$|\bp$", "prime", text)
    text = text.replace("一套", "set")
    return re.sub(r"[\s_·.\-]+", "", text)


def parse_query(text: str) -> MarketQuery:
    """Parse buyer/MAX flags while preserving multiword item names.

    English flags are standalone tokens; names such as Maxim must survive.
    Only the international PC market is included in this first release.
    """
    words = text.split()
    flags = {word.casefold() for word in words}
    unsupported = {"ps4", "ps5", "xbox", "xb1", "switch", "swi", "mobile", "cn", "国服"}
    if flags & unsupported:
        raise QueryError("此首版仅支持国际服 PC 市场，其他平台尚未接入。")
    buyer = bool(flags & {"买家", "购买", "buy"})
    seller = bool(flags & {"卖家", "出售", "sell"})
    if buyer and seller:
        raise QueryError("买家和卖家只能选择一种。")
    reserved = {"pc", "买家", "购买", "buy", "卖家", "出售", "sell", "满级", "max"}
    keyword = " ".join(word for word in words if word.casefold() not in reserved)
    if not keyword:
        raise QueryError("用法：/wm 物品名称 [买家|卖家] [满级]，例如 /wm 压迫点p 满级。")
    return MarketQuery(keyword, buyer, bool(flags & {"满级", "max"}))


def parse_items(payload: dict[str, Any]) -> list[Item]:
    """Decode the v2 multilingual item catalogue."""
    items: list[Item] = []
    for raw in payload["data"]:
        if not isinstance(raw, dict) or not raw.get("id") or not raw.get("slug"):
            continue
        localized = raw.get("i18n") or {}
        chinese = (localized.get("zh-hans") or {}).get("name")
        english = (localized.get("en") or {}).get("name") or raw["slug"].replace("_", " ")
        items.append(
            Item(
                str(raw["id"]),
                str(raw["slug"]),
                str(chinese or english),
                str(english),
                raw.get("maxRank"),
            )
        )
    if not items:
        raise QueryError("市场物品索引为空或格式已变化，请稍后重试。")
    return items


def resolve_item(keyword: str, items: list[Item], aliases: dict[str, str]) -> list[Item]:
    """Resolve exact names, aliases and Prime sets, otherwise return candidates."""
    key = normalize(keyword)
    exact = [item for item in items if key in _item_keys(item)]
    if exact:
        return exact[:15]
    # Alias values are base names (e.g. 电男 -> Volt), before Prime expansion.
    base = key.removesuffix("prime")
    alias = aliases.get(base)
    search = normalize(alias) if alias is not None else base
    sets = [
        item
        for item in items
        if item.slug.endswith("_prime_set")
        and search
        in {
            normalize(item.english_name).removesuffix("primeset"),
            normalize(item.name).removesuffix("primeset"),
        }
    ]
    if sets:
        return sets[:15]
    keys = {key, search}
    partial = [
        item for item in items if any(k and k in name for k in keys for name in _item_keys(item))
    ]
    return sorted(partial, key=lambda item: (len(item.name), item.name))[:15]


def _item_keys(item: Item) -> set[str]:
    return {normalize(item.name), normalize(item.english_name), normalize(item.slug)}


def enrich_item(item: Item, payload: dict[str, Any]) -> Item:
    """Use item/set details when the catalogue does not include a Mod's max rank."""
    for detail in payload["data"].get("items", []):
        if detail.get("id") == item.item_id:
            maximum = detail.get("maxRank")
            if isinstance(maximum, int) and not isinstance(maximum, bool):
                return replace(item, max_rank=maximum)
    return item


def _parse_order(raw: Any, item: Item, query: MarketQuery) -> Order | None:
    if not isinstance(raw, dict) or raw.get("visible") is False:
        return None
    user = raw.get("user")
    if not isinstance(user, dict) or user.get("status") not in {"online", "ingame"}:
        return None
    if raw.get("itemId") != item.item_id or raw.get("type") != ("buy" if query.buyer else "sell"):
        return None
    rank = raw.get("rank")
    if query.max_rank and (rank is None or rank != item.max_rank):
        return None
    price, quantity, player = raw.get("platinum"), raw.get("quantity"), user.get("ingameName")
    if (
        type(price) is not int
        or price < 0
        or type(quantity) is not int
        or quantity < 1
        or not isinstance(player, str)
        or not player.strip()
    ):
        return None
    locale = str(user.get("locale") or "en")
    return Order(player, price, quantity, user["status"], rank, locale)


def filter_all_orders(payload: dict[str, Any], item: Item, query: MarketQuery) -> list[Order]:
    """Select all online visible orders sorted sells low-first or buys high-first."""
    if query.max_rank and item.max_rank is None:
        raise QueryError("该物品缺少满级信息，无法可靠筛选；请移除“满级”后查询。")
    orders = [order for raw in payload["data"] if (order := _parse_order(raw, item, query))]
    return sorted(orders, key=lambda order: order.price, reverse=query.buyer)


def filter_orders(
    payload: dict[str, Any], item: Item, query: MarketQuery, *, limit: int = 8
) -> list[Order]:
    """Select top online visible orders and sort sells low-first or buys high-first."""
    return filter_all_orders(payload, item, query)[:limit]


def _summarize_window(entries: Any) -> str | None:
    if not isinstance(entries, list) or not entries:
        return None
    total_vol = 0
    weighted = 0.0
    lows: list[float] = []
    highs: list[float] = []
    for row in entries:
        if not isinstance(row, dict):
            continue
        vol = row.get("volume")
        price = row.get("wa_price") if row.get("wa_price") is not None else row.get("avg_price")
        if isinstance(vol, (int, float)) and isinstance(price, (int, float)) and vol > 0:
            total_vol += int(vol)
            weighted += float(price) * float(vol)
        lo = row.get("min_price")
        hi = row.get("max_price")
        if isinstance(lo, (int, float)):
            lows.append(float(lo))
        if isinstance(hi, (int, float)):
            highs.append(float(hi))
    if total_vol <= 0 and not lows:
        return None
    avg_val = weighted / total_vol if total_vol > 0 else (sum(lows) / len(lows))
    lo_text = f"{min(lows):g}" if lows else "-"
    hi_text = f"{max(highs):g}" if highs else "-"
    return f"均价 {avg_val:.1f}p ({lo_text}~{hi_text}p · 成交 {total_vol})"


def parse_wm_stats(body: Any) -> str:
    """Summarize Warframe Market `/v1/items/{slug}/statistics` 48h and 90d windows."""
    payload = body.get("payload") if isinstance(body, dict) else None
    closed = payload.get("statistics_closed") if isinstance(payload, dict) else None
    if not isinstance(closed, dict):
        return ""
    parts: list[str] = []
    for key, label in (("48hours", "48h"), ("90days", "90d")):
        summary = _summarize_window(closed.get(key))
        if summary is not None and summary:
            parts.append(f"{label}：{summary}")
    return "  |  ".join(parts)
