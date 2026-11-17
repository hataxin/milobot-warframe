"""WorldState parsers and structured Card builders for PC international server."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

from .card_model import Card
from .command_flags import page_caption, paginate
from .cycles import calculate_cycles, duviri_emotion_cycle, parse_duviri_choices, utc_time
from .dictionary import (
    NightwaveChallenge,
    NodeInfo,
    PoolReward,
    TranslationIndex,
    strip_markup,
)
from .errors import QueryError


@dataclass(frozen=True)
class QueryMeta:
    """Shared timestamp and warning context passed into card builders."""

    now: float
    fetched_at: float
    warnings: list[str]


STEEL_PATH_START = 1_605_484_800
STEEL_PATH_WEEK = 604_800
STEEL_PATH_CYCLE = 4_838_400

STEEL_PATH_ROTATION: tuple[tuple[str, int], ...] = (
    ("Umbra Forma 蓝图", 150),
    ("50,000 赤毒", 55),
    ("组合枪裂罅 Mod", 75),
    ("3x Forma", 75),
    ("Zaw 裂罅 Mod", 75),
    ("30,000 内融核心", 150),
    ("步枪裂罅 Mod", 75),
    ("霰弹枪裂罅 Mod", 75),
)

FACTION_NAMES: dict[str, str] = {
    "FC_GRINEER": "Grineer",
    "FC_CORPUS": "Corpus",
    "FC_INFESTATION": "Infested",
    "FC_OROKIN": "奥罗金",
    "FC_CORRUPTED": "堕落者",
    "FC_SENTIENT": "Sentient",
    "FC_NARMER": "合一众",
    "FC_MURMUR": "低语者",
    "FC_SCALDRA": "炽蛇军",
    "FC_TECHROT": "科腐者",
    "FC_DUVIRI": "双衍王境",
    "FC_MITW": "墙中人",
    "FC_TENNO": "Tenno",
    "FC_CROSSFIRE": "多方交战",
    "FC_NONE": "未知派系",
}

COMPACT_FACTION_NAMES: dict[str, str] = {
    "FC_GRINEER": "G系",
    "FC_CORPUS": "C系",
    "FC_INFESTATION": "I系",
    "FC_OROKIN": "O系",
    "FC_CORRUPTED": "O系",
    "FC_SENTIENT": "S系",
    "FC_NARMER": "合一",
    "FC_MURMUR": "低语",
    "FC_SCALDRA": "炽蛇",
    "FC_TECHROT": "科腐",
    "FC_DUVIRI": "双衍",
    "FC_MITW": "墙中人",
    "FC_TENNO": "Tenno",
    "FC_CROSSFIRE": "交战",
    "FC_NONE": "未知",
}

_UTC_PLUS_8 = timezone(timedelta(hours=8))

FACTION_INDEX_MAP: dict[int, str] = {
    0: "FC_GRINEER",
    1: "FC_CORPUS",
    2: "FC_INFESTATION",
    3: "FC_OROKIN",
    4: "FC_CORRUPTED",
    5: "FC_SENTIENT",
    6: "FC_NARMER",
    7: "FC_MURMUR",
    8: "FC_SCALDRA",
    9: "FC_TECHROT",
    10: "FC_DUVIRI",
    11: "FC_MITW",
    12: "FC_TENNO",
}

MISSION_TYPE_NAMES: dict[str, str] = {
    "MT_ASSASSINATION": "刺杀",
    "MT_EXTERMINATION": "歼灭",
    "MT_SURVIVAL": "生存",
    "MT_RESCUE": "救援",
    "MT_SABOTAGE": "破坏",
    "MT_CAPTURE": "捕获",
    "MT_ENDLESS_CAPTURE": "传承细胞收割",
    "MT_DEFAULT": "未知",
    "MT_INTEL": "间谍",
    "MT_DEFENSE": "防御",
    "MT_MOBILE_DEFENSE": "移动防御",
    "MT_PVP": "武形秘仪",
    "MT_SECTOR": "黑暗地带",
    "MT_TERRITORY": "拦截",
    "MT_RETRIEVAL": "劫持",
    "MT_HIVE": "清巢",
    "MT_EXCAVATE": "挖掘",
    "MT_SALVAGE": "资源回收",
    "MT_ARENA": "竞技场",
    "MT_PURSUIT": "追击",
    "MT_ASSAULT": "强袭",
    "MT_EVACUATION": "叛逃",
    "MT_LANDSCAPE": "自由漫步",
    "MT_DISRUPTION": "中断",
    "MT_ARTIFACT": "中断",
    "MT_VOID_FLOOD": "虚空洪流",
    "MT_VOID_CASCADE": "虚空覆涌",
    "MT_VOID_ARMAGEDDON": "虚空决战",
    "MT_ALCHEMY": "元素转换",
    "MT_CAMBIRE": "异化区",
    "MT_LEGACYTE_HARVEST": "传承种收割",
    "MT_SHRINE_DEFENSE": "祈运坛防御",
    "MT_FACEOFF": "对战",
    "MT_CORRUPTION": "腐化",
    "MT_SKIRMISH": "前哨战",
    "MT_VOLATILE": "爆发",
    "MT_ORPHEUS": "奥菲斯",
    "MT_ASCENSION": "扬升",
    "MT_RELAY": "中继站",
}

MISSION_INDEX_MAP: dict[int, str] = {
    0: "MT_ASSASSINATION",
    1: "MT_EXTERMINATION",
    2: "MT_SURVIVAL",
    3: "MT_RESCUE",
    4: "MT_SABOTAGE",
    5: "MT_CAPTURE",
    7: "MT_INTEL",
    8: "MT_DEFENSE",
    9: "MT_MOBILE_DEFENSE",
    10: "MT_PVP",
    11: "MT_SECTOR",
    13: "MT_TERRITORY",
    14: "MT_RETRIEVAL",
    15: "MT_HIVE",
    17: "MT_EXCAVATE",
    21: "MT_SALVAGE",
    22: "MT_ARENA",
    24: "MT_PURSUIT",
    25: "MT_PURSUIT",
    26: "MT_ASSAULT",
    27: "MT_EVACUATION",
    28: "MT_LANDSCAPE",
    31: "MT_LANDSCAPE",
    32: "MT_ARTIFACT",
    33: "MT_ARTIFACT",
    34: "MT_VOID_FLOOD",
    35: "MT_VOID_CASCADE",
    36: "MT_VOID_ARMAGEDDON",
    38: "MT_ALCHEMY",
    39: "MT_CAMBIRE",
    40: "MT_LEGACYTE_HARVEST",
    41: "MT_SHRINE_DEFENSE",
    42: "MT_FACEOFF",
    60: "MT_SKIRMISH",
    61: "MT_VOLATILE",
    62: "MT_ORPHEUS",
    90: "MT_ASCENSION",
    100: "MT_RELAY",
}

BOSS_NAMES: dict[str, tuple[str, str]] = {
    "SORTIE_BOSS_KELA": ("Kela De Thaym", "Grineer"),
    "SORTIE_BOSS_VOR": ("Vor 上尉", "Grineer"),
    "SORTIE_BOSS_RUK": ("Sargas Ruk 将军", "Grineer"),
    "SORTIE_BOSS_HEK": ("Vay Hek 委员", "Grineer"),
    "SORTIE_BOSS_KRIL": ("Lech Kril 中尉", "Grineer"),
    "SORTIE_BOSS_TYL": ("Tyl Regor", "Grineer"),
    "SORTIE_BOSS_HYENA": ("鬣狗群", "Corpus"),
    "SORTIE_BOSS_JACKAL": ("豺狼", "Corpus"),
    "SORTIE_BOSS_ALAD": ("Alad V", "Corpus"),
    "SORTIE_BOSS_AMBULAS": ("Ambulas", "Corpus"),
    "SORTIE_BOSS_NEF": ("Nef Anyo", "Corpus"),
    "SORTIE_BOSS_RAPTOR": ("猛禽", "Corpus"),
    "SORTIE_BOSS_PHORID": ("Phorid", "Infested"),
    "SORTIE_BOSS_LEPHANTIS": ("Lephantis", "Infested"),
    "SORTIE_BOSS_INFALAD": ("异融者 Alad V", "Infested"),
    "SORTIE_BOSS_CORRUPTED_VOR": ("堕落 Vor", "堕落者"),
    "SORTIE_BOSS_BOREAL": ("诡文枭主", "合一众"),
    "SORTIE_BOSS_AMAR": ("欺谋狼主", "合一众"),
    "SORTIE_BOSS_NIRA": ("混沌蛇主", "合一众"),
    "SORTIE_BOSS_PAAZUL": ("帕祖", "合一众"),
}

MODIFIER_NAMES: dict[str, str] = {
    "SORTIE_MODIFIER_HAZARD_RADIATION": "辐射灾害",
    "SORTIE_MODIFIER_HAZARD_MAGNETIC": "电磁异常",
    "SORTIE_MODIFIER_HAZARD_FOG": "浓雾",
    "SORTIE_MODIFIER_HAZARD_FIRE": "环境危害：火灾",
    "SORTIE_MODIFIER_HAZARD_ICE": "低温外泄",
    "SORTIE_MODIFIER_HAZARD_COLD": "极度寒冷",
    "SORTIE_MODIFIER_SLASH": "敌人物理强化(切割)",
    "SORTIE_MODIFIER_IMPACT": "敌人物理强化(冲击)",
    "SORTIE_MODIFIER_PUNCTURE": "敌人物理强化(穿刺)",
    "SORTIE_MODIFIER_MAGNETIC": "敌人元素强化(磁力)",
    "SORTIE_MODIFIER_EXPLOSION": "敌人元素强化(爆炸)",
    "SORTIE_MODIFIER_CORROSIVE": "敌人元素强化(腐蚀)",
    "SORTIE_MODIFIER_VIRAL": "敌人元素强化(病毒)",
    "SORTIE_MODIFIER_ELECTRICITY": "敌人元素强化(电击)",
    "SORTIE_MODIFIER_RADIATION": "敌人元素强化(辐射)",
    "SORTIE_MODIFIER_GAS": "敌人元素强化(毒气)",
    "SORTIE_MODIFIER_FIRE": "敌人元素强化(火焰)",
    "SORTIE_MODIFIER_FREEZE": "敌人元素强化(冰冻)",
    "SORTIE_MODIFIER_TOXIN": "敌人元素强化(毒素)",
    "SORTIE_MODIFIER_POISON": "敌人元素强化(毒素)",
    "SORTIE_MODIFIER_SHIELDS": "敌人护盾强化",
    "SORTIE_MODIFIER_ARMOR": "敌人护甲强化",
    "SORTIE_MODIFIER_BOW_ONLY": "仅限弓箭/弩",
    "SORTIE_MODIFIER_SHOTGUN_ONLY": "仅限霰弹枪",
    "SORTIE_MODIFIER_RIFLE_ONLY": "仅限突击步枪",
    "SORTIE_MODIFIER_SECONDARY_ONLY": "武器限定：次要武器",
    "SORTIE_MODIFIER_SNIPER_ONLY": "武器限定：狙击枪",
    "SORTIE_MODIFIER_MELEE_ONLY": "武器限定：近战",
    "SORTIE_MODIFIER_EXIMUS": "卓越者大本营",
    "SORTIE_MODIFIER_LOW_ENERGY": "能量上限减少",
}

VOID_TIERS: dict[str, tuple[str, int]] = {
    "VoidT1": ("古纪", 1),
    "VoidT2": ("前纪", 2),
    "VoidT3": ("中纪", 3),
    "VoidT4": ("后纪", 4),
    "VoidT5": ("安魂", 5),
    "VoidT6": ("全能", 6),
}

SYNDICATE_TITLES: dict[str, str] = {
    "CetusSyndicate": "希图斯 · Ostron 赏金",
    "SolarisSyndicate": "索拉里斯联盟赏金",
    "EntratiSyndicate": "英择谛（火卫二）赏金",
}

CALENDAR_SEASONS: dict[str, str] = {
    "CST_SPRING": "春季",
    "CST_SUMMER": "夏季",
    "CST_FALL": "秋季",
    "CST_WINTER": "冬季",
}

_MONTH_LENGTHS: tuple[int, ...] = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


def parse_mongo_time(value: Any) -> float | None:
    """Decode MongoDB extended JSON timestamps without throwing on missing fields."""
    try:
        return int(value["$date"]["$numberLong"]) / 1000
    except (TypeError, KeyError, ValueError):
        return None


def format_remaining(expires_at: float | None, now: float) -> str:
    """Format remaining duration as HH:MM:SS or N天 HH:MM:SS."""
    if expires_at is None:
        return "未知"
    seconds = max(0, int(expires_at - now))
    days, rem = divmod(seconds, 86_400)
    hours, rem = divmod(rem, 3_600)
    minutes, secs = divmod(rem, 60)
    clock = f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{days}天 {clock}" if days > 0 else clock


def path_tail(text: str) -> str:
    """Return the final segment of an untranslated /Lotus/... resource path."""
    if not text or not text.startswith("/") or any(c.isspace() for c in text):
        return text
    return text.rsplit("/", 1)[-1]


def faction_name(code: str | None) -> str:
    """Resolve faction code to Chinese display label."""
    if code is None or not code:
        return "未知派系"
    return FACTION_NAMES.get(code, code)


def compact_faction(code: str | None) -> str:
    """Resolve faction code to compact pill label (`G系`/`C系`/`I系`/`O系`/`低语`...)."""
    if code is None or not code:
        return "未知"
    return COMPACT_FACTION_NAMES.get(code, code)


def compact_remaining(expires_at: float | None, now: float) -> str:
    """Format compact remaining duration (`12m34s`, `1h05m`, `2d 03h`)."""
    if expires_at is None:
        return "未知"
    seconds = max(0, int(expires_at - now))
    days, rem = divmod(seconds, 86_400)
    hours, rem = divmod(rem, 3_600)
    minutes, secs = divmod(rem, 60)
    if days > 0:
        return f"{days}d {hours:02d}h"
    if hours > 0:
        return f"{hours}h{minutes:02d}m"
    return f"{minutes:02d}m{secs:02d}s"


def mission_name(code: str | None) -> str:
    """Resolve mission type code to Chinese display label."""
    if code is None or not code:
        return "未知"
    return MISSION_TYPE_NAMES.get(code, code)


def node_display(key: str, nodes: dict[str, NodeInfo]) -> tuple[str, NodeInfo | None]:
    """Return localized node name and metadata if present."""
    info = nodes.get(key)
    return (info.display_name, info) if info else (key or "未知节点", None)


def node_mission_faction(
    info: NodeInfo | None,
    raw_mission: str | None,
    raw_faction: str | None,
    *,
    compact: bool = False,
) -> str:
    """Format localized mission type and faction for a node."""
    m_code = raw_mission or (
        MISSION_INDEX_MAP.get(info.mission_index)
        if info and info.mission_index is not None
        else None
    )
    f_code = raw_faction or (
        FACTION_INDEX_MAP.get(info.faction_index)
        if info and info.faction_index is not None
        else None
    )
    if compact:
        return f"{compact_faction(f_code)} · {mission_name(m_code)}"
    return f"{mission_name(m_code)} · {faction_name(f_code)}"


def subtitle(meta: QueryMeta, *extras: str) -> str:
    """Format a standard PC international subtitle with UTC fetch timestamp."""
    parts = ["国际服 PC"]
    for extra in extras:
        if extra:
            parts.append(extra)
    parts.append(f"数据获取于 {utc_time(meta.fetched_at)}")
    if meta.warnings:
        parts.append("；".join(meta.warnings))
    return " · ".join(parts)


def format_reward(reward: Any, trans: TranslationIndex) -> str:
    """Format a WorldState missionReward object into localized text."""
    if not isinstance(reward, dict):
        return ""
    segments: list[str] = []
    credits_val = reward.get("credits")
    if isinstance(credits_val, int) and credits_val > 0:
        segments.append(f"{credits_val:,} 星币")
    for raw_item in reward.get("items") or []:
        if isinstance(raw_item, str) and raw_item:
            name = strip_markup(trans.translate(raw_item))
            segments.append(path_tail(name))
    for entry in reward.get("countedItems") or []:
        if not isinstance(entry, dict) or not entry.get("ItemType"):
            continue
        name = path_tail(strip_markup(trans.translate(str(entry["ItemType"]))))
        count = entry.get("ItemCount")
        segments.append(f"{name} ×{count}" if isinstance(count, int) and count > 1 else name)
    return "，".join(segments)


def build_alerts_card(
    ws: dict[str, Any],
    nodes: dict[str, NodeInfo],
    trans: TranslationIndex,
    meta: QueryMeta,
) -> Card:
    """Build the active alerts Card."""
    rows: list[tuple[str, ...]] = []
    for raw in ws.get("Alerts", []):
        if not isinstance(raw, dict):
            continue
        info = raw.get("MissionInfo")
        if not isinstance(info, dict):
            continue
        expiry = parse_mongo_time(raw.get("Expiry"))
        if expiry is not None and expiry <= meta.now:
            continue
        loc, node_info = node_display(str(info.get("location") or ""), nodes)
        mission_col = node_mission_faction(node_info, info.get("missionType"), info.get("faction"))
        reward_text = format_reward(info.get("missionReward"), trans) or "无道具奖励"
        rows.append((loc, mission_col, reward_text, format_remaining(expiry, meta.now)))
    return Card(
        "警报任务",
        rows,
        subtitle(meta),
        columns=("节点", "任务 / 派系", "奖励", "剩余时间"),
        kind="alerts",
        empty_message="当前没有活跃的警报",
    )


def _collect_fissures(
    ws: dict[str, Any],
    nodes: dict[str, NodeInfo],
    mode: str,
    meta: QueryMeta,
    filter_kw: str,
) -> list[tuple[int, float, str, tuple[str, str, str]]]:
    source = ws.get("VoidStorms", []) if mode == "storm" else ws.get("ActiveMissions", [])
    kw = filter_kw.strip().casefold()
    collected: list[tuple[int, float, str, tuple[str, str, str]]] = []
    for raw in source:
        if not isinstance(raw, dict):
            continue
        if mode != "storm" and bool(raw.get("Hard")) != (mode == "steel"):
            continue
        expiry = parse_mongo_time(raw.get("Expiry"))
        if expiry is not None and expiry <= meta.now:
            continue
        tier_code = str(raw.get("ActiveMissionTier" if mode == "storm" else "Modifier") or "")
        tier_label, tier_order = VOID_TIERS.get(tier_code, (tier_code or "未知", 99))
        loc, node_info = node_display(str(raw.get("Node") or ""), nodes)
        m_arg = None if mode == "storm" else raw.get("MissionType")
        compact_col = node_mission_faction(node_info, m_arg, raw.get("Faction"), compact=True)
        full_col = node_mission_faction(node_info, m_arg, raw.get("Faction"), compact=False)
        if kw and kw not in f"{tier_label} {tier_code} {loc} {compact_col} {full_col}".casefold():
            continue
        group_title = f"{tier_label} (T{tier_order})" if tier_order < 99 else tier_label
        row = (compact_col, loc, compact_remaining(expiry, meta.now))
        collected.append((tier_order, expiry or float("inf"), group_title, row))
    collected.sort(key=lambda item: (item[0], item[1]))
    return collected


def _group_fissure_rows(
    paged: list[tuple[int, float, str, tuple[str, str, str]]],
) -> list[tuple[str, ...]]:
    rows: list[tuple[str, ...]] = []
    last_group = ""
    for _, _, grp, row in paged:
        if grp != last_group:
            rows.append((f"§{grp}", "", ""))
            last_group = grp
        rows.append(row)
    return rows


def build_fissures_card(
    ws: dict[str, Any],
    nodes: dict[str, NodeInfo],
    mode: str,
    meta: QueryMeta,
    *,
    filter_kw: str = "",
    page: int = 1,
) -> Card:
    """Build grouped, compact 3-column fissures Card with keyword filter & pagination."""
    titles = {"normal": "虚空裂隙", "steel": "钢铁裂隙", "storm": "九重天虚空风暴"}
    collected = _collect_fissures(ws, nodes, mode, meta, filter_kw)
    tier_counts: dict[str, int] = {}
    for _, _, grp, _ in collected:
        tier_counts[grp] = tier_counts.get(grp, 0) + 1
    paged, cur_page, total_pages = paginate(collected, page, 14)
    rows = _group_fissure_rows(paged)
    stats_line = "  ·  ".join(f"{name} {cnt}" for name, cnt in tier_counts.items())
    extra = [
        x
        for x in (
            f"筛选: {filter_kw.strip()}" if filter_kw.strip() else "",
            page_caption(cur_page, total_pages),
        )
        if x
    ]
    return Card(
        titles.get(mode, "虚空裂隙"),
        rows,
        subtitle(meta, *extra),
        columns=("派系 / 任务", "节点", "剩余时间"),
        kind="fissures",
        empty_message=f"当前没有匹配的{titles.get(mode, '裂隙')}",
        stats_line=stats_line,
    )


def build_sortie_card(
    ws: dict[str, Any],
    nodes: dict[str, NodeInfo],
    meta: QueryMeta,
) -> Card:
    """Build today's Sortie Card."""
    sorties = ws.get("Sorties", [])
    if not isinstance(sorties, list) or not sorties or not isinstance(sorties[0], dict):
        return Card(
            "突击任务",
            [],
            subtitle(meta),
            columns=("阶段", "任务类型", "节点", "状态变异"),
            kind="sortie",
            empty_message="当前没有突击数据",
        )
    sortie = sorties[0]
    boss_code = str(sortie.get("Boss") or "")
    boss_name, boss_faction = BOSS_NAMES.get(boss_code, (boss_code or "未知", "未知"))
    expiry = parse_mongo_time(sortie.get("Expiry"))
    rows: list[tuple[str, ...]] = []
    for index, variant in enumerate(sortie.get("Variants", []), 1):
        if not isinstance(variant, dict):
            continue
        loc, _ = node_display(str(variant.get("node") or ""), nodes)
        mod_code = str(variant.get("modifierType") or "")
        rows.append(
            (
                f"阶段 {index}",
                mission_name(variant.get("missionType")),
                loc,
                MODIFIER_NAMES.get(mod_code, mod_code or "无"),
            )
        )
    return Card(
        "突击任务",
        rows,
        subtitle(meta, f"剩余 {format_remaining(expiry, meta.now)}"),
        columns=("阶段", "任务类型", "节点", "状态变异"),
        kind="sortie",
        empty_message="当前没有突击任务",
        highlight=f"Boss：{boss_name}（{boss_faction}）",
    )


