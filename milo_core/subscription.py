"""WorldState/Arbitration event subscriptions, SQLite store, and per-stream deduplication."""

from __future__ import annotations

import json
import re
import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .arbitration import ARBITRATION_DURATION, mission_faction_for_node, normalized_tier
from .cache import ensure_schema
from .card_model import Card, CardKind
from .cycles import calculate_cycles, utc_time
from .dictionary import NodeInfo, TranslationIndex
from .errors import QueryError
from .worldstate import (
    MISSION_TYPE_NAMES,
    VOID_TIERS,
    QueryMeta,
    build_archon_card,
    build_sortie_card,
    build_void_trader_card,
    faction_name,
    format_remaining,
    format_reward,
    invasion_reward_text,
    node_display,
    node_mission_faction,
    parse_mongo_time,
    subtitle,
)

SUBSCRIPTION_LABELS: dict[str, str] = {
    "alerts": "警报",
    "fissures": "裂缝",
    "sortie": "突击",
    "archon": "执刑官猎杀",
    "invasions": "入侵",
    "void_trader": "虚空商人",
    "cycles": "平原周期",
    "arbitration": "仲裁",
}

SUBSCRIPTION_ALIASES: dict[str, tuple[str, dict[str, Any]]] = {
    "警报": ("alerts", {}),
    "alert": ("alerts", {}),
    "alerts": ("alerts", {}),
    "裂缝": ("fissures", {}),
    "裂隙": ("fissures", {}),
    "虚空裂缝": ("fissures", {}),
    "虚空裂隙": ("fissures", {}),
    "fissure": ("fissures", {}),
    "fissures": ("fissures", {}),
    "普通裂缝": ("fissures", {"mode": "normal"}),
    "普通裂隙": ("fissures", {"mode": "normal"}),
    "钢铁裂缝": ("fissures", {"mode": "steel"}),
    "钢铁裂隙": ("fissures", {"mode": "steel"}),
    "九重天裂缝": ("fissures", {"mode": "storm"}),
    "九重天裂隙": ("fissures", {"mode": "storm"}),
    "虚空风暴": ("fissures", {"mode": "storm"}),
    "突击": ("sortie", {}),
    "sortie": ("sortie", {}),
    "sorties": ("sortie", {}),
    "猎杀": ("archon", {}),
    "执刑官": ("archon", {}),
    "执刑官猎杀": ("archon", {}),
    "archon": ("archon", {}),
    "入侵": ("invasions", {}),
    "invasion": ("invasions", {}),
    "invasions": ("invasions", {}),
    "奸商": ("void_trader", {}),
    "虚空商人": ("void_trader", {}),
    "void_trader": ("void_trader", {}),
    "baro": ("void_trader", {}),
    "平原": ("cycles", {}),
    "平原周期": ("cycles", {}),
    "周期": ("cycles", {}),
    "夜灵": ("cycles", {"areas": ["夜灵平原"]}),
    "夜灵平原": ("cycles", {"areas": ["夜灵平原"]}),
    "地球": ("cycles", {"areas": ["地球"]}),
    "双衍": ("cycles", {"areas": ["双衍王境"]}),
    "双衍王境": ("cycles", {"areas": ["双衍王境"]}),
    "扎里曼": ("cycles", {"areas": ["扎里曼"]}),
    "cycles": ("cycles", {}),
    "cycle": ("cycles", {}),
    "仲裁": ("arbitration", {}),
    "arbitration": ("arbitration", {}),
    "arbys": ("arbitration", {}),
}

_FISSURE_MODES: dict[str, str] = {
    "普通": "normal",
    "normal": "normal",
    "钢铁": "steel",
    "钢铁之路": "steel",
    "steel": "steel",
    "sp": "steel",
    "九重天": "storm",
    "风暴": "storm",
    "storm": "storm",
}

_FISSURE_MODE_LABELS: dict[str, str] = {
    "normal": "普通",
    "steel": "钢铁",
    "storm": "九重天",
}

_TIER_ALIASES: dict[str, str] = {
    "古纪": "古纪",
    "lith": "古纪",
    "前纪": "前纪",
    "meso": "前纪",
    "中纪": "中纪",
    "neo": "中纪",
    "后纪": "后纪",
    "axi": "后纪",
    "安魂": "安魂",
    "requiem": "安魂",
    "全能": "全能",
    "omnia": "全能",
}

_MISSION_FILTER_NAMES = frozenset(MISSION_TYPE_NAMES.values())

_CYCLE_AREAS: dict[str, str] = {
    "全部": "all",
    "所有": "all",
    "all": "all",
    "地球": "地球",
    "earth": "地球",
    "夜灵": "夜灵平原",
    "夜灵平原": "夜灵平原",
    "cetus": "夜灵平原",
    "奥布山谷": "奥布山谷",
    "奥布": "奥布山谷",
    "金星": "奥布山谷",
    "vallis": "奥布山谷",
    "魔胎之境": "魔胎之境",
    "魔胎": "魔胎之境",
    "火卫二": "魔胎之境",
    "cambion": "魔胎之境",
    "扎里曼": "扎里曼",
    "zariman": "扎里曼",
    "双衍": "双衍王境",
    "双衍王境": "双衍王境",
    "duviri": "双衍王境",
}

