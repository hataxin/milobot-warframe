"""Local pure-Python Riven disposition & stat range calculation (no OCR dependency)."""

from __future__ import annotations

import re

from .card_model import Card
from .dictionary import RivenTrendEntry, WeaponMeta
from .errors import QueryError
from .market import normalize

# Ordered from most specific to generic so compound phrases match before "伤害".
_TREND_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("射速", "射速/攻击速度"),
    ("攻速", "射速/攻击速度"),
    ("攻击速度", "射速/攻击速度"),
    ("后坐力", "后坐力"),
    ("后座力", "后坐力"),
    ("后座", "后坐力"),
    ("infested", "对Infested伤害"),
    ("corpus", "对Corpus伤害"),
    ("grineer", "对Grineer伤害"),
    ("grinner", "对Grineer伤害"),
    ("orokin", "对Orokin伤害"),
    ("炽蛇军", "对炽蛇军伤害"),
    ("科腐者", "对科腐者伤害"),
    ("滑行", "滑行攻击暴击几率"),
    ("弱点暴击", "弱点暴击几率"),
    ("弱点伤害", "弱点伤害"),
    ("暴击几率", "暴击几率"),
    ("暴击率", "暴击几率"),
    ("爆率", "暴击几率"),
    ("暴击伤害", "暴击伤害"),
    ("爆伤", "暴击伤害"),
    ("触发几率", "触发几率"),
    ("触发时间", "触发时间"),
    ("连击持续", "连击持续时间"),
    ("秒连击", "连击持续时间"),
    ("初始连击", "初始连击"),
    ("几率不获得连击数", "几率不获得连击数"),
    ("额外连击数", "额外连击数几率"),
    ("连击数", "几率不获得连击数"),
    ("冰冻", "冰冻伤害"),
    ("毒素", "毒素伤害"),
    ("电击", "电击伤害"),
    ("火焰", "火焰伤害"),
    ("冲击", "冲击伤害"),
    ("切割", "切割伤害"),
    ("穿刺", "穿刺伤害"),
    ("爆炸", "爆炸伤害"),
    ("腐蚀", "腐蚀伤害"),
    ("毒气", "毒气伤害"),
    ("磁力", "磁力伤害"),
    ("辐射", "辐射伤害"),
    ("病毒", "病毒伤害"),
    ("异常状态伤害", "异常状态伤害"),
    ("投射物", "投射物飞行速度"),
    ("弹速", "投射物飞行速度"),
    ("多重射击", "多重射击"),
    ("多重", "多重射击"),
    ("弹药最大值", "弹药最大值"),
    ("弹药上限", "弹药最大值"),
    ("弹药效率", "弹药效率"),
    ("弹匣容量", "弹匣容量"),
    ("弹匣", "弹匣容量"),
    ("装填速度", "装填速度"),
    ("装填", "装填速度"),
    ("穿透", "穿透"),
    ("攻击范围", "攻击范围"),
    ("范围", "攻击范围"),
    ("变焦", "变焦"),
    ("重击效率", "重击效率"),
    ("重击准备", "重击准备速度"),
    ("重击伤害", "重击伤害"),
    ("处决", "处决伤害"),
    ("震地", "震地攻击伤害"),
    ("格挡", "格挡角度"),
    ("收起时自动装填", "收起时自动装填"),
    ("基伤", "伤害/近战伤害"),
    ("近战伤害", "伤害/近战伤害"),
    ("伤害", "伤害/近战伤害"),
)

_DISCRIMINATION_KEYS = ("Infested", "Corpus", "Grineer", "Orokin", "炽蛇军", "科腐者")
_CATEGORY_LABELS: dict[str, str] = {
    "Pistols": "手枪",
    "LongGuns": "步枪",
    "Melee": "近战",
    "SpaceGuns": "Archwing 枪械",
    "SpaceMelee": "Archwing 近战",
    "Shotguns": "霰弹枪",
    "SentinelWeapons": "守护武器",
}

_NUM_FIRST_RE = re.compile(
    r"([xX+\-]?\s*\d+(?:\.\d+)?%?)\s*([^\d%,，;\n+\-\s][^\d%,，;\n+\-]*?)"
    r"(?=\s*(?:[xX+\-]\s*\d|\s+\d|[,，;\n]|$))"
)
_STAT_FIRST_RE = re.compile(r"([^\d%,，;\n+\-\s][^\d%,，;\n+\-]*?)\s*([xX+\-]?\s*\d+(?:\.\d+)?%?)")
_LEAD_NUM_SPLIT_RE = re.compile(
    r"(?:^|[\s,，;])((?:[xX+\-]\s*\d+(?:\.\d+)?%?|\d+(?:\.\d+)?%))(?=\s+[^\d%,，;\n+\-\s])"
)
_LEAD_STAT_SPLIT_RE = re.compile(
    r"(?:^|[\s,，;])([^\s\d%,，;+\-]+?\s*(?:[xX+\-]\s*\d+(?:\.\d+)?%?|\d+(?:\.\d+)?%))"
)
_NUM_RE = re.compile(r"([+\-]?\d+(?:\.\d+)?)")