def build_archon_card(
    ws: dict[str, Any],
    nodes: dict[str, NodeInfo],
    meta: QueryMeta,
) -> Card:
    """Build weekly Archon Hunt Card."""
    hunts = ws.get("LiteSorties", [])
    if not isinstance(hunts, list) or not hunts or not isinstance(hunts[0], dict):
        return Card(
            "执刑官猎杀",
            [],
            subtitle(meta),
            columns=("阶段", "任务类型", "节点"),
            kind="archon",
            empty_message="当前没有执刑官猎杀数据",
        )
    hunt = hunts[0]
    boss_code = str(hunt.get("Boss") or "")
    boss_name, boss_faction = BOSS_NAMES.get(boss_code, (boss_code or "未知", "合一众"))
    expiry = parse_mongo_time(hunt.get("Expiry"))
    rows: list[tuple[str, ...]] = []
    for index, mission in enumerate(hunt.get("Missions", []), 1):
        if not isinstance(mission, dict):
            continue
        loc, _ = node_display(str(mission.get("node") or ""), nodes)
        rows.append((f"阶段 {index}", mission_name(mission.get("missionType")), loc))
    return Card(
        "执刑官猎杀",
        rows,
        subtitle(meta, f"剩余 {format_remaining(expiry, meta.now)}"),
        columns=("阶段", "任务类型", "节点"),
        kind="archon",
        empty_message="当前没有执刑官猎杀任务",
        highlight=f"执刑官：{boss_name}（{boss_faction}）",
    )