_CYCLE_STATES: dict[str, str] = {
    "白昼": "白昼",
    "白天": "白昼",
    "day": "白昼",
    "夜晚": "夜晚",
    "黑夜": "夜晚",
    "晚上": "夜晚",
    "night": "夜晚",
    "温暖": "温暖",
    "warm": "温暖",
    "寒冷": "寒冷",
    "cold": "寒冷",
    "fass": "FASS",
    "vome": "VOME",
    "corpus": "Corpus",
    "grineer": "Grineer",
    "悲伤": "悲伤",
    "恐惧": "恐惧",
    "喜悦": "喜悦",
    "愤怒": "愤怒",
    "嫉妒": "嫉妒",
}

_STATE_DEFAULT_AREAS: dict[str, str] = {
    "FASS": "魔胎之境",
    "VOME": "魔胎之境",
    "温暖": "奥布山谷",
    "寒冷": "奥布山谷",
    "Corpus": "扎里曼",
    "Grineer": "扎里曼",
    "悲伤": "双衍王境",
    "恐惧": "双衍王境",
    "喜悦": "双衍王境",
    "愤怒": "双衍王境",
    "嫉妒": "双衍王境",
}

_ARBYS_TIERS = frozenset({"S", "A", "B", "C", "D", "F"})


@dataclass(frozen=True)
class SubscriptionRule:
    """Persisted per-stream subscription rule."""

    stream_id: str
    event_type: str
    filters: dict[str, Any]
    created_at: float


@dataclass(frozen=True)
class DetectedEvent:
    """Normalized active WorldState/Arbitration event evaluated against subscription rules."""

    event_type: str
    event_key: str
    row: tuple[str, ...]
    search_text: str
    mode: str = ""
    tier: str = ""
    mission: str = ""
    area: str = ""
    state: str = ""
    card: Card | None = None


_UTC_PLUS_8 = timezone(timedelta(hours=8))
_HOURS_RE = re.compile(r"^(?:时段)?(\d{1,2})(?:点)?[-~到至](\d{1,2})(?:点)?$")
_DURATION_PART_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(天|d|小时|时|h|分钟|分|m)", re.IGNORECASE)


@dataclass(frozen=True)
class PendingNotification:
    """One grouped notification card destined for one subscribed stream."""

    stream_id: str
    event_type: str
    event_keys: list[str]
    card: Card
    once: bool = False


@dataclass(frozen=True)
class FoundryReminder:
    """One persisted personal Warframe Foundry completion reminder."""

    reminder_id: int
    stream_id: str
    user_id: str
    item_name: str
    due_at: float


def _parse_hour_window(token: str) -> list[int] | None:
    match = _HOURS_RE.fullmatch(token.strip())
    if match is None:
        return None
    start, end = int(match.group(1)), int(match.group(2))
    if not 0 <= start <= 23 or not 0 <= end <= 23:
        raise QueryError("推送时段小时范围须为 0-23，例如：时段 9-22。")
    return [start, end]


def _strip_schedule_flags(tokens: list[str]) -> tuple[list[str], bool, list[int] | None]:
    kept: list[str] = []
    once = False
    active_hours: list[int] | None = None
    index = 0
    while index < len(tokens):
        token = tokens[index]
        low = token.casefold()
        if low in {"单次", "一次", "once"}:
            once = True
        elif token == "时段" and index + 1 < len(tokens):
            parsed = _parse_hour_window(tokens[index + 1])
            if parsed is None:
                raise QueryError("时段格式错误，示例：时段 9-22。")
            active_hours = parsed
            index += 1
        elif (parsed := _parse_hour_window(token)) is not None:
            active_hours = parsed
        else:
            kept.append(token)
        index += 1
    return kept, once, active_hours


def _merge_schedule_flags(
    filters: dict[str, Any], once: bool, active_hours: list[int] | None
) -> dict[str, Any]:
    merged = dict(filters)
    if once:
        merged["once"] = True
    if active_hours is not None:
        merged["active_hours"] = active_hours
    return merged


def parse_subscribe_spec(raw_args: str) -> tuple[str, dict[str, Any]]:
    """Parse `/订阅 <类型> [条件]` into canonical event_type and filter dictionary."""
    tokens = raw_args.split()
    if not tokens:
        raise QueryError("请指定要订阅的事件类型，例如：/订阅 警报")
    entry = SUBSCRIPTION_ALIASES.get(tokens[0].casefold())
    if entry is None:
        supported = "、".join(SUBSCRIPTION_LABELS.values())
        raise QueryError(f"不支持的订阅类型“{tokens[0]}”，可用类型：{supported}。")
    event_type, base_filters = entry
    rest, once, active_hours = _strip_schedule_flags(tokens[1:])
    if event_type == "fissures":
        filters = _parse_fissure_filters(rest, base_filters)
    elif event_type == "cycles":
        filters = _parse_cycle_filters(rest, base_filters)
    elif event_type == "arbitration":
        filters = _parse_arbitration_filters(rest)
    elif event_type == "void_trader":
        if rest:
            raise QueryError("虚空商人订阅无需额外过滤参数，直接使用：/订阅 奸商。")
        filters = {}
    else:
        kw = " ".join(rest).strip()
        filters = {"keyword": kw} if kw else {}
    return event_type, _merge_schedule_flags(filters, once, active_hours)