def dot_from_omega(omega: float) -> str:
    """Convert numeric Omega disposition into a 5-dot Warframe gauge."""
    thresholds = ((0.7, 1), (0.9, 2), (1.15, 3), (1.3, 4))
    dots = next((count for limit, count in thresholds if omega < limit), 5)
    return "●" * dots + "○" * (5 - dots)


def compute_low_high(
    base_val: float,
    omega: float,
    attr_count: int,
    has_curse: bool,
    is_curse: bool,
) -> tuple[float, float]:
    """Compute official Warframe 0.9x..1.1x stat bounds rounded to 4 decimals."""
    if attr_count == 2:
        factor = 0.99
    elif attr_count == 3:
        factor = (-0.495 if is_curse else 1.2375) if has_curse else 0.75
    elif attr_count == 4:
        factor = -0.75 if is_curse else 0.9375
    else:
        return 0.0, 0.0
    return round(0.9 * base_val * omega * factor, 4), round(1.1 * base_val * omega * factor, 4)


def compute_diff(
    trend_name: str, value: float, bounds: tuple[float, float], *, is_mult: bool
) -> str:
    """Calculate signed percentage deviation from the theoretical midpoint."""
    low, high = bounds
    median = (low + high) / 2
    if median == 0:
        return "0.0%"
    observed = value
    if is_mult and any(key in trend_name for key in _DISCRIMINATION_KEYS):
        abs_val = abs(value)
        observed = (abs_val - 1) * 100 if abs_val > 1 else 100 - abs_val * 100
    delta = abs(observed) - abs(median)
    pct = round((abs(observed) - abs(median)) / abs(median) * 100, 2)
    if delta > 0:
        return f"+{abs(pct):.1f}%"
    if delta == 0:
        return "0.0%"
    return f"-{abs(pct):.1f}%"


def _select_base(trend: RivenTrendEntry, weapon: WeaponMeta) -> float:
    desc = weapon.description
    if weapon.product_category == "SentinelWeapons":
        if "霰弹枪" in desc or "散弹枪" in desc:
            return trend.shotgun
        if "近战" in desc or "分离" in weapon.name:
            return trend.melee
        return trend.rifle
    if "霰弹枪" in desc or "散弹枪" in desc:
        return trend.shotgun
    return {
        "Pistols": trend.pistol,
        "LongGuns": trend.rifle,
        "Melee": trend.melee,
        "SpaceGuns": trend.archwing,
        "SpaceMelee": trend.archwing,
        "Shotguns": trend.shotgun,
    }.get(weapon.product_category, 0.0)


def select_base_value(trend: RivenTrendEntry, weapon: WeaponMeta) -> float:
    """Select base stat value matching the weapon's Riven category."""
    return _select_base(trend, weapon)


def lookup_trend_optional(
    stat_text: str, trends: dict[str, RivenTrendEntry]
) -> tuple[str, RivenTrendEntry] | None:
    """Resolve stat text against trend table without raising if unmatched."""
    lowered = stat_text.strip().casefold()
    for keyword, target in _TREND_KEYWORDS:
        if keyword.casefold() in lowered and target in trends:
            return target, trends[target]
    stripped = stat_text.strip()
    if stripped in trends:
        entry = trends[stripped]
        return entry.name, entry
    return None


def _lookup_trend(
    stat_text: str, trends: dict[str, RivenTrendEntry]
) -> tuple[str, RivenTrendEntry]:
    matched = lookup_trend_optional(stat_text, trends)
    if matched is not None:
        return matched
    raise QueryError(f"未能识别紫卡词条“{stat_text.strip()}”，请使用常见游戏词条名称。")


def _match_weapon(query: str, weapons: list[WeaponMeta], aliases: dict[str, str]) -> WeaponMeta:
    rivenable = [w for w in weapons if w.omega_attenuation > 0]
    key = normalize(query)
    aliased = aliases.get(key)
    resolved_alias = normalize(aliased) if aliased is not None and aliased else ""
    keys = {k for k in (key, resolved_alias) if k}
    exact = [
        w
        for w in rivenable
        if normalize(w.name) in keys or (w.english_name and normalize(w.english_name) in keys)
    ]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        return min(exact, key=lambda w: len(w.name))
    partial = [
        w
        for w in rivenable
        if any(
            k in normalize(w.name) or (w.english_name and k in normalize(w.english_name))
            for k in keys
        )
    ]
    if not partial:
        raise QueryError(f"未找到支持紫卡倾向的武器“{query}”，请尝试完整中文或英文武器名。")
    partial.sort(key=lambda w: (len(w.name), w.name))
    return partial[0]


def _parse_stat_token(num_raw: str, name_raw: str) -> tuple[str, float, bool]:
    compact = num_raw.replace(" ", "")
    is_mult = compact.casefold().startswith("x")
    num_match = _NUM_RE.search(compact)
    if num_match is None:
        raise QueryError(f"无法解析词条数值：{num_raw} {name_raw}")
    return name_raw.strip(), float(num_match.group(1)), is_mult