def invasion_reward_text(raw: Any, trans: TranslationIndex) -> str:
    """Format an Invasion attacker/defender reward list or dict into localized text."""
    if isinstance(raw, list):
        parts = [format_reward(entry, trans) for entry in raw]
        return "，".join(part for part in parts if part) or "—"
    return format_reward(raw, trans) or "—"


def build_invasions_card(
    ws: dict[str, Any],
    nodes: dict[str, NodeInfo],
    trans: TranslationIndex,
    meta: QueryMeta,
) -> Card:
    """Build active Invasions Card sorted by goal descending."""
    raw_list = [
        inv for inv in ws.get("Invasions", []) if isinstance(inv, dict) and not inv.get("Completed")
    ]
    raw_list.sort(key=lambda inv: float(inv.get("Goal") or 0), reverse=True)
    rows: list[tuple[str, ...]] = []
    for inv in raw_list:
        loc, _ = node_display(str(inv.get("Node") or ""), nodes)
        atk_fac = faction_name(inv.get("Faction"))
        def_fac = faction_name(inv.get("DefenderFaction"))
        atk_rew = invasion_reward_text(inv.get("AttackerReward"), trans)
        def_rew = invasion_reward_text(inv.get("DefenderReward"), trans)
        goal = float(inv.get("Goal") or 0)
        count = float(inv.get("Count") or 0)
        progress = min(abs(count) / goal, 1.0) if goal else 0.0
        rows.append(
            (
                loc,
                f"{atk_fac}\nvs {def_fac}",
                f"攻：{atk_rew}\n守：{def_rew}",
                f"{progress * 100:.1f}%",
            )
        )
    return Card(
        "入侵任务",
        rows,
        subtitle(meta),
        columns=("节点", "对抗阵营", "进攻 / 防守奖励", "进度"),
        kind="invasions",
        empty_message="当前没有活跃的入侵",
    )