def _parse_fissure_filters(tokens: list[str], defaults: dict[str, Any]) -> dict[str, Any]:
    mode = str(defaults.get("mode") or "")
    tiers: list[str] = []
    missions: list[str] = []
    kw_tokens: list[str] = []
    for token in tokens:
        lower = token.casefold()
        if lower in _FISSURE_MODES:
            mode = _FISSURE_MODES[lower]
        elif lower in _TIER_ALIASES:
            tiers.append(_TIER_ALIASES[lower])
        elif token in _MISSION_FILTER_NAMES:
            missions.append(token)
        else:
            kw_tokens.append(token)
    filters: dict[str, Any] = {}
    if mode:
        filters["mode"] = mode
    if tiers:
        filters["tiers"] = list(dict.fromkeys(tiers))
    if missions:
        filters["missions"] = list(dict.fromkeys(missions))
    if kw_tokens:
        filters["keyword"] = " ".join(kw_tokens)
    return filters


def _parse_cycle_filters(tokens: list[str], defaults: dict[str, Any]) -> dict[str, Any]:
    areas: list[str] = list(defaults.get("areas") or [])
    states: list[str] = []
    for token in tokens:
        lower = token.casefold()
        if lower in _CYCLE_AREAS:
            areas.append(_CYCLE_AREAS[lower])
        elif lower in _CYCLE_STATES:
            states.append(_CYCLE_STATES[lower])
        else:
            raise QueryError(
                f"无法识别的平原筛选条件“{token}”，可用区域：夜灵平原/地球/奥布山谷/魔胎之境/扎里曼/双衍王境/全部。"
            )
    if not areas:
        inferred = {_STATE_DEFAULT_AREAS.get(state, "夜灵平原") for state in states}
        areas = sorted(inferred) if inferred else ["夜灵平原"]
    filters: dict[str, Any] = {"areas": ["all"] if "all" in areas else list(dict.fromkeys(areas))}
    if states:
        filters["states"] = list(dict.fromkeys(states))
    return filters


def _parse_arbitration_filters(tokens: list[str]) -> dict[str, Any]:
    tiers: list[str] = []
    kw_tokens: list[str] = []
    for token in tokens:
        upper = token.upper()
        if upper in _ARBYS_TIERS:
            tiers.append(upper)
        else:
            kw_tokens.append(token)
    filters: dict[str, Any] = {}
    if tiers:
        filters["tiers"] = list(dict.fromkeys(tiers))
    if kw_tokens:
        filters["keyword"] = " ".join(kw_tokens)
    return filters


def parse_unsubscribe_target(raw_args: str) -> str:
    """Parse `/退订 <类型|全部>` into 'all' or canonical event_type."""
    cleaned = raw_args.strip().casefold()
    if not cleaned:
        raise QueryError("请指定要退订的类型或“全部”，例如：/退订 警报 或 /退订 全部。")
    if cleaned in {"全部", "所有", "all", "*"}:
        return "all"
    entry = SUBSCRIPTION_ALIASES.get(cleaned)
    if entry is None:
        supported = "、".join(SUBSCRIPTION_LABELS.values())
        raise QueryError(f"不支持的退订类型“{raw_args.strip()}”，可用类型：{supported} 或 全部。")
    return entry[0]


def _append_schedule_summary(parts: list[str], filters: dict[str, Any]) -> None:
    if kw := filters.get("keyword"):
        parts.append(f"关键词“{kw}”")
    hours = filters.get("active_hours")
    if isinstance(hours, list) and len(hours) == 2:
        parts.append(f"时段 {hours[0]:02d}-{hours[1]:02d}")
    if filters.get("once"):
        parts.append("单次")


def format_filter_summary(event_type: str, filters: dict[str, Any]) -> str:
    """Format a subscription filter dict into concise Chinese text."""
    parts: list[str] = []
    if mode := filters.get("mode"):
        parts.append(_FISSURE_MODE_LABELS.get(str(mode), str(mode)))
    if tiers := filters.get("tiers"):
        joined = "/".join(str(item) for item in tiers)
        parts.append(f"{joined}级" if event_type == "arbitration" else joined)
    if missions := filters.get("missions"):
        parts.append("/".join(str(item) for item in missions))
    if areas := filters.get("areas"):
        parts.append("全部区域" if "all" in areas else "/".join(str(item) for item in areas))
    if states := filters.get("states"):
        parts.append("/".join(str(item) for item in states))
    _append_schedule_summary(parts, filters)
    return " · ".join(parts) if parts else "全部事件"


