"""Ducats gold/silver junk ranking from Warframe Market v1 tools/ducats."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from .card_model import Card
from .errors import QueryError
from .worldstate import QueryMeta, subtitle


@dataclass(frozen=True)
class DucatItem:
    """One ranked Ducat trade entry."""

    item_id: str
    name: str
    ducats: int
    dpp_wa: float
    wa_price: float
    volume: int


def _filter_ranked(
    raw_items: Any,
    kind: Literal["gold", "silver", "copper"],
    name_map: dict[str, str],
) -> list[DucatItem]:
    if not isinstance(raw_items, list):
        return []
    matched: list[DucatItem] = []
    for entry in raw_items:
        if not isinstance(entry, dict):
            continue
        ducats = entry.get("ducats")
        if type(ducats) is not int:
            continue
        if kind == "gold" and ducats != 100:
            continue
        if kind == "silver" and not (45 <= ducats < 100):
            continue
        if kind == "copper" and not (15 <= ducats < 45):
            continue
        item_id = str(entry.get("item") or "").strip()
        if not item_id:
            continue
        dpp_raw = entry.get("ducats_per_platinum_wa") or entry.get("ducats_per_platinum") or 0
        wa_raw = entry.get("wa_price") or entry.get("median") or 0
        vol_raw = entry.get("volume") or 0
        matched.append(
            DucatItem(
                item_id=item_id,
                name=name_map.get(item_id, item_id),
                ducats=ducats,
                dpp_wa=float(dpp_raw),
                wa_price=float(wa_raw),
                volume=int(vol_raw),
            )
        )
    matched.sort(key=lambda item: item.dpp_wa, reverse=True)
    return matched[:10]


def build_ducats_card(
    kind: Literal["gold", "silver", "copper"],
    body: Any,
    name_map: dict[str, str],
    meta: QueryMeta,
) -> Card:
    """Build gold (`100`), silver (`45-99`), or copper (`15-44`) ducat junk ranking Card."""
    payload = body.get("payload") if isinstance(body, dict) else None
    if not isinstance(payload, dict):
        raise QueryError("杜卡德垃圾数据格式已变化，请稍后重试。")
    day_items = _filter_ranked(payload.get("previous_day"), kind, name_map)
    hour_items = _filter_ranked(payload.get("previous_hour"), kind, name_map)
    rows: list[tuple[str, ...]] = [
        ("当天", it.name, str(it.ducats), f"{it.dpp_wa:.2f}", f"{it.wa_price:.1f} / {it.volume}")
        for it in day_items
    ] + [
        ("每小时", it.name, str(it.ducats), f"{it.dpp_wa:.2f}", f"{it.wa_price:.1f} / {it.volume}")
        for it in hour_items
    ]
    titles = {
        "gold": "杜卡德金垃圾排行",
        "silver": "杜卡德银垃圾排行",
        "copper": "杜卡德铜垃圾排行",
    }
    highlights = {
        "gold": "筛选条件：100 杜卡德币",
        "silver": "筛选条件：45 ～ 99 杜卡德币",
        "copper": "筛选条件：15 ～ 44 杜卡德币",
    }
    title = titles[kind]
    return Card(
        title,
        rows,
        subtitle(meta),
        columns=("时段", "物品名称", "杜卡德", "性价比", "均价 / 库存"),
        kind="ducats",
        empty_message=f"当前没有符合条件的{title}数据",
        highlight=highlights[kind],
    )