def build_void_trader_card(
    ws: dict[str, Any],
    nodes: dict[str, NodeInfo],
    trans: TranslationIndex,
    meta: QueryMeta,
) -> Card:
    """Build Baro Ki'Teer Void Trader Card."""
    traders = ws.get("VoidTraders", [])
    if not isinstance(traders, list) or not traders or not isinstance(traders[0], dict):
        return Card(
            "虚空商人",
            [],
            subtitle(meta),
            columns=("商品名称", "杜卡德币", "星币"),
            kind="void_trader",
            empty_message="当前没有虚空商人数据",
        )
    trader = traders[0]
    character = str(trader.get("Character") or "Baro Ki'Teer")
    loc, _ = node_display(str(trader.get("Node") or ""), nodes)
    activation = parse_mongo_time(trader.get("Activation"))
    expiry = parse_mongo_time(trader.get("Expiry"))
    manifest = trader.get("Manifest")
    if activation is not None and meta.now < activation and not manifest:
        return Card(
            "虚空商人",
            [(loc, "尚未到达", format_remaining(activation, meta.now))],
            subtitle(meta),
            columns=("目的地", "状态", "到达倒计时"),
            kind="void_trader",
            highlight=f"{character} · 即将抵达 {loc}",
            footer_note="商品清单将在商人抵达中继站后公布",
        )
    rows: list[tuple[str, ...]] = []
    for entry in manifest or []:
        if not isinstance(entry, dict):
            continue
        item_name = path_tail(strip_markup(trans.translate(str(entry.get("ItemType") or ""))))
        ducats = entry.get("PrimePrice")
        credits_val = entry.get("RegularPrice")
        rows.append(
            (
                item_name or "未知商品",
                f"{ducats:,}" if isinstance(ducats, int) else "—",
                f"{credits_val:,}" if isinstance(credits_val, int) else "—",
            )
        )
    return Card(
        "虚空商人",
        rows,
        subtitle(meta),
        columns=("商品名称", "杜卡德币", "星币"),
        kind="void_trader",
        empty_message="商人已在位但暂无商品记录",
        highlight=f"{character} · {loc} · 离开倒计时 {format_remaining(expiry, meta.now)}",
    )


def build_steel_path_card(now: float) -> Card:
    """Build Steel Path Teshin weekly offering rotation Card."""
    elapsed = max(0, int(now) - STEEL_PATH_START)
    index = (elapsed % STEEL_PATH_CYCLE) // STEEL_PATH_WEEK
    current_name, current_cost = STEEL_PATH_ROTATION[index % len(STEEL_PATH_ROTATION)]
    now_dt = datetime.fromtimestamp(now, UTC)
    start_of_week = now_dt.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(
        days=now_dt.weekday()
    )
    end_of_week = (start_of_week + timedelta(days=7)).timestamp()
    rows: list[tuple[str, ...]] = []
    for offset in range(len(STEEL_PATH_ROTATION)):
        label = "本周" if offset == 0 else ("下周" if offset == 1 else f"+{offset}周")
        name, cost = STEEL_PATH_ROTATION[(index + offset) % len(STEEL_PATH_ROTATION)]
        rows.append((label, name, f"{cost} 精华"))
    return Card(
        "钢铁之路奖励",
        rows,
        f"国际服 PC · 距下次轮换 {format_remaining(end_of_week, now)} · 计算于 {utc_time(now)}",
        columns=("周期", "奖励内容", "消耗"),
        kind="steel_path",
        highlight=f"本周：{current_name}（{current_cost} 钢铁精华）",
        footer_note="按 UTC 每周一 00:00 自动轮换",
    )