class SubscriptionStore:
    """Persist subscription rules and per-stream delivery deduplication keys in SQLite."""

    def __init__(self, db_path: Path) -> None:
        self.path = db_path

    def initialize(self) -> None:
        """Create required tables if absent."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=5.0)) as conn:
            ensure_schema(conn)

    def upsert(
        self,
        stream_id: str,
        event_type: str,
        filters: dict[str, Any],
        *,
        now: float | None = None,
    ) -> SubscriptionRule:
        """Insert or update one stream subscription rule."""
        ts = time.time() if now is None else now
        encoded = json.dumps(filters, ensure_ascii=False, sort_keys=True)
        with closing(sqlite3.connect(self.path, timeout=5.0)) as conn:
            conn.execute(
                "INSERT INTO subscriptions (stream_id, event_type, filter_json, created_at) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(stream_id, event_type) DO UPDATE "
                "SET filter_json=excluded.filter_json, created_at=excluded.created_at",
                (stream_id, event_type, encoded, ts),
            )
            conn.commit()
        return SubscriptionRule(stream_id, event_type, dict(filters), ts)

    def remove(self, stream_id: str, event_type: str) -> bool:
        """Delete one subscription rule for a stream."""
        with closing(sqlite3.connect(self.path, timeout=5.0)) as conn:
            cursor = conn.execute(
                "DELETE FROM subscriptions WHERE stream_id = ? AND event_type = ?",
                (stream_id, event_type),
            )
            conn.commit()
            return cursor.rowcount > 0

    def remove_all(self, stream_id: str) -> int:
        """Delete all subscription rules for a stream."""
        with closing(sqlite3.connect(self.path, timeout=5.0)) as conn:
            cursor = conn.execute("DELETE FROM subscriptions WHERE stream_id = ?", (stream_id,))
            conn.commit()
            return cursor.rowcount

    def list_for_stream(self, stream_id: str) -> list[SubscriptionRule]:
        """Return active rules for one stream ordered by creation time."""
        with closing(sqlite3.connect(self.path, timeout=5.0)) as conn:
            rows = conn.execute(
                "SELECT stream_id, event_type, filter_json, created_at "
                "FROM subscriptions WHERE stream_id = ? ORDER BY created_at ASC, event_type ASC",
                (stream_id,),
            ).fetchall()
        return [_row_to_rule(row) for row in rows]

    def list_all(self) -> list[SubscriptionRule]:
        """Return all persisted rules across every stream."""
        with closing(sqlite3.connect(self.path, timeout=5.0)) as conn:
            rows = conn.execute(
                "SELECT stream_id, event_type, filter_json, created_at "
                "FROM subscriptions ORDER BY stream_id ASC, created_at ASC",
            ).fetchall()
        return [_row_to_rule(row) for row in rows]

    def has_delivered(self, stream_id: str, event_key: str) -> bool:
        """Return whether an event key was already delivered to a specific stream."""
        with closing(sqlite3.connect(self.path, timeout=5.0)) as conn:
            row = conn.execute(
                "SELECT 1 FROM subscription_deliveries WHERE stream_id = ? AND event_key = ?",
                (stream_id, event_key),
            ).fetchone()
        return row is not None

    def delivered_keys_for_stream(self, stream_id: str, keys: list[str]) -> set[str]:
        """Fetch already-delivered keys for one stream across arbitrary batches."""
        unique = list(dict.fromkeys(keys))
        if not unique:
            return set()
        found: set[str] = set()
        with closing(sqlite3.connect(self.path, timeout=5.0)) as conn:
            for offset in range(0, len(unique), 400):
                batch = unique[offset : offset + 400]
                placeholders = ",".join("?" for _ in batch)
                sql = (
                    "SELECT event_key FROM subscription_deliveries "
                    f"WHERE stream_id = ? AND event_key IN ({placeholders})"
                )
                rows = conn.execute(sql, (stream_id, *batch)).fetchall()
                found.update(str(row[0]) for row in rows)
        return found

    def record_deliveries(
        self,
        stream_id: str,
        event_keys: list[str],
        *,
        now: float | None = None,
    ) -> None:
        """Record successfully delivered keys for one stream only."""
        unique = list(dict.fromkeys(event_keys))
        if not unique:
            return
        ts = time.time() if now is None else now
        with closing(sqlite3.connect(self.path, timeout=5.0)) as conn:
            conn.executemany(
                "INSERT OR IGNORE INTO subscription_deliveries "
                "(stream_id, event_key, delivered_at) VALUES (?, ?, ?)",
                [(stream_id, key, ts) for key in unique],
            )
            conn.commit()

    def prune_deliveries(self, before_ts: float) -> int:
        """Remove historical delivery markers older than the cutoff timestamp."""
        with closing(sqlite3.connect(self.path, timeout=5.0)) as conn:
            cursor = conn.execute(
                "DELETE FROM subscription_deliveries WHERE delivered_at < ?",
                (before_ts,),
            )
            conn.commit()
            return cursor.rowcount


def _row_to_rule(row: tuple[Any, ...]) -> SubscriptionRule:
    try:
        parsed = json.loads(str(row[2]))
        filters = parsed if isinstance(parsed, dict) else {}
    except ValueError:
        filters = {}
    return SubscriptionRule(str(row[0]), str(row[1]), filters, float(row[3]))


def _extract_oid(raw: dict[str, Any]) -> str:
    raw_id = raw.get("_id")
    if isinstance(raw_id, dict) and raw_id.get("$oid"):
        return str(raw_id["$oid"]).strip()
    if raw.get("id"):
        return str(raw["id"]).strip()
    if raw.get("Id"):
        return str(raw["Id"]).strip()
    return ""


def _ts_token(value: Any) -> str:
    try:
        return str(int(value["$date"]["$numberLong"]))
    except (TypeError, KeyError, ValueError):
        return ""


def detect_alerts(
    ws: dict[str, Any],
    nodes: dict[str, NodeInfo],
    trans: TranslationIndex,
    now: float,
) -> list[DetectedEvent]:
    """Extract active Alert events with stable IDs."""
    events: list[DetectedEvent] = []
    for raw in ws.get("Alerts", []):
        if not isinstance(raw, dict):
            continue
        info = raw.get("MissionInfo")
        if not isinstance(info, dict):
            continue
        expiry = parse_mongo_time(raw.get("Expiry"))
        if expiry is not None and expiry <= now:
            continue
        loc, node_info = node_display(str(info.get("location") or ""), nodes)
        mission_col = node_mission_faction(node_info, info.get("missionType"), info.get("faction"))
        reward_text = format_reward(info.get("missionReward"), trans) or "无道具奖励"
        uid = _extract_oid(raw) or (
            f"{info.get('location')}:{info.get('missionType')}:"
            f"{_ts_token(raw.get('Expiry'))}:{reward_text}"
        )
        events.append(
            DetectedEvent(
                "alerts",
                f"alerts:{uid}",
                (loc, mission_col, reward_text, format_remaining(expiry, now)),
                f"{loc} {mission_col} {reward_text}",
                mission=mission_col,
            )
        )
    return events


def detect_fissures(
    ws: dict[str, Any],
    nodes: dict[str, NodeInfo],
    now: float,
) -> list[DetectedEvent]:
    """Extract active normal, Steel Path, and Void Storm fissure events."""
    events: list[DetectedEvent] = []
    sources: tuple[tuple[str, list[Any]], ...] = (
        ("active", ws.get("ActiveMissions", [])),
        ("storm", ws.get("VoidStorms", [])),
    )
    for source_kind, items in sources:
        if not isinstance(items, list):
            continue
        for raw in items:
            if not isinstance(raw, dict):
                continue
            expiry = parse_mongo_time(raw.get("Expiry"))
            if expiry is not None and expiry <= now:
                continue
            mode = (
                "storm"
                if source_kind == "storm"
                else ("steel" if bool(raw.get("Hard")) else "normal")
            )
            tier_key = "ActiveMissionTier" if mode == "storm" else "Modifier"
            tier_label, _ = VOID_TIERS.get(str(raw.get(tier_key) or ""), ("未知", 99))
            loc, node_info = node_display(str(raw.get("Node") or ""), nodes)
            mission_col = node_mission_faction(
                node_info,
                None if mode == "storm" else raw.get("MissionType"),
                raw.get("Faction"),
            )
            display_col = (
                f"[{_FISSURE_MODE_LABELS[mode]}] {mission_col}" if mode != "normal" else mission_col
            )
            uid = _extract_oid(raw) or (
                f"{mode}:{raw.get('Node')}:{raw.get(tier_key)}:{_ts_token(raw.get('Expiry'))}"
            )
            events.append(
                DetectedEvent(
                    "fissures",
                    f"fissures:{uid}",
                    (tier_label, loc, display_col, format_remaining(expiry, now)),
                    f"{_FISSURE_MODE_LABELS[mode]} {tier_label} {loc} {mission_col}",
                    mode=mode,
                    tier=tier_label,
                    mission=mission_col,
                )
            )
    return events


def detect_invasions(
    ws: dict[str, Any],
    nodes: dict[str, NodeInfo],
    trans: TranslationIndex,
) -> list[DetectedEvent]:
    """Extract active Invasion events."""
    events: list[DetectedEvent] = []
    for raw in ws.get("Invasions", []):
        if not isinstance(raw, dict) or raw.get("Completed"):
            continue
        loc, _ = node_display(str(raw.get("Node") or ""), nodes)
        atk_rew = invasion_reward_text(raw.get("AttackerReward"), trans)
        def_rew = invasion_reward_text(raw.get("DefenderReward"), trans)
        goal = float(raw.get("Goal") or 0)
        count = float(raw.get("Count") or 0)
        progress = min(abs(count) / goal, 1.0) if goal else 0.0
        atk_fac = faction_name(raw.get("Faction"))
        def_fac = faction_name(raw.get("DefenderFaction"))
        vs_text = f"{atk_fac}\nvs {def_fac}"
        uid = _extract_oid(raw) or f"{raw.get('Node')}:{_ts_token(raw.get('Activation'))}:{atk_rew}"
        events.append(
            DetectedEvent(
                "invasions",
                f"invasions:{uid}",
                (loc, vs_text, f"攻：{atk_rew}\n守：{def_rew}", f"{progress * 100:.1f}%"),
                f"{loc} {atk_rew} {def_rew} {atk_fac} {def_fac}",
            )
        )
    return events


def detect_sortie(
    ws: dict[str, Any],
    nodes: dict[str, NodeInfo],
    meta: QueryMeta,
) -> list[DetectedEvent]:
    """Extract today's active Sortie rotation as a single notification event."""
    sorties = ws.get("Sorties", [])
    if not isinstance(sorties, list) or not sorties or not isinstance(sorties[0], dict):
        return []
    sortie = sorties[0]
    expiry = parse_mongo_time(sortie.get("Expiry"))
    if expiry is not None and expiry <= meta.now:
        return []
    card = build_sortie_card(ws, nodes, meta)
    uid = _extract_oid(sortie) or f"{sortie.get('Boss')}:{_ts_token(sortie.get('Expiry'))}"
    search = " ".join([card.highlight, *(" ".join(row) for row in card.rows)])
    return [DetectedEvent("sortie", f"sortie:{uid}", (), search, card=card)]


