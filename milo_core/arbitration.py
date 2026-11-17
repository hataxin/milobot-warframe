"""Arbitration schedule parsing and Card builders from browse.wf."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .card_model import Card
from .command_flags import page_caption, paginate
from .dictionary import NodeInfo
from .errors import QueryError
from .worldstate import (
    FACTION_INDEX_MAP,
    MISSION_INDEX_MAP,
    QueryMeta,
    compact_faction,
    compact_remaining,
    faction_name,
    format_remaining,
    mission_name,
    node_display,
    subtitle,
)

ARBYS_TTL = 43_200
ARBITRATION_DURATION = 3_600
ARBITRATION_WINDOW = 30 * 86_400
ARBYS_STORE_WINDOW = 35 * 86_400
ARBYS_LIST_LIMIT = 10
WORTH_TIERS = frozenset({"S", "A", "B"})
_UTC_PLUS_8 = timezone(timedelta(hours=8))


def parse_arbys(raw: str, now: float) -> list[list[Any]]:
    """Parse browse.wf/arbys.txt into sorted [activation, node_key] pairs."""
    cutoff = now + ARBYS_STORE_WINDOW
    entries: list[list[Any]] = []
    for line in raw.splitlines():
        cleaned = line.strip()
        if not cleaned:
            continue
        ts_text, sep, node_key = cleaned.partition(",")
        node_key = node_key.strip()
        if not sep or not node_key:
            continue
        try:
            activation = int(ts_text.strip())
        except ValueError:
            continue
        if activation + ARBITRATION_DURATION <= now or activation >= cutoff:
            continue
        entries.append([activation, node_key])
    entries.sort(key=lambda item: int(item[0]))
    if not entries:
        raise QueryError("仲裁排期数据为空或已过期，请稍后重试。")
    return entries


def mission_faction_for_node(info: NodeInfo | None, *, compact: bool = False) -> str:
    """Format mission type and faction from node metadata."""
    if info is None:
        return "未知 · 未知" if compact else "未知 · 未知派系"
    m_code = MISSION_INDEX_MAP.get(info.mission_index) if info.mission_index is not None else None
    f_code = FACTION_INDEX_MAP.get(info.faction_index) if info.faction_index is not None else None
    if compact:
        return f"{compact_faction(f_code)} · {mission_name(m_code)}"
    return f"{mission_name(m_code)} · {faction_name(f_code)}"


def normalized_tier(tiers: dict[str, str], node_key: str) -> str:
    """Return normalized arbitration tier grade S..F or placeholder."""
    if not tiers:
        return "—"
    tier = tiers.get(node_key, "F").strip().upper()
    return tier if tier in {"S", "A", "B", "C", "D", "F"} else "F"


def build_arbitration_card(
    entries: list[list[Any]],
    nodes: dict[str, NodeInfo],
    tiers: dict[str, str],
    meta: QueryMeta,
) -> Card:
    """Build the currently active Arbitration mission Card."""
    active = [
        (int(entry[0]), str(entry[1]))
        for entry in entries
        if int(entry[0]) <= meta.now < int(entry[0]) + ARBITRATION_DURATION
    ]
    if not active:
        return Card(
            "当前仲裁",
            [],
            subtitle(meta),
            columns=("节点", "任务 / 派系", "评级", "剩余时间"),
            kind="arbitration",
            empty_message="当前没有进行中的仲裁数据",
        )
    activation, node_key = min(active, key=lambda item: item[0])
    loc, info = node_display(node_key, nodes)
    tier = normalized_tier(tiers, node_key)
    remaining = format_remaining(float(activation + ARBITRATION_DURATION), meta.now)
    return Card(
        "当前仲裁",
        [(loc, mission_faction_for_node(info), tier, remaining)],
        subtitle(meta),
        columns=("节点", "任务 / 派系", "评级", "剩余时间"),
        kind="arbitration",
    )


def arbitration_summary(
    entries: list[list[Any]],
    nodes: dict[str, NodeInfo],
    tiers: dict[str, str],
    now: float,
) -> tuple[str, str] | None:
    """Return `(status_label, remaining_text)` for the active Arbitration node."""
    active = [
        (int(entry[0]), str(entry[1]))
        for entry in entries
        if int(entry[0]) <= now < int(entry[0]) + ARBITRATION_DURATION
    ]
    if not active:
        return None
    activation, node_key = min(active, key=lambda item: item[0])
    loc, info = node_display(node_key, nodes)
    tier = normalized_tier(tiers, node_key)
    rem = compact_remaining(float(activation + ARBITRATION_DURATION), now)
    return (f"{loc} [{tier}] {mission_faction_for_node(info, compact=True)}", rem)


def build_arbitration_list_card(
    entries: list[list[Any]],
    nodes: dict[str, NodeInfo],
    tiers: dict[str, str],
    meta: QueryMeta,
    *,
    page: int = 1,
    show_all: bool = False,
) -> Card:
    """Build upcoming Arbitration schedule Card (S/A/B by default or all tiers, paginated)."""
    cutoff = meta.now + ARBITRATION_WINDOW
    all_rows: list[tuple[str, ...]] = []
    for entry in entries:
        activation, node_key = int(entry[0]), str(entry[1])
        if not meta.now < activation < cutoff:
            continue
        tier = normalized_tier(tiers, node_key)
        if not show_all and tier not in WORTH_TIERS:
            continue
        loc, info = node_display(node_key, nodes)
        start_text = datetime.fromtimestamp(activation, _UTC_PLUS_8).strftime("%m-%d %H:%M")
        all_rows.append((start_text, loc, mission_faction_for_node(info, compact=True), tier))
    paged, cur_page, total_pages = paginate(all_rows, page, 12)
    scope = "未来 30 天全评级" if show_all else "未来 30 天 S/A/B 级"
    sub = subtitle(meta, *(x for x in (scope, page_caption(cur_page, total_pages)) if x))
    hint = (
        f"共筛选 {len(all_rows)} 条排期（可用 /仲裁表 所有 查看全部评级）"
        if not show_all and all_rows
        else f"共 {len(all_rows)} 条排期"
    )
    return Card(
        "仲裁前瞻表",
        paged,
        sub,
        columns=("开始时间 (UTC+8)", "节点", "派系 / 任务", "评级"),
        kind="arbitration_list",
        empty_message="未来 30 天内暂无符合条件的仲裁排期",
        stats_line=hint,
    )
