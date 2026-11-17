"""Pure-local Warframe calculators & bidirectional dictionary/relic-value cards."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .card_model import Card
from .command_flags import page_caption, paginate
from .dictionary import NodeInfo, RelicEntry, TranslationIndex, split_camel_case, strip_markup
from .errors import QueryError
from .market import Item, normalize
from .worldstate import (
    VOID_TIERS,
    QueryMeta,
    node_display,
    node_mission_faction,
    parse_mongo_time,
    subtitle,
)

_FAST_MISSIONS: frozenset[str] = frozenset(
    {"MT_CAPTURE", "MT_EXTERMINATE", "MT_RESCUE", "MT_SABOTAGE"}
)

_RARITY_COSTS: dict[str, tuple[str, int, int, int]] = {
    "铜": ("铜卡 (普通)", 10, 483, 10),
    "普通": ("铜卡 (普通)", 10, 483, 10),
    "common": ("铜卡 (普通)", 10, 483, 10),
    "银": ("银卡 (罕见)", 20, 966, 10),
    "罕见": ("银卡 (罕见)", 20, 966, 10),
    "uncommon": ("银卡 (罕见)", 20, 966, 10),
    "金": ("金卡 (稀有)", 30, 1449, 10),
    "稀有": ("金卡 (稀有)", 30, 1449, 10),
    "rare": ("金卡 (稀有)", 30, 1449, 10),
    "传奇": ("传奇 / 紫卡", 40, 1932, 10),
    "p卡": ("传奇 / 紫卡", 40, 1932, 10),
    "prime": ("传奇 / 紫卡", 40, 1932, 10),
    "紫卡": ("传奇 / 紫卡", 40, 1932, 10),
    "umbral": ("传奇 / 紫卡", 40, 1932, 10),
}


@dataclass(frozen=True)
class RelicValuationContext:
    """Bundled catalog + pricing inputs for `/开核桃` evaluation."""

    ws: dict[str, Any]
    nodes: dict[str, NodeInfo]
    relics: list[RelicEntry]
    items: list[Item]
    ducats_body: Any


def _collect_translation_hits(
    keyword: str,
    trans: TranslationIndex,
    items: list[Item],
    aliases: dict[str, str],
) -> list[tuple[int, str, str, str]]:
    raw_kw = keyword.strip()
    norm_kw = normalize(raw_kw)
    alias_val = aliases.get(norm_kw)
    alias_norm = normalize(alias_val) if alias_val is not None and alias_val else ""
    search_keys = {k for k in (norm_kw, alias_norm) if k}
    seen: set[tuple[str, str]] = set()
    hits: list[tuple[int, str, str, str]] = []
    _scan_market_items(items, search_keys, seen, hits)
    _scan_export_names(trans, search_keys, seen, hits)
    hits.sort(key=lambda row: (row[0], len(row[1]), row[1]))
    return hits


def _scan_market_items(
    items: list[Item],
    search_keys: set[str],
    seen: set[tuple[str, str]],
    hits: list[tuple[int, str, str, str]],
) -> None:
    for item in items:
        zh_n, en_n = normalize(item.name), normalize(item.english_name)
        if any(k in (zh_n, en_n) for k in search_keys):
            score = 0
        elif any(k in zh_n or k in en_n for k in search_keys):
            score = 1
        else:
            continue
        pair = (item.name, item.english_name)
        if pair not in seen:
            seen.add(pair)
            hits.append((score, item.name, item.english_name, "WM 市场"))


def _scan_export_names(
    trans: TranslationIndex,
    search_keys: set[str],
    seen: set[tuple[str, str]],
    hits: list[tuple[int, str, str, str]],
) -> None:
    for unique_name, raw_zh in trans.names.items():
        zh_name = strip_markup(raw_zh)
        if not zh_name or zh_name.startswith("/"):
            continue
        en_guess = split_camel_case(unique_name.rsplit("/", 1)[-1])
        zh_n, en_n = normalize(zh_name), normalize(en_guess)
        if any(k in (zh_n, en_n) for k in search_keys):
            score = 0
        elif any(k in zh_n or k in en_n for k in search_keys):
            score = 2
        else:
            continue
        pair = (zh_name, en_guess)
        if pair not in seen:
            seen.add(pair)
            hits.append((score, zh_name, en_guess, "官方导出"))


def build_translate_card(
    keyword: str,
    trans: TranslationIndex,
    items: list[Item],
    aliases: dict[str, str],
    meta: QueryMeta,
    *,
    page: int = 1,
) -> Card:
    """Build bidirectional EN<->ZH dictionary Card from WM items & PublicExport."""
    cleaned = keyword.strip()
    if not cleaned:
        raise QueryError("请输入要翻译的中/英文词条，例如：/翻译 Volt 或 /翻译 狂暴化。")
    hits = _collect_translation_hits(cleaned, trans, items, aliases)
    paged, cur_page, total_pages = paginate(hits, page, 12)
    rows: list[tuple[str, ...]] = [(zh, en, source) for _, zh, en, source in paged]
    extra = [x for x in (f"词条: {cleaned}", page_caption(cur_page, total_pages)) if x]
    return Card(
        "中英词典检索",
        rows,
        subtitle(meta, *extra),
        columns=("中文名称", "英文名称", "来源"),
        kind="translate",
        empty_message=f"未找到与“{cleaned}”相关的中英文词条",
        stats_line=f"共匹配 {len(hits)} 条结果",
    )


def _simulate_fusion(start_pct: float, donor_pct: float, target_pct: float) -> list[float]:
    val = start_pct
    steps: list[float] = []
    while val < target_pct and len(steps) < 15:
        base = max(val, donor_pct)
        nxt = min(60.0, round(base * 1.1, 1))
        if nxt >= 58.0:
            nxt = 60.0
        if nxt <= val:
            break
        val = nxt
        steps.append(val)
    return steps


def build_fusion_card(raw_args: str, meta: QueryMeta) -> Card:
    """Calculate Kuva/Tenet Valence Fusion step count from current% to target%."""
    nums = [float(m.group(1)) for m in re.finditer(r"(\d+(?:\.\d+)?)", raw_args)]
    if not nums:
        raise QueryError("用法：/融合 <当前加成%> [目标加成%]，例如：/融合 25 或 /融合 38.5 60。")
    current = nums[0]
    target = nums[1] if len(nums) >= 2 else 60.0
    if not 25.0 <= current <= 60.0 or not current <= target <= 60.0:
        raise QueryError("加成范围须满足 25% ≤ 当前 ≤ 目标 ≤ 60%。")
    if current >= target:
        return Card(
            "赤毒 / 信条武器融合计算",
            [("已达标", f"{current:g}%", f"已满足目标 {target:g}%")],
            subtitle(meta),
            columns=("状态", "当前加成", "说明"),
            kind="fusion",
        )
    worst = _simulate_fusion(current, 25.0, target)
    mid = _simulate_fusion(current, 40.0, target)
    high = _simulate_fusion(current, 50.0, target)
    rows: list[tuple[str, ...]] = [
        ("§25% 胚子逐次合成路线", "", ""),
    ]
    prev = current
    for idx, val in enumerate(worst, 1):
        gain = val - prev
        rows.append((f"第 {idx} 次", f"{prev:g}% → {val:g}%", f"+{gain:.1f}%"))
        prev = val
    banner = f"从 {current:g}% 升至 {target:g}% 预计所需胚子数量"
    stats_line = (
        f"胚子参考数量：25%胚×{len(worst)}把  ·  40%胚×{len(mid)}把  ·  50%胚×{len(high)}把"
    )
    return Card(
        "赤毒 / 信条武器融合计算",
        rows,
        subtitle(meta),
        columns=("次数", "合成后加成", "单次提升"),
        kind="fusion",
        highlight=banner,
        stats_line=stats_line,
    )


def _arcane_cost_card(target_rank: int, meta: QueryMeta) -> Card:
    rank = max(0, min(5, target_rank))
    rows: list[tuple[str, ...]] = [
        (f"Rank {r}", f"{r + 1} 张", f"{(r + 1) * (r + 2) // 2} 张") for r in range(rank + 1)
    ]
    total = (rank + 1) * (rank + 2) // 2
    return Card(
        "赋能等级合成消耗",
        rows,
        subtitle(meta),
        columns=("等级", "本级增量", "累计 0 级赋能"),
        kind="fusion",
        highlight=f"0 级 → Rank {rank} 共需 {total} 个 0 级赋能",
    )


def _mod_overview_card(meta: QueryMeta) -> Card:
    rows = [
        ("铜卡 (普通)", "10,230 内融核心", "494,109 星币 (R0→R10)"),
        ("银卡 (罕见)", "20,460 内融核心", "988,218 星币 (R0→R10)"),
        ("金卡 (稀有)", "30,690 内融核心", "1,482,327 星币 (R0→R10)"),
        ("传奇 / Prime", "40,920 内融核心", "1,976,436 星币 (R0→R10)"),
        ("紫卡 (R8)", "7,650 内融核心", "369,495 星币 (R0→R8)"),
        ("赋能 (R5)", "21 个 0 级赋能", "累计 1+2+3+4+5+6"),
    ]
    return Card(
        "Mod 与赋能升级消耗总览",
        rows,
        subtitle(meta),
        columns=("稀有度 / 类型", "核心 / 数量", "星币 / 说明"),
        kind="fusion",
        stats_line="可用 /升级消耗 <等级> <铜|银|金|传奇|赋能> 查看逐级明细",
    )


def build_upgrade_cost_card(raw_args: str, meta: QueryMeta) -> Card:
    """Calculate Mod Endo/Credits or Arcane copy counts for upgrade targets."""
    cleaned = raw_args.strip()
    if not cleaned:
        return _mod_overview_card(meta)
    low = cleaned.casefold()
    num_matches = [int(m.group(1)) for m in re.finditer(r"(\d+)", cleaned)]
    if "赋能" in low or "arcane" in low:
        return _arcane_cost_card(num_matches[-1] if num_matches else 5, meta)
    rarity_key = next((key for key in _RARITY_COSTS if key in low), "传奇")
    label, base_endo, base_credits, default_max = _RARITY_COSTS[rarity_key]
    start_rank = num_matches[0] if len(num_matches) >= 2 else 0
    end_rank = num_matches[-1] if num_matches else (8 if "紫" in low else default_max)
    end_rank = max(1, min(10, end_rank))
    start_rank = max(0, min(end_rank - 1, start_rank))
    rows: list[tuple[str, ...]] = []
    for r in range(start_rank + 1, end_rank + 1):
        step = 1 << (r - 1)
        rows.append(
            (f"R{r - 1} → R{r}", f"{base_endo * step:,} 核心", f"{base_credits * step:,} 星币")
        )
    factor = (1 << end_rank) - (1 << start_rank)
    total_endo, total_credits = base_endo * factor, base_credits * factor
    return Card(
        f"{label} 升级消耗",
        rows,
        subtitle(meta),
        columns=("升级阶段", "本级内融核心", "本级星币"),
        kind="fusion",
        highlight=f"R{start_rank} → R{end_rank} 合计",
        stats_line=f"总消耗：{total_endo:,} 内融核心  ·  {total_credits:,} 星币",
    )


def _ducat_lookup_maps(ducats_body: Any) -> tuple[dict[str, tuple[int, float]], dict[str, str]]:
    payload = ducats_body.get("payload") if isinstance(ducats_body, dict) else None
    source = (
        payload.get("previous_hour") or payload.get("previous_day") or []
        if isinstance(payload, dict)
        else []
    )
    by_id: dict[str, tuple[int, float]] = {}
    for row in source:
        if not isinstance(row, dict) or not row.get("item"):
            continue
        ducats = row.get("ducats")
        wa_price = row.get("wa_price")
        if isinstance(ducats, (int, float)) and isinstance(wa_price, (int, float)):
            by_id[str(row["item"])] = (int(ducats), float(wa_price))
    return by_id, {}


def _item_price_map(
    items: list[Item],
    by_id: dict[str, tuple[int, float]],
) -> dict[str, tuple[int, float]]:
    by_name: dict[str, tuple[int, float]] = {}
    for item in items:
        if item.item_id in by_id:
            vals = by_id[item.item_id]
            by_name[normalize(item.name)] = vals
            by_name[normalize(item.english_name)] = vals
    return by_name


def _active_fissure_tiers(
    ws: dict[str, Any],
    nodes: dict[str, NodeInfo],
    *,
    fast_only: bool,
    now: float,
) -> tuple[set[str], list[str]]:
    tiers: set[str] = set()
    summaries: list[str] = []
    for raw in ws.get("ActiveMissions") or []:
        if not isinstance(raw, dict):
            continue
        expiry = parse_mongo_time(raw.get("Expiry"))
        if expiry is not None and expiry <= now:
            continue
        tier_code = str(raw.get("Modifier") or "")
        tier_name, _ = VOID_TIERS.get(tier_code, ("", 99))
        if not tier_name or tier_name == "安魂":
            continue
        loc, info = node_display(str(raw.get("Node") or ""), nodes)
        m_code = raw.get("MissionType")
        if fast_only and m_code not in _FAST_MISSIONS:
            continue
        tiers.add(tier_name)
        label = node_mission_faction(info, m_code, raw.get("Faction"), compact=True)
        summaries.append(f"{tier_name}:{label}@{loc}")
    return tiers, summaries[:4]


def _score_relic(
    relic: RelicEntry,
    by_name: dict[str, tuple[int, float]],
    *,
    prefer_ducats: bool,
) -> tuple[float, str]:
    rare_labels: list[str] = []
    expected = 0.0
    weights = {"RARE": 0.10, "UNCOMMON": 0.20, "COMMON": 0.1667}
    for rew in relic.rewards:
        key = normalize(rew.name.replace(" 蓝图", ""))
        vals = by_name.get(normalize(rew.name)) or by_name.get(key)
        ducats, plat = vals if vals is not None else (0, 0.0)
        weight = weights.get(rew.rarity.upper(), 0.10)
        expected += weight * (ducats if prefer_ducats else plat)
        if rew.rarity.upper() == "RARE":
            val_text = f"{ducats}奸" if prefer_ducats else f"{plat:.0f}p"
            rare_labels.append(f"{rew.name} ({val_text})")
    return expected, " / ".join(rare_labels) or "暂无稀有估值"


def _collect_scored_relics(
    relics: list[RelicEntry],
    active_tiers: set[str],
    by_name: dict[str, tuple[int, float]],
    *,
    kw_cf: str,
    include_all_tiers: bool,
    prefer_ducats: bool,
) -> list[tuple[float, str, str, str]]:
    candidates: list[tuple[float, str, str, str]] = []
    for relic in relics:
        if not include_all_tiers and (
            not active_tiers or not any(relic.name.startswith(t) for t in active_tiers)
        ):
            continue
        if (
            kw_cf
            and kw_cf not in relic.name.casefold()
            and not any(kw_cf in r.name.casefold() for r in relic.rewards)
        ):
            continue
        ev, rare_desc = _score_relic(relic, by_name, prefer_ducats=prefer_ducats)
        if ev <= 0:
            continue
        unit = "奸商币" if prefer_ducats else "白金"
        candidates.append((ev, relic.name, rare_desc, f"{ev:.1f} {unit}"))
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates


def build_relic_value_card(
    raw_args: str,
    ctx: RelicValuationContext,
    meta: QueryMeta,
    *,
    page: int = 1,
) -> Card:
    """Estimate Radiant Void Relic platinum / ducat expected value across active fissures."""
    tokens = raw_args.split()
    flags = {t.casefold() for t in tokens}
    fast_only = "速刷" in flags or ("全部" not in flags)
    include_all = "全部" in flags
    prefer_ducats = "奸商" in flags or "杜卡德" in flags
    reserved = {"速刷", "全部", "白金", "奸商", "杜卡德"}
    kw = " ".join(t for t in tokens if t.casefold() not in reserved)

    by_id, _ = _ducat_lookup_maps(ctx.ducats_body)
    by_name = _item_price_map(ctx.items, by_id)
    active_tiers, summaries = _active_fissure_tiers(
        ctx.ws, ctx.nodes, fast_only=fast_only, now=meta.now
    )
    candidates = _collect_scored_relics(
        ctx.relics,
        active_tiers,
        by_name,
        kw_cf=kw.strip().casefold(),
        include_all_tiers=include_all,
        prefer_ducats=prefer_ducats,
    )
    paged, cur_page, total_pages = paginate(candidates, page, 12)
    rows: list[tuple[str, ...]] = [(name, rare, ev_text) for _, name, rare, ev_text in paged]
    mode_tag = "全部遗物" if include_all else ("速刷裂隙" if fast_only else "全裂隙")
    metric_tag = "按奸商币均值" if prefer_ducats else "按白金均价"
    extra = [x for x in (mode_tag, metric_tag, page_caption(cur_page, total_pages)) if x]
    return Card(
        "开核桃期望推荐 (光辉)",
        rows,
        subtitle(meta, *extra),
        columns=("遗物", "稀有金档与单价", "单车期望收益"),
        kind="relic_value",
        empty_message="当前时段暂无匹配的推荐开核桃方案（可尝试 /开核桃 全部）",
        stats_line=("活跃裂隙参考：" + " · ".join(summaries)) if summaries else "",
    )