def detect_archon(
    ws: dict[str, Any],
    nodes: dict[str, NodeInfo],
    meta: QueryMeta,
) -> list[DetectedEvent]:
    """Extract this week's Archon Hunt as a single notification event."""
    hunts = ws.get("LiteSorties", [])
    if not isinstance(hunts, list) or not hunts or not isinstance(hunts[0], dict):
        return []
    hunt = hunts[0]
    expiry = parse_mongo_time(hunt.get("Expiry"))
    if expiry is not None and expiry <= meta.now:
        return []
    card = build_archon_card(ws, nodes, meta)
    uid = _extract_oid(hunt) or f"{hunt.get('Boss')}:{_ts_token(hunt.get('Expiry'))}"
    search = " ".join([card.highlight, *(" ".join(row) for row in card.rows)])
    return [DetectedEvent("archon", f"archon:{uid}", (), search, card=card)]


def detect_void_trader(
    ws: dict[str, Any],
    nodes: dict[str, NodeInfo],
    trans: TranslationIndex,
    meta: QueryMeta,
) -> list[DetectedEvent]:
    """Emit Void Trader events when arriving within 1h or actively trading."""
    traders = ws.get("VoidTraders", [])
    if not isinstance(traders, list) or not traders or not isinstance(traders[0], dict):
        return []
    trader = traders[0]
    activation = parse_mongo_time(trader.get("Activation"))
    expiry = parse_mongo_time(trader.get("Expiry"))
    if expiry is not None and expiry <= meta.now:
        return []
    uid = _extract_oid(trader) or f"{trader.get('Node')}:{_ts_token(trader.get('Activation'))}"
    manifest = trader.get("Manifest")
    is_active = (activation is None or activation <= meta.now) and bool(manifest)
    is_soon = activation is not None and 0 < activation - meta.now <= 3_600
    if not is_active and not is_soon:
        return []
    card = build_void_trader_card(ws, nodes, trans, meta)
    phase = "arrived" if is_active else "soon"
    return [
        DetectedEvent("void_trader", f"void_trader:{phase}:{uid}", (), card.highlight, card=card)
    ]