def _split_single_line(cleaned: str) -> tuple[str, str]:
    match = _LEAD_NUM_SPLIT_RE.search(cleaned) or _LEAD_STAT_SPLIT_RE.search(cleaned)
    if match is None:
        raise QueryError(
            "未能从输入中解析出词条数值，示例：/紫卡分析 托里德 +180% 暴击几率 +140% 暴击伤害"
        )
    idx = match.start(1)
    return cleaned[:idx].strip(" ,，;\n"), cleaned[idx:]


def _extract_stats_from_blob(stats_blob: str) -> list[tuple[str, float, bool]]:
    num_first = [
        _parse_stat_token(m.group(1), m.group(2)) for m in _NUM_FIRST_RE.finditer(stats_blob)
    ]
    if num_first:
        return num_first
    return [_parse_stat_token(m.group(2), m.group(1)) for m in _STAT_FIRST_RE.finditer(stats_blob)]


def _split_weapon_and_stats(raw_text: str) -> tuple[str, list[tuple[str, float, bool]]]:
    cleaned = raw_text.strip()
    if not cleaned:
        raise QueryError(
            "请提供武器名与 2～4 条紫卡词条，例如：/紫卡分析 托里德 +180% 暴击几率 +140% 暴击伤害"
        )
    first_line, sep, rest_lines = cleaned.partition("\n")
    if sep and not _NUM_RE.search(first_line):
        weapon_part, stats_blob = first_line.strip(), rest_lines
    else:
        weapon_part, stats_blob = _split_single_line(cleaned)
    if not weapon_part:
        raise QueryError(
            "缺少武器名称，请把武器名放在最前面，例如：托里德 +180% 暴击几率 +140% 暴击伤害"
        )
    parsed_stats = _extract_stats_from_blob(stats_blob)
    if not 2 <= len(parsed_stats) <= 4:
        raise QueryError(f"紫卡倾向分析需要 2～4 条词条，当前识别到 {len(parsed_stats)} 条。")
    return weapon_part, parsed_stats


def _is_curse(label: str, value: float, is_mult: bool) -> bool:
    if "后坐" in label or "后座" in label:
        return value > 0
    if is_mult:
        return abs(value) < 1.0
    return value < 0


def build_riven_analyse_card(
    raw_text: str,
    weapons: list[WeaponMeta],
    trends: dict[str, RivenTrendEntry],
    aliases: dict[str, str],
) -> Card:
    """Compute theoretical min/max and median deviation for a text Riven specification."""
    weapon_part, parsed_attrs = _split_weapon_and_stats(raw_text)
    weapon = _match_weapon(weapon_part, weapons, aliases)
    attr_count = len(parsed_attrs)
    curse_flags = [_is_curse(label, val, mult) for label, val, mult in parsed_attrs]
    has_curse = any(curse_flags) and attr_count >= 3
    if attr_count == 2 and any(curse_flags):
        raise QueryError("2 词条紫卡不带负面词条，请检查输入是否完整。")

    rows: list[tuple[str, ...]] = []
    for (raw_name, val, is_mult), is_neg in zip(parsed_attrs, curse_flags, strict=True):
        trend_name, trend = _lookup_trend(raw_name, trends)
        base_val = _select_base(trend, weapon)
        if base_val == 0:
            low, high, diff = 0.0, 0.0, "0.0%"
        else:
            low, high = compute_low_high(
                base_val, weapon.omega_attenuation, attr_count, has_curse, is_neg
            )
            diff = compute_diff(trend_name, val, (low, high), is_mult=is_mult)
        val_text = f"x{val:g}" if is_mult else f"{val:g}%"
        range_text = f"{low:.1f}% ～ {high:.1f}%"
        rows.append((raw_name, val_text, range_text, diff))

    cat_cn = _CATEGORY_LABELS.get(weapon.product_category, weapon.product_category or "未知")
    dots = dot_from_omega(weapon.omega_attenuation)
    return Card(
        f"{weapon.name} · 紫卡倾向分析",
        rows,
        f"国际服 PC · {attr_count} 词条" + ("（含负面）" if has_curse else "（无负面）"),
        columns=("词条", "当前数值", "理论区间", "中位偏差"),
        kind="riven_analyse",
        highlight=f"武器类型：{cat_cn} · 倾向：{dots} ({weapon.omega_attenuation:.2f})",
    )


def build_riven_analyse_help_card() -> Card:
    """Build text-first help Card for `/紫卡分析`."""
    return Card(
        "紫卡倾向分析帮助",
        [
            (
                "单行格式",
                "/紫卡分析 托里德 +180% 暴击几率 +140% 暴击伤害 -45% 变焦",
                "空格分隔武器与 2~4 条属性",
            ),
            (
                "逗号格式",
                "/紫卡分析 Torid 爆率+180%, 爆伤+140%, 多重+110%",
                "支持简称（爆率/爆伤/基伤/多重）",
            ),
            ("多行粘贴", "/紫卡分析 武器名 后直接换行粘贴词条", "支持 +数值% 与 x1.x 歧视写法"),
        ],
        "国际服 PC · 纯本地数学推算，无需截图或 OCR",
        columns=("方式", "示例指令", "说明"),
        kind="riven_analyse_help",
    )