def _challenge_kind(standing: int, raw_daily: Any) -> tuple[str, int]:
    if standing == 1000 or (standing == 0 and raw_daily):
        return "每日", 0
    if standing == 4500:
        return "每周", 1
    if standing == 7000:
        return "精英", 2
    return "普通", 3


def build_nightwave_card(
    ws: dict[str, Any],
    nw_dict: dict[str, NightwaveChallenge],
    meta: QueryMeta,
) -> Card:
    """Build Nightwave season challenges Card."""
    season_info = ws.get("SeasonInfo")
    if not isinstance(season_info, dict):
        return Card(
            "午夜电波",
            [],
            subtitle(meta),
            columns=("类型", "任务名称", "任务说明", "声望"),
            kind="nightwave",
            empty_message="当前没有午夜电波数据",
        )
    season = season_info.get("Season")
    expiry = parse_mongo_time(season_info.get("Expiry"))
    collected: list[tuple[int, int, tuple[str, ...]]] = []
    for entry in season_info.get("ActiveChallenges", []):
        if not isinstance(entry, dict):
            continue
        cid = str(entry.get("Challenge") or "")
        ch = nw_dict.get(cid)
        if ch is not None:
            name, desc, standing = ch.name, ch.formatted_desc, ch.standing
        else:
            name, desc, standing = path_tail(cid) or "未知任务", "—", 0
        kind_label, order = _challenge_kind(standing, entry.get("Daily"))
        row = (kind_label, name, desc or "—", f"{standing:,}" if standing else "—")
        collected.append((order, standing, row))
    collected.sort(key=lambda item: (item[0], item[1]))
    banner = f"第 {season} 季" if season is not None else "当前赛季"
    return Card(
        "午夜电波",
        [item[2] for item in collected],
        subtitle(meta, f"剩余 {format_remaining(expiry, meta.now)}"),
        columns=("类型", "任务名称", "任务说明", "声望"),
        kind="nightwave",
        empty_message="当前没有活跃的电波挑战",
        highlight=banner,
    )


def build_daily_deals_card(
    ws: dict[str, Any],
    trans: TranslationIndex,
    meta: QueryMeta,
) -> Card:
    """Build Darvo Daily Deals Card."""
    rows: list[tuple[str, ...]] = []
    for deal in ws.get("DailyDeals", []):
        if not isinstance(deal, dict):
            continue
        item_name = path_tail(strip_markup(trans.translate(str(deal.get("StoreItem") or ""))))
        discount = int(deal.get("Discount") or 0)
        original = int(deal.get("OriginalPrice") or 0)
        sale = int(deal.get("SalePrice") or 0)
        total = int(deal.get("AmountTotal") or 0)
        sold = int(deal.get("AmountSold") or 0)
        remaining_count = max(0, total - sold)
        expiry = parse_mongo_time(deal.get("Expiry"))
        rows.append(
            (
                item_name or "未知物品",
                f"-{discount}%",
                f"{sale} / {original}",
                f"{remaining_count} / {total}",
                format_remaining(expiry, meta.now),
            )
        )
    return Card(
        "每日特惠",
        rows,
        subtitle(meta),
        columns=("物品名称", "折扣", "现价 / 原价", "余量 / 总量", "剩余时间"),
        kind="daily_deals",
        empty_message="当前没有每日特惠数据",
    )


def _day_of_year_to_month_day(day_of_year: int) -> tuple[int, int]:
    remaining = day_of_year
    for month, length in enumerate(_MONTH_LENGTHS, 1):
        if remaining <= length:
            return month, remaining
        remaining -= length
    return 12, remaining


def _format_calendar_event(evt: dict[str, Any], trans: TranslationIndex) -> tuple[str, str] | None:
    evt_type = str(evt.get("type") or "")
    if evt_type == "CET_CHALLENGE":
        key = str(evt.get("challenge") or "")
        title = path_tail(trans.translate(key))
        desc = trans.describe(key)
        return ("任务", f"{title}：{desc}" if desc else title) if title else None
    if evt_type == "CET_REWARD":
        key = str(evt.get("reward") or "")
        reward = path_tail(strip_markup(trans.translate(key)))
        return ("奖励", reward) if reward else None
    if evt_type == "CET_UPGRADE":
        key = str(evt.get("upgrade") or "")
        title = path_tail(trans.translate(key))
        desc = trans.describe(key)
        return ("加成", f"{title}：{desc}" if desc else title) if title else None
    return None


def build_calendar_card(
    ws: dict[str, Any],
    trans: TranslationIndex,
    meta: QueryMeta,
) -> Card:
    """Build 1999 Calendar Seasons Card."""
    seasons = ws.get("KnownCalendarSeasons", [])
    if not isinstance(seasons, list) or not seasons or not isinstance(seasons[0], dict):
        return Card(
            "1999 日历",
            [],
            subtitle(meta),
            columns=("日期", "类型", "内容"),
            kind="calendar",
            empty_message="当前没有 1999 日历数据",
        )
    cal = seasons[0]
    season_label = CALENDAR_SEASONS.get(str(cal.get("Season") or ""), str(cal.get("Season") or ""))
    year_iter = cal.get("YearIteration")
    expiry = parse_mongo_time(cal.get("Expiry"))
    parsed_days: list[tuple[int, int, list[tuple[str, str]]]] = []
    for raw_day in cal.get("Days", []):
        if not isinstance(raw_day, dict) or not isinstance(raw_day.get("day"), int):
            continue
        month, dom = _day_of_year_to_month_day(raw_day["day"])
        events = [
            formatted
            for evt in raw_day.get("events", [])
            if isinstance(evt, dict) and (formatted := _format_calendar_event(evt, trans))
        ]
        if events:
            parsed_days.append((month, dom, events))
    parsed_days.sort(key=lambda item: (item[0], item[1]))
    rows: list[tuple[str, ...]] = [
        (f"{month}月{dom}日" if idx == 0 else "", kind_label, content)
        for month, dom, events in parsed_days
        for idx, (kind_label, content) in enumerate(events)
    ]
    banner = f"{season_label or '当前季节'} · 第 {year_iter} 次迭代"
    return Card(
        "1999 日历",
        rows,
        subtitle(meta, f"剩余 {format_remaining(expiry, meta.now)}"),
        columns=("日期", "类型", "内容"),
        kind="calendar",
        empty_message="当前季节暂无日历事件",
        highlight=banner,
    )


def build_syndicate_card(
    ws: dict[str, Any],
    tag: str,
    reward_pools: dict[str, list[PoolReward]],
    trans: TranslationIndex,
    meta: QueryMeta,
) -> Card:
    """Build Syndicate Bounty Missions Card for Cetus, Solaris or Entrati."""
    title = SYNDICATE_TITLES.get(tag, f"{tag} 赏金")
    mission = _find_syndicate_mission(ws.get("SyndicateMissions", []), tag)
    if mission is None:
        return Card(
            title,
            [],
            subtitle(meta),
            columns=("赏金任务", "等级 / 声望", "奖励池"),
            kind="syndicate",
            empty_message="当前没有该集团的赏金数据",
        )
    expiry = parse_mongo_time(mission.get("Expiry"))
    rows = [
        _format_job_row(job, reward_pools, trans)
        for job in mission.get("Jobs", [])
        if isinstance(job, dict)
    ]
    return Card(
        title,
        rows,
        subtitle(meta, f"刷新剩余 {format_remaining(expiry, meta.now)}"),
        columns=("赏金任务", "等级 / 声望", "奖励池"),
        kind="syndicate",
        empty_message="当前没有活跃赏金任务",
    )