def detect_cycles(ws: dict[str, Any], now: float) -> list[DetectedEvent]:
    """Extract current cycle state transitions keyed by minute-rounded boundary."""
    events: list[DetectedEvent] = []
    for cycle in calculate_cycles(ws, now):
        bucket = round(cycle.expires_at / 60)
        events.append(
            DetectedEvent(
                "cycles",
                f"cycles:{cycle.name}:{cycle.state}:{bucket}",
                (cycle.name, cycle.state, cycle.remaining(now)),
                f"{cycle.name} {cycle.state}",
                area=cycle.name,
                state=cycle.state,
            )
        )
    return events


def detect_arbitration(
    entries: list[list[Any]],
    nodes: dict[str, NodeInfo],
    tiers: dict[str, str],
    now: float,
) -> list[DetectedEvent]:
    """Extract currently active hourly Arbitration mission if present."""
    active = [
        (int(entry[0]), str(entry[1]))
        for entry in entries
        if int(entry[0]) <= now < int(entry[0]) + ARBITRATION_DURATION
    ]
    if not active:
        return []
    activation, node_key = min(active, key=lambda item: item[0])
    loc, info = node_display(node_key, nodes)
    mission_col = mission_faction_for_node(info)
    tier = normalized_tier(tiers, node_key)
    remaining = format_remaining(float(activation + ARBITRATION_DURATION), now)
    return [
        DetectedEvent(
            "arbitration",
            f"arbitration:{activation}:{node_key}",
            (loc, mission_col, tier, remaining),
            f"{loc} {mission_col} {tier}",
            tier=tier,
            mission=mission_col,
        )
    ]


def matches_rule(rule: SubscriptionRule, event: DetectedEvent) -> bool:
    """Return True when an event satisfies all configured rule filters."""
    filters = rule.filters
    keyword = str(filters.get("keyword") or "").strip().casefold()
    if keyword and keyword not in event.search_text.casefold():
        return False
    mode = str(filters.get("mode") or "")
    if mode and event.mode != mode:
        return False
    tiers = filters.get("tiers")
    if isinstance(tiers, list) and tiers and event.tier not in tiers:
        return False
    missions = filters.get("missions")
    if isinstance(missions, list) and missions and not any(m in event.mission for m in missions):
        return False
    areas = filters.get("areas")
    if isinstance(areas, list) and areas and "all" not in areas and event.area not in areas:
        return False
    states = filters.get("states")
    if isinstance(states, list) and states:
        allowed = {str(item).casefold() for item in states}
        if event.state.casefold() not in allowed:
            return False
    return True


