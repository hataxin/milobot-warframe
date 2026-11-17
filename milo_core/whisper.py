"""In-game Warframe Market whisper templates and instance-owned pick store."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from .errors import QueryError
from .market import Order

WHISPER_TTL_SECONDS = 120.0
_CN_LOCALE_CODES = frozenset({"zh", "zh-hans", "zh-hant", "zh-cn", "zh-tw"})
_WM_TAG = "(warframe.market)"

_ELEMENT_ZH: dict[str, str] = {
    "impact": "冲击",
    "heat": "火焰",
    "cold": "冰冻",
    "electricity": "电击",
    "toxin": "毒素",
    "magnetic": "磁力",
    "radiation": "辐射",
}
_ELEMENT_EN: dict[str, str] = {key: key.capitalize() for key in _ELEMENT_ZH}


@dataclass(frozen=True)
class WhisperEntry:
    """One formatted `/w` copy-paste line mapped to a market card row."""

    ingame_name: str
    locale: str
    lang: str
    text: str
    status: str = ""


@dataclass(frozen=True)
class _PickBucket:
    expires_at: float
    source: str
    entries: tuple[WhisperEntry, ...]


def pick_lang(locale: str | None, fallback: str = "en") -> str:
    """Select Chinese template when seller locale indicates Chinese, else English."""
    if locale is None or not locale:
        return fallback
    return "zh" if str(locale).strip().casefold() in _CN_LOCALE_CODES else "en"


def element_label(element: str | None, lang: str) -> str:
    """Translate Lich/Sister element key into Chinese or English label."""
    if element is None or not element:
        return ""
    norm = element.strip().casefold()
    if lang == "zh":
        return _ELEMENT_ZH.get(norm, element)
    return _ELEMENT_EN.get(norm, element.title())


def _parse_auction_seller(
    owner: dict[str, Any], weapon_zh: str, weapon_en: str
) -> tuple[str, str, str, str, str] | None:
    player = str(owner.get("ingame_name") or "").strip()
    if not player:
        return None
    locale = str(owner.get("locale") or "")
    lang = pick_lang(locale)
    weapon = (weapon_zh or weapon_en) if lang == "zh" else (weapon_en or weapon_zh)
    status = str(owner.get("status") or "")
    return player, locale, lang, weapon, status


def order_whisper(
    order: Order,
    name_zh: str,
    name_en: str,
    *,
    buyer: bool,
    fallback: str = "en",
) -> WhisperEntry:
    """Build `/w` chat string matching Warframe Market order conventions."""
    lang = pick_lang(order.locale, fallback)
    item_name = (name_en if lang == "en" else name_zh) or name_zh or name_en
    qty_prefix = f"x{order.quantity} " if order.quantity > 1 else ""
    if lang == "zh":
        verb = "出售" if buyer else "购买"
        rank_part = f" (等级 {order.rank})" if order.rank is not None else ""
        text = (
            f"/w {order.player} 你好! 我想以{order.price}白金{verb}: "
            f'{qty_prefix}"{item_name}{rank_part}"。{_WM_TAG}'
        )
    else:
        verb = "sell" if buyer else "buy"
        rank_part = f" (rank {order.rank})" if order.rank is not None else ""
        text = (
            f"/w {order.player} Hi! I want to {verb}: "
            f'{qty_prefix}"{item_name}{rank_part}" for {order.price} platinum. {_WM_TAG}'
        )
    return WhisperEntry(order.player, order.locale, lang, text, order.status)


def riven_whisper(
    owner: dict[str, Any],
    riven_name: str,
    weapon_zh: str,
    weapon_en: str,
) -> WhisperEntry | None:
    """Build `/w` chat string for a Warframe Market Riven auction."""
    parsed = _parse_auction_seller(owner, weapon_zh, weapon_en)
    if parsed is None:
        return None
    player, locale, lang, weapon, status = parsed
    suffix = riven_name.strip().capitalize()
    if lang == "zh":
        text = f"/w {player} 你好! 我想购买你的「{weapon}」紫卡 {suffix}".rstrip()
    else:
        text = f'/w {player} Hi! I want to buy your {weapon} riven "{suffix}"'
    return WhisperEntry(player, locale, lang, text, status)


def lich_whisper(
    owner: dict[str, Any],
    item: dict[str, Any],
    weapon_zh: str,
    weapon_en: str,
) -> WhisperEntry | None:
    """Build `/w` chat string for a Kuva Lich or Tenet Sister auction."""
    parsed = _parse_auction_seller(owner, weapon_zh, weapon_en)
    if parsed is None:
        return None
    player, locale, lang, weapon, status = parsed
    elem = element_label(str(item.get("element") or ""), lang)
    damage = item.get("damage")
    has_ephemera = bool(item.get("having_ephemera"))
    traits: list[str] = []
    if damage is not None and elem:
        traits.append(f"（{damage}% {elem}）" if lang == "zh" else f" ({damage}% {elem})")
    if has_ephemera:
        traits.append("（带幻纹）" if lang == "zh" else " (with Ephemera)")
    detail = "".join(traits)
    greeting = (
        f"你好! 我想购买你的「{weapon}」" if lang == "zh" else f"Hi! I want to buy your {weapon}"
    )
    return WhisperEntry(player, locale, lang, f"/w {player} {greeting}{detail}", status)


class WhisperStore:
    """Per-instance cache mapping `(stream_id, user_id)` to recent `/w` entries."""

    def __init__(self, ttl: float = WHISPER_TTL_SECONDS) -> None:
        self._ttl = ttl
        self._buckets: dict[tuple[str, str], _PickBucket] = {}

    def clear(self) -> None:
        """Discard all transient whisper entries on plugin unload."""
        self._buckets.clear()

    def remember(
        self,
        stream_id: str,
        user_id: str,
        source: str,
        entries: list[WhisperEntry],
    ) -> None:
        """Store numbered whisper entries scoped to stream + sender."""
        now = time.monotonic()
        self._buckets = {
            k: bucket for k, bucket in self._buckets.items() if bucket.expires_at > now
        }
        if not entries:
            return
        if len(self._buckets) >= 256:
            self._buckets.pop(next(iter(self._buckets)))
        self._buckets[(stream_id, user_id)] = _PickBucket(now + self._ttl, source, tuple(entries))

    def reply_for(self, stream_id: str, user_id: str, raw_arg: str) -> str:
        """Resolve `/w <序号>` into a ready-to-paste whisper line or helpful error."""
        text = raw_arg.strip()
        if not text:
            return (
                "用法：/w <序号>\n序号对应最近一次 /wm、/wr、/cd、/xt 查询卡片行号，2 分钟内有效。"
            )
        head = text.split(maxsplit=1)[0]
        if not head.isdigit():
            raise QueryError(f"“{head}”不是有效序号，请输入数字，例如：/w 1。")
        index = int(head)
        bucket = self._buckets.get((stream_id, user_id))
        if bucket is None or bucket.expires_at <= time.monotonic():
            self._buckets.pop((stream_id, user_id), None)
            raise QueryError("当前没有可用的私聊记录，请先用 /wm、/wr、/cd 或 /xt 查询。")
        total = len(bucket.entries)
        if not 1 <= index <= total:
            raise QueryError(f"序号超出范围：当前共 {total} 条，请回复 /w 1～{total}。")
        entry = bucket.entries[index - 1]
        if entry.status == "offline":
            return f"{entry.text}\n（对方当前离线，可能收不到）"
        return entry.text