def _format_job_row(
    job: dict[str, Any],
    reward_pools: dict[str, list[PoolReward]],
    trans: TranslationIndex,
) -> tuple[str, ...]:
    key = str(job.get("jobType") or job.get("locationTag") or "")
    job_name = path_tail(trans.translate(key)) or "未知任务"
    if job.get("isVault"):
        job_name += " [保险库]"
    elif job.get("endless"):
        job_name += " [无尽]"
    meta_parts = [f"Lv.{job.get('minEnemyLevel', '?')}-{job.get('maxEnemyLevel', '?')}"]
    if isinstance(job.get("masteryReq"), int) and job["masteryReq"] > 0:
        meta_parts.append(f"MR {job['masteryReq']}")
    xp_list = job.get("xpAmounts") or []
    if isinstance(xp_list, list) and xp_list:
        meta_parts.append(f"声望 {sum(int(x) for x in xp_list):,}")
    rewards = reward_pools.get(str(job.get("rewards") or ""), [])
    reward_text = "、".join(r.display_name for r in rewards) if rewards else "—"
    return (job_name, "\n".join(meta_parts), reward_text)


def _find_syndicate_mission(missions: Any, tag: str) -> dict[str, Any] | None:
    if not isinstance(missions, list):
        return None
    for entry in missions:
        if isinstance(entry, dict) and entry.get("Tag") == tag and entry.get("Jobs"):
            return entry
    return None


def build_duviri_card(
    ws: dict[str, Any],
    weapons_en: dict[str, str],
    meta: QueryMeta,
) -> Card:
    """Build Duviri mood and Endless Circuit choices Card."""
    emotion = duviri_emotion_cycle(meta.now)
    choices = parse_duviri_choices(ws, weapons_en)
    rows: list[tuple[str, ...]] = [
        (category, " / ".join(items) if items else "暂无") for category, items in choices
    ]
    return Card(
        "双衍王境轮换",
        rows,
        subtitle(meta),
        columns=("类别", "本周可选列表"),
        kind="duviri",
        empty_message="当前没有无尽回廊轮换数据",
        highlight=f"当前情绪：{emotion.state} · 剩余 {emotion.remaining(meta.now)}",
    )


def _varzia_rows(
    trader: dict[str, Any], trans: TranslationIndex, now: float
) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    for entry in trader.get("Manifest") or []:
        if not isinstance(entry, dict):
            continue
        name = path_tail(strip_markup(trans.translate(str(entry.get("ItemType") or ""))))
        prime_price = entry.get("PrimePrice")
        reg_price = entry.get("RegularPrice")
        cost = (
            f"{prime_price} 御品阿耶"
            if isinstance(prime_price, int) and prime_price > 0
            else f"{reg_price} 阿耶"
            if isinstance(reg_price, int) and reg_price > 0
            else "—"
        )
        rows.append((name or "未知商品", cost, "当期轮换"))
    for sched in trader.get("ScheduleInfo") or []:
        if not isinstance(sched, dict):
            continue
        featured = path_tail(strip_markup(trans.translate(str(sched.get("FeaturedItem") or ""))))
        act = parse_mongo_time(sched.get("Activation"))
        when = (
            datetime.fromtimestamp(act, _UTC_PLUS_8).strftime("%m-%d %H:%M")
            if act is not None
            else "待定"
        )
        note = "进行中" if act is not None and act <= now else f"{when} 开启"
        rows.append((featured or "预告组合包", "轮换排期", note))
    return rows


def build_varzia_card(
    ws: dict[str, Any],
    nodes: dict[str, NodeInfo],
    trans: TranslationIndex,
    meta: QueryMeta,
    *,
    page: int = 1,
    page_size: int = 12,
) -> Card:
    """Build Varzia Prime Resurgence (`PrimeVaultTraders`) Card."""
    traders = ws.get("PrimeVaultTraders", [])
    if not isinstance(traders, list) or not traders or not isinstance(traders[0], dict):
        return Card(
            "瓦奇娅 · 圣装重生",
            [],
            subtitle(meta),
            columns=("商品 / 轮换", "消耗", "状态"),
            kind="varzia",
            empty_message="当前没有瓦奇娅圣装重生数据",
        )
    trader = traders[0]
    loc, _ = node_display(str(trader.get("Node") or ""), nodes)
    expiry = parse_mongo_time(trader.get("Expiry"))
    all_rows = list[tuple[str, ...]](_varzia_rows(trader, trans, meta.now))
    paged, cur_page, total_pages = paginate(all_rows, page, page_size)
    banner = f"{loc} · 离开倒计时 {format_remaining(expiry, meta.now)}"
    return Card(
        "瓦奇娅 · 圣装重生",
        paged,
        subtitle(meta, page_caption(cur_page, total_pages)),
        columns=("商品 / 轮换", "消耗", "状态"),
        kind="varzia",
        empty_message="当前暂无瓦奇娅商品清单",
        highlight=banner,
        stats_line=f"共收录 {len(all_rows)} 项商品与排期",
    )


_CONQUEST_TITLES: dict[str, str] = {
    "CT_LAB": "深层科研",
    "CT_HEX": "时光科研",
}