def build_notification_card(
    rule: SubscriptionRule,
    events: list[DetectedEvent],
    meta: QueryMeta,
) -> Card:
    """Render one grouped Card for unseen matched events."""
    first = events[0]
    if first.card is not None:
        base = first.card
        prefix = f"[订阅推送] {base.highlight}" if base.highlight else "[订阅推送]"
        return replace(base, title=f"订阅推送 · {base.title}", highlight=prefix)
    kind_columns: dict[str, tuple[CardKind, tuple[str, ...]]] = {
        "alerts": ("alerts", ("节点", "任务 / 派系", "奖励", "剩余时间")),
        "fissures": ("fissures", ("纪元", "节点", "任务 / 派系", "剩余时间")),
        "invasions": ("invasions", ("节点", "对抗阵营", "进攻 / 防守奖励", "进度")),
        "cycles": ("cycles", ("区域", "状态", "剩余时间")),
        "arbitration": ("arbitration", ("节点", "任务 / 派系", "评级", "剩余时间")),
    }
    card_kind, columns = kind_columns.get(rule.event_type, ("summary", ("项目", "详情")))
    label = SUBSCRIPTION_LABELS.get(rule.event_type, rule.event_type)
    filter_desc = format_filter_summary(rule.event_type, rule.filters)
    return Card(
        f"订阅推送 · {label}",
        [evt.row for evt in events],
        subtitle(meta),
        columns=columns,
        kind=card_kind,
        highlight=f"命中规则：{filter_desc}",
    )


def _is_within_active_hours(active_hours: Any, now: float) -> bool:
    if not isinstance(active_hours, list) or len(active_hours) != 2:
        return True
    start, end = int(active_hours[0]), int(active_hours[1])
    hour = datetime.fromtimestamp(now, _UTC_PLUS_8).hour
    if start == end:
        return True
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


def match_notifications(
    rules: list[SubscriptionRule],
    events_by_type: dict[str, list[DetectedEvent]],
    delivered_lookup: dict[str, set[str]],
    meta: QueryMeta,
) -> list[PendingNotification]:
    """Pair subscription rules with unseen events into per-stream notification cards."""
    pending: list[PendingNotification] = []
    for rule in rules:
        if not _is_within_active_hours(rule.filters.get("active_hours"), meta.now):
            continue
        delivered = delivered_lookup.get(rule.stream_id, set())
        unseen = [
            evt
            for evt in events_by_type.get(rule.event_type, [])
            if evt.event_key not in delivered and matches_rule(rule, evt)
        ]
        if not unseen:
            continue
        card = build_notification_card(rule, unseen, meta)
        pending.append(
            PendingNotification(
                stream_id=rule.stream_id,
                event_type=rule.event_type,
                event_keys=[evt.event_key for evt in unseen],
                card=card,
                once=bool(rule.filters.get("once")),
            )
        )
    return pending


def build_subscription_list_card(rules: list[SubscriptionRule]) -> Card:
    """Build a visual/text Card listing active subscription rules for one stream."""
    rows: list[tuple[str, ...]] = [
        (
            SUBSCRIPTION_LABELS.get(rule.event_type, rule.event_type),
            format_filter_summary(rule.event_type, rule.filters),
            utc_time(rule.created_at),
        )
        for rule in rules
    ]
    return Card(
        "当前会话订阅",
        rows,
        "国际服 PC · 后台自动检测变更并推送到本会话",
        columns=("类型", "过滤条件", "订阅时间"),
        kind="subscriptions",
        empty_message="当前会话尚未订阅任何事件，可发送 /订阅 警报 开始",
    )


def build_subscription_help_card() -> Card:
    """Build usage help Card for `/订阅`."""
    return Card(
        "订阅指令帮助",
        [
            ("警报 / 入侵", "/订阅 警报 [关键词]", "按奖励或节点过滤（如 反应堆 / Forma）"),
            (
                "裂缝 / 风暴",
                "/订阅 裂缝 [钢铁|九重天] [纪元] [任务]",
                "支持组合过滤（如 钢铁 后纪 捕获）",
            ),
            ("突击 / 猎杀", "/订阅 突击 | /订阅 猎杀", "每日突击或每周执刑官轮换时提醒"),
            ("虚空商人", "/订阅 奸商", "Baro 即将抵达或抵达中继站时提醒"),
            (
                "平原周期",
                "/订阅 平原 [区域] [状态]",
                "默认监控夜灵平原，支持 地球/双衍/扎里曼/全部",
            ),
            ("仲裁排期", "/订阅 仲裁 [S/A/B]", "整点轮换为指定评级或节点时提醒"),
            ("推送控制", "附加 时段 9-22 或 单次", "仅在 UTC+8 指定时段推送，或触发一次即退订"),
            ("铸造提醒", "/铸造提醒 物品 [时长] | /铸造列表", "定时到期提醒（如 Forma 23h）"),
            ("管理订阅", "/订阅列表 | /退订 <类型|全部>", "查看本会话规则或退订"),
        ],
        "国际服 PC · 同一会话对同类型重复订阅会覆盖更新条件",
        columns=("类别", "示例指令", "说明"),
        kind="subscription_help",
    )


def _duration_seconds(token: str) -> float | None:
    matches = list(_DURATION_PART_RE.finditer(token.strip()))
    if not matches:
        return None
    consumed = "".join(m.group(0) for m in matches)
    if consumed.replace(" ", "") != token.strip().replace(" ", ""):
        return None
    unit_mult = {
        "天": 86_400.0,
        "d": 86_400.0,
        "小时": 3_600.0,
        "时": 3_600.0,
        "h": 3_600.0,
        "分钟": 60.0,
        "分": 60.0,
        "m": 60.0,
    }
    total = sum(float(m.group(1)) * unit_mult[m.group(2).casefold()] for m in matches)
    return total if total > 0 else None