CONQUEST_MODIFIER_NAMES: dict[str, str] = {
    "abilitylockout": "技能封锁（全队击杀 50 名敌人后解锁）",
    "acceleratedenemies": "狂暴冒进（敌伤 -15%/受击 +15%，移速攻速 +15%）",
    "alchemicalshields": "炼金无敌护盾（10% 敌人带免疫元素盾，需元素瓶破盾）",
    "antiguard": "护盾失守（战甲与友方超宏防护获取 -75%）",
    "antimaterialweapons": "重装重炮（殁世重炮兵对超宏防护与机甲造成 5 倍伤害）",
    "aoedebuff": "爆炸范围缩减（范围伤害半径降低）",
    "arcadeautomata": "街机弹幕（敌人改为发射缓慢移动的巨型能量球）",
    "armorless": "护甲碎裂（施放技能使护甲降低 10%，持续 10 秒）",
    "artillerybeacons": "炮火信标（炽蛇军阵亡后掉落召唤炮击信标）",
    "balloonfest": "气球盛宴（炽蛇预兆兵数量增多且移速更快）",
    "channeldrain": "引导贪婪（开启引导技能每秒削减护盾上限）",
    "chemicalnoise": "噪音压制（无人机在 Flare 上方喷洒艾弗旺毒气）",
    "competitionspillover": "竞争蔓延（对决模式随机负面效果全程生效）",
    "contactdamage": "次生创伤（每次受伤附带 1 层穿刺异常状态）",
    "contaminationzone": "屏息毒区（全场持续造成随时间递增的毒素伤害）",
    "decayingflesh": "永久伤残（每次受到生命伤害会削减最大生命值）",
    "deflectors": "强固敌军（可能刷新守护者卓越者及机甲）",
    "disruptivesounds": "吸血摇滚（Flare 吸收能量回血并干扰技能）",
    "doubletrouble": "双重危机（每轮 2 台爆破殁世机甲，但生命值降低）",
    "doubletroublelegacyte": "有丝分裂（每轮出现 2 个传承种且需双倍捕获数）",
    "drainingresiduals": "恶魔契约（击杀 4m 内友军 +25% 射速但 -50% 弹药效率）",
    "dullblades": "钝化利刃（近战连击获取几率降低 50%）",
    "empblackhole": "引力猎犬（重型机犬蓄力时将战甲拉向自身）",
    "efervonfog": "艾弗旺浓雾（毒雾弥漫全场，击杀敌人可掉滤毒罐）",
    "energystarved": "能量枯竭（10m 内每有 1 名敌人每秒流失 2 点能量）",
    "escalateimmediately": "宝箱危机（未开启补给箱将使完成所需击杀数翻倍）",
    "exhaustion": "能量枯竭（10m 内每有 1 名敌人每秒流失 2 点能量）",
    "eximusgrenadiers": "卓越者元素罐（卓越者被击杀必定掉落元素罐）",
    "explosivecrawlers": "爆炸潜能（碎裂爬行者替换为自爆变体）",
    "explosiveenergy": "爆裂溃烂（敌人阵亡掉落冲向 Flare 的爆裂怪）",
    "explosivesummer": "过量炸药（所有补给箱替换为爆炸桶）",
    "factionswarm_scaldra": "炽蛇突袭（所有敌人替换为炽蛇军且高速移动）",
    "factionswarm_techrot": "科腐突袭（所有敌人替换为科腐者且高速移动）",
    "fallfog": "秋雾迷漫（浓雾大幅限制视野范围）",
    "fortifiedfoes": "密封装甲（敌人非弱点命中伤害降低 90%）",
    "fragilenodes": "协同破坏（敌人可直接攻击并摧毁导管）",
    "framecurse": "战甲诅咒综合征（每次施放技能损失 50 生命值）",
    "gearless": "携带限制（禁止使用携带道具选单）",
    "gestatingtumors": "孢子滋生（净化器旁生成瘤体加速维生下降）",
    "growingincursion": "裂隙级联（裂隙每 10 秒提升敌人 1 级，摧毁可停止）",
    "harshwords": "荆棘符文（拾取每个浮雕符文会造成微量伤害）",
    "heavywarfare": "重型武器战（非重型武器对敌伤害 -95%，召唤冷却缩至 5 秒）",
    "highscalinglegacyte": "生长激素（传承种逐代强化但逃脱时间更长）",
    "hostileovergrowth": "活体蔓生（地下停止移动会遭敌意菌蔓攻击）",
    "hostilesecurity": "感官侵蚀（仪典目标持续掉血，收集浮雕可治疗）",
    "infectedtechrot": "腐化血肉（科腐者死亡爆炸并留下致命艾弗旺毒池）",
    "infectedwounds": "感染创口（受击附带持续毒素/流血负面效果）",
    "infinitetide": "无尽潮汐（碎裂潮汐永不停止进攻）",
    "jadespring": "翠玉之灵（翠玉幽灵靠近后化为翠玉光束追击）",
    "knifestep": "如履刀尖（地面移动每秒损失 2 生命值，跳跃可暂停）",
    "lostintranslation": "符文倍增（激活安全系统所需符文数量翻倍）",
    "miasmitehive": "溃烂虫潮（科腐爆裂虫从阴影中成群涌出）",
    "murmurincursion": "墙后入侵（低语者加入炽蛇军与科腐者阵营）",
    "mutatedenemies": "平行进化（传承种进化时场上其他敌人同步获强化）",
    "necramechactivation": "机甲涌入（殁世机甲刷新频率大幅提高）",
    "operatorlockout": "传识失真（禁止切换指挥官与漂泊者）",
    "oversensitive": "高度敏感（负面异常状态持续时间变为 3 倍）",
    "pointblank": "近视弹药（只有 15m 内的玩家才能对敌人造成伤害）",
    "quicksand": "缠绕束缚（击杀敌人 4m 内友军移速与跑酷速度降低）",
    "rangedebuff": "技能范围缩减（战甲与武器范围效果降低）",
    "regeneratingenemies": "敌意再生（敌人生命值缓慢恢复）",
    "reinforcements": "协同前线（卓越者支援碎裂潮汐及其最终形态）",
    "shielddelay": "迟滞护盾（护盾充能延迟增加 500%）",
    "shieldedfoes": "坚壁好战（全部敌人获得等同生命上限 50% 的超宏防护）",
    "starvation": "弹药匮乏（掉落与道具恢复的弹药减少 75%）",
    "stickyfingers": "贪婪粗鬼（全部贪婪粗鬼均为卓越者单位）",
    "tankreinforcements": "援军支援（坦克首领战期间不断刷新援军）",
    "tankstrongarmor": "热美亚装甲（坦克仅受热美亚 RPG 伤害）",
    "tanksupertoxic": "剧毒坦克（坦克自带毒气光环并留下毒液轨迹）",
    "techrotconjunction": "蜂拥污染（科腐近战接触清道器使其污染度 +25%）",
    "timedilation": "技能缩时（所有技能持续时间降低 50%）",
    "undersupplied": "补给不足（全部武器最大备弹量降低 75%）",
    "unpoweredcapsules": "寄生维生塔（需在 15m 内击杀 20 名敌人方可激活维生塔）",
    "voidaberration": "吸血清道夫（不朽的虚空幽影靠近时吸取生命与能量）",
    "voidenergyoverload": "技能超载（施放技能在脚下开启虚空裂隙）",
    "voidburst": "死后震爆（被击杀的敌人爆炸释放虚空能量）",
    "volatilegrenades": "危险货物（搬运元素罐期间持续受到元素伤害）",
    "winterfrost": "厚重冰盾（极寒卓越者冰罩耐久提高至 30 倍）",
    "withering": "无法治疗（无法拾取生命球且拾取物不再回血）",
}


def _conquest_label(raw_code: str, trans: TranslationIndex) -> str:
    if not raw_code:
        return ""
    cleaned = path_tail(raw_code).strip()
    if (mapped := CONQUEST_MODIFIER_NAMES.get(cleaned.casefold())) is not None:
        return mapped
    translated = strip_markup(trans.translate(raw_code))
    return path_tail(translated) or cleaned


def _conquest_rows(conquest: dict[str, Any], trans: TranslationIndex) -> list[tuple[str, str, str]]:
    c_type = str(conquest.get("Type") or "")
    header = _CONQUEST_TITLES.get(c_type, c_type or "科研任务")
    rows: list[tuple[str, str, str]] = [(f"§{header}", "", "")]
    for idx, mission in enumerate(conquest.get("Missions") or [], 1):
        if not isinstance(mission, dict):
            continue
        m_name = mission_name(mission.get("missionType"))
        f_name = compact_faction(mission.get("faction"))
        details: list[str] = []
        for diff in mission.get("difficulties") or []:
            if not isinstance(diff, dict):
                continue
            dev = _conquest_label(str(diff.get("deviation") or ""), trans)
            risks = [
                _conquest_label(str(rv), trans)
                for rv in (diff.get("riskVariables") or [])
                if isinstance(rv, str) and rv
            ]
            line = " / ".join(x for x in (dev, "、".join(risks)) if x)
            if line and line not in details:
                details.append(line)
        rows.append((f"阶段 {idx}", f"{f_name} · {m_name}", "\n".join(details) or "标准条件"))
    personal = [
        _conquest_label(str(v), trans)
        for v in (conquest.get("Variables") or [])
        if isinstance(v, str) and v
    ]
    if personal:
        rows.append(("个人词条", "本周限定", "\n".join(personal)))
    return rows