def parse_foundry_spec(raw_args: str, now: float) -> tuple[str, float, float]:
    """Parse `/铸造提醒 <物品名> [时长]` into `(item_name, duration_sec, due_at)`."""
    tokens = raw_args.split()
    if not tokens:
        raise QueryError(
            "用法：/铸造提醒 <物品名称> [时长]，例如：/铸造提醒 Forma 23h 或 毒妈p 72h。"
        )
    duration: float | None = None
    if len(tokens) >= 2 and (parsed := _duration_seconds(tokens[-1])) is not None:
        duration = parsed
        item_name = " ".join(tokens[:-1]).strip()
    elif len(tokens) >= 2 and (parsed := _duration_seconds(tokens[0])) is not None:
        duration = parsed
        item_name = " ".join(tokens[1:]).strip()
    else:
        duration = 12 * 3_600.0
        item_name = " ".join(tokens).strip()
    if not item_name:
        raise QueryError("请填写要提醒的铸造物品名称。")
    if duration < 60 or duration > 30 * 86_400:
        raise QueryError("铸造提醒时长须介于 1 分钟至 30 天之间。")
    return item_name, duration, now + duration


class FoundryStore:
    """Persist personal Foundry completion reminders in SQLite."""

    def __init__(self, db_path: Path) -> None:
        self.path = db_path

    def initialize(self) -> None:
        """Ensure SQLite tables exist."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=5.0)) as conn:
            ensure_schema(conn)

    def add(
        self, stream_id: str, item_name: str, due_at: float, *, user_id: str = ""
    ) -> FoundryReminder:
        """Insert a new Foundry reminder and return the persisted record."""
        with closing(sqlite3.connect(self.path, timeout=5.0)) as conn:
            cursor = conn.execute(
                "INSERT INTO foundry_reminders (stream_id, user_id, item_name, due_at) "
                "VALUES (?, ?, ?, ?)",
                (stream_id, user_id, item_name, due_at),
            )
            conn.commit()
            rid = int(cursor.lastrowid or 0)
        return FoundryReminder(rid, stream_id, user_id, item_name, due_at)

    def list_for_stream(self, stream_id: str) -> list[FoundryReminder]:
        """List active Foundry reminders for a stream ordered by due time."""
        with closing(sqlite3.connect(self.path, timeout=5.0)) as conn:
            rows = conn.execute(
                "SELECT id, stream_id, user_id, item_name, due_at "
                "FROM foundry_reminders WHERE stream_id = ? ORDER BY due_at ASC, id ASC",
                (stream_id,),
            ).fetchall()
        return [
            FoundryReminder(int(r[0]), str(r[1]), str(r[2]), str(r[3]), float(r[4])) for r in rows
        ]

    def pop_due(self, now: float) -> list[FoundryReminder]:
        """Fetch and delete all reminders whose `due_at <= now`."""
        with closing(sqlite3.connect(self.path, timeout=5.0)) as conn:
            rows = conn.execute(
                "SELECT id, stream_id, user_id, item_name, due_at "
                "FROM foundry_reminders WHERE due_at <= ? ORDER BY due_at ASC, id ASC",
                (now,),
            ).fetchall()
            if not rows:
                return []
            ids = [(int(r[0]),) for r in rows]
            conn.executemany("DELETE FROM foundry_reminders WHERE id = ?", ids)
            conn.commit()
        return [
            FoundryReminder(int(r[0]), str(r[1]), str(r[2]), str(r[3]), float(r[4])) for r in rows
        ]

    def remove(self, stream_id: str, reminder_id: int) -> bool:
        """Delete one reminder owned by `stream_id`."""
        with closing(sqlite3.connect(self.path, timeout=5.0)) as conn:
            cursor = conn.execute(
                "DELETE FROM foundry_reminders WHERE stream_id = ? AND id = ?",
                (stream_id, reminder_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def remove_all(self, stream_id: str) -> int:
        """Delete all reminders owned by `stream_id`."""
        with closing(sqlite3.connect(self.path, timeout=5.0)) as conn:
            cursor = conn.execute(
                "DELETE FROM foundry_reminders WHERE stream_id = ?",
                (stream_id,),
            )
            conn.commit()
            return cursor.rowcount


def build_foundry_list_card(reminders: list[FoundryReminder], now: float) -> Card:
    """Build a visual/text Card listing pending Foundry completion reminders."""
    rows: list[tuple[str, ...]] = []
    for rem in reminders:
        due_text = datetime.fromtimestamp(rem.due_at, _UTC_PLUS_8).strftime("%m-%d %H:%M")
        rem_text = format_remaining(rem.due_at, now)
        rows.append((f"#{rem.reminder_id}", rem.item_name, f"{rem_text} ({due_text})"))
    return Card(
        "当前铸造提醒队列",
        rows,
        "国际服 PC · 到期后将自动在本会话推送提醒 (UTC+8)",
        columns=("编号", "物品名称", "剩余 / 预计完成"),
        kind="subscriptions",
        empty_message="当前会话没有待提醒的铸造任务，可发送 /铸造提醒 Forma 23h 添加",
    )