def build_conquest_card(
    ws: dict[str, Any],
    trans: TranslationIndex,
    meta: QueryMeta,
) -> Card:
    """Build weekly Deep & Temporal Archimedea (`Conquests`) Card."""
    conquests = [c for c in (ws.get("Conquests") or []) if isinstance(c, dict)]
    if not conquests:
        return Card(
            "每周科研",
            [],
            subtitle(meta),
            columns=("阶段", "派系 / 任务", "偏差与风险变量"),
            kind="conquest",
            empty_message="当前没有活跃的科研轮换数据",
        )
    rows: list[tuple[str, ...]] = []
    for conquest in conquests:
        rows.extend(_conquest_rows(conquest, trans))
    expiry = parse_mongo_time(conquests[0].get("Expiry"))
    return Card(
        "每周科研",
        rows,
        subtitle(meta, f"重置剩余 {format_remaining(expiry, meta.now)}"),
        columns=("阶段", "派系 / 任务", "偏差与风险变量"),
        kind="conquest",
        empty_message="当前没有科研关卡数据",
    )


def _pick_event_message(messages: Any) -> str:
    if not isinstance(messages, list):
        return ""
    preferred: dict[str, str] = {}
    fallback = ""
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        code = str(msg.get("LanguageCode") or "").casefold()
        text = str(msg.get("Message") or "").strip()
        if not text:
            continue
        preferred[code] = text
        fallback = fallback or text
    for lang in ("zh", "zh-hans", "zhs", "en"):
        if lang in preferred:
            return preferred[lang]
    return fallback


def build_news_card(
    ws: dict[str, Any],
    meta: QueryMeta,
    *,
    page: int = 1,
    page_size: int = 10,
) -> Card:
    """Build official Warframe news/events Card from `Events`."""
    raw_events = [e for e in (ws.get("Events") or []) if isinstance(e, dict)]
    items: list[tuple[float, tuple[str, str, str]]] = []
    for event in raw_events:
        msg = _pick_event_message(event.get("Messages"))
        if not msg:
            continue
        dt = (
            parse_mongo_time(event.get("Date"))
            or parse_mongo_time(event.get("EventStartDate"))
            or 0.0
        )
        end_dt = parse_mongo_time(event.get("EventEndDate"))
        tag = "置顶" if event.get("Priority") else ("社区" if event.get("Community") else "公告")
        time_text = (
            f"剩 {compact_remaining(end_dt, meta.now)}"
            if end_dt is not None and end_dt > meta.now
            else datetime.fromtimestamp(dt, _UTC_PLUS_8).strftime("%m-%d %H:%M")
            if dt > 0
            else "—"
        )
        items.append((dt, (tag, msg, time_text)))
    items.sort(key=lambda item: item[0], reverse=True)
    flat_rows: list[tuple[str, ...]] = [item[1] for item in items]
    paged, cur_page, total_pages = paginate(flat_rows, page, page_size)
    return Card(
        "官方新闻与活动",
        paged,
        subtitle(meta, page_caption(cur_page, total_pages)),
        columns=("类型", "标题 / 内容", "时间 / 剩余"),
        kind="news",
        empty_message="当前没有官方新闻条目",
    )


def build_timings_card(
    ws: dict[str, Any],
    meta: QueryMeta,
    *,
    arbys_summary: tuple[str, str] | None = None,
) -> Card:
    """Build consolidated countdown overview Card combining cycles and major timers."""
    now = meta.now
    rows: list[tuple[str, ...]] = [("§开放世界与周期", "", "")]
    try:
        for cycle in calculate_cycles(ws, now):
            rows.append((cycle.name, cycle.state, cycle.remaining(now)))
    except QueryError:
        duviri = duviri_emotion_cycle(now)
        rows.append((duviri.name, duviri.state, duviri.remaining(now)))
    rows.append(("§日常与轮换节点", "", ""))
    sorties = ws.get("Sorties", [])
    if isinstance(sorties, list) and sorties and isinstance(sorties[0], dict):
        s_exp = parse_mongo_time(sorties[0].get("Expiry"))
        rows.append(("每日突击", "进行中", compact_remaining(s_exp, now)))
    hunts = ws.get("LiteSorties", [])
    if isinstance(hunts, list) and hunts and isinstance(hunts[0], dict):
        h_exp = parse_mongo_time(hunts[0].get("Expiry"))
        rows.append(("执刑官猎杀", "本周进行中", compact_remaining(h_exp, now)))
    traders = ws.get("VoidTraders", [])
    if isinstance(traders, list) and traders and isinstance(traders[0], dict):
        t = traders[0]
        act, exp = parse_mongo_time(t.get("Activation")), parse_mongo_time(t.get("Expiry"))
        if act is not None and now < act:
            rows.append(("虚空商人", "尚未到达", compact_remaining(act, now)))
        else:
            rows.append(("虚空商人", "营业中", compact_remaining(exp, now)))
    if arbys_summary is not None:
        rows.append(("当前仲裁", arbys_summary[0], arbys_summary[1]))
    return Card(
        "全局时效总览",
        rows,
        subtitle(meta),
        columns=("项目", "当前状态", "切换 / 剩余"),
        kind="timings",
        empty_message="暂无时效数据",
    )


def build_help_card() -> Card:
    """Build structured image/text help menu Card covering all v0.6.0 commands."""
    rows: list[tuple[str, ...]] = [
        ("基础总览", "/时效 | /状态 | /帮助", "一图全局倒计时总览、本地索引统计与菜单"),
        (
            "开放世界",
            "/平原 | /轮换 | /地球赏金 | /金星赏金 | /火卫二赏金",
            "六大周期、双衍王境与三大集团赏金",
        ),
        (
            "世界活动",
            "/警报 | /突击 | /猎杀 | /入侵 | /新闻",
            "实时任务、每周三阶段及官方公告时间流",
        ),
        (
            "裂隙筛选",
            "/裂缝 [关键词] | /钢铁裂缝 | /九重天裂缝",
            "纪元分组简写卡片，支持关键词筛选与翻页",
        ),
        (
            "商人轮换",
            "/奸商 | /瓦奇娅 | /科研 | /钢铁 | /电波 | /特惠 | /1999",
            "虚空商人 / 圣装重生 / 科研 / 钢铁 / 日历",
        ),
        (
            "仲裁遗物",
            "/仲裁 | /仲裁表 [所有] | /遗物 <词> | /开核桃",
            "仲裁评级前瞻、遗物掉落与光辉单车期望排行",
        ),
        (
            "效率计算",
            "/翻译 <词> | /融合 <当前%> [目标%] | /升级消耗",
            "中英双向词典、心智融合步数与核心星币计算",
        ),
        (
            "市场垃圾",
            "/wm <物品> [买家] [满级] [-en] | /金垃圾 | /银垃圾 | /铜垃圾",
            "含 48h/90d 成交均价、/w 1 预览与分档杜卡德",
        ),
        (
            "拍卖私聊",
            "/wr <武器> [词条/零洗/v槽/3+1/1000p] | /cd | /xt | /w <号>",
            "紫卡(含 R8 偏差)/玄骸拍卖检索与一键私聊",
        ),
        (
            "紫卡分析",
            "/紫卡分析",
            "暂未添加紫卡分析功能",
        ),
        (
            "订阅铸造",
            "/订阅 <类型> [时段 9-22] [单次] | /铸造提醒 <名> [时长]",
            "/订阅列表 /退订 | /铸造列表 /取消铸造",
        ),
    ]
    return Card(
        "Milo bot · Warframe 指令菜单",
        rows,
        "国际服 PC · 群聊可附加 @Milo 前缀 · /wm /wr /cd /xt /w 支持无斜杠触发",
        columns=("分类", "指令与常用参数", "功能说明"),
        kind="help",
        highlight="支持 -1/-w 纯文本 · -2/-3 翻页 · /wm -en 英文模式",
    )
