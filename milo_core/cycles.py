"""Warframe PC cycle calculations with explicit input and UTC timestamps."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from .dictionary import split_camel_case
from .errors import QueryError

VALLIS_EPOCH = 1_541_837_628
ZARIMAN_CORPUS_EPOCH_MS = 1_655_182_800_000
ZARIMAN_FULL_CYCLE_MS = 18_000_000
ZARIMAN_HALF_CYCLE_MS = 9_000_000
DUVIRI_CYCLE_SECONDS = 36_000
DUVIRI_STATE_SECONDS = 7_200
DUVIRI_STATES: tuple[str, ...] = ("悲伤", "恐惧", "喜悦", "愤怒", "嫉妒")


@dataclass(frozen=True)
class Cycle:
    """One cycle phase with an absolute end time."""

    name: str
    state: str
    expires_at: float

    def remaining(self, now: float) -> str:
        """Format remaining time without retaining stale relative strings."""
        seconds = max(0, int(self.expires_at - now))
        hours, seconds = divmod(seconds, 3600)
        minutes, seconds = divmod(seconds, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _timestamp(value: Any) -> float:
    """Decode the official API's MongoDB extended-JSON date."""
    try:
        return int(value["$date"]["$numberLong"]) / 1000
    except (TypeError, KeyError, ValueError) as exc:
        raise QueryError("世界状态的时间字段格式已变化，请稍后重试并检查日志。") from exc


def _syndicate_expiry(missions: list[Any], tag: str, now: float, max_ahead: float) -> float | None:
    expiries = [
        _timestamp(mission.get("Expiry"))
        for mission in missions
        if isinstance(mission, dict) and mission.get("Tag") == tag
    ]
    valid = [expiry for expiry in expiries if now < expiry <= now + max_ahead]
    return min(valid) if valid else None


def duviri_emotion_cycle(now: float) -> Cycle:
    """Return the current Duviri mood cycle phase for PC."""
    cycle_delta = (int(now) - 52) % DUVIRI_CYCLE_SECONDS
    state_index = cycle_delta // DUVIRI_STATE_SECONDS
    until_next = DUVIRI_STATE_SECONDS - (cycle_delta % DUVIRI_STATE_SECONDS)
    return Cycle("双衍王境", DUVIRI_STATES[state_index], float(int(now) + until_next))


def zariman_cycle_from_expiry(expiry: float) -> Cycle:
    """Calculate Zariman Corpus/Grineer occupation from ZarimanSyndicate expiry."""
    bounties_clone_ms = int(expiry * 1000) - 5_000
    elapsed_ms = (bounties_clone_ms - ZARIMAN_CORPUS_EPOCH_MS) % ZARIMAN_FULL_CYCLE_MS
    left_ms = ZARIMAN_FULL_CYCLE_MS - elapsed_ms
    is_corpus = left_ms > ZARIMAN_HALF_CYCLE_MS
    state = "Corpus" if is_corpus else "Grineer"
    expires_at = float(round(bounties_clone_ms / 60_000) * 60)
    return Cycle("扎里曼", state, expires_at)


def calculate_cycles(worldstate: dict[str, Any], now: float) -> list[Cycle]:
    """Return Earth, Cetus, Orb Vallis, Cambion, Zariman and Duviri phases for PC.

    Cetus and Cambion depend on the live bounty expiry. Expired or missing Cetus
    data causes a clear failure instead of inventing a current phase from old data.
    """
    missions = worldstate.get("SyndicateMissions")
    if not isinstance(missions, list):
        raise QueryError("世界状态缺少赏金数据，暂时不能查询平原周期。")
    bounty_end = _syndicate_expiry(missions, "CetusSyndicate", now, 9_100)
    if bounty_end is None:
        raise QueryError("夜灵平原赏金数据缺失或已过期，请稍后重试。")
    is_day = bounty_end - now > 3000
    cetus_end = bounty_end - 3000 if is_day else bounty_end
    earth_offset = now % 28_800
    earth_end = now + 14_400 - earth_offset % 14_400
    vallis_offset = (now - VALLIS_EPOCH) % 1600
    is_warm = vallis_offset < 400
    vallis_end = now + (400 if is_warm else 1600) - vallis_offset
    cycles = [
        Cycle("地球", "白昼" if earth_offset < 14_400 else "夜晚", earth_end),
        Cycle("夜灵平原", "白昼" if is_day else "夜晚", cetus_end),
        Cycle("奥布山谷", "温暖" if is_warm else "寒冷", vallis_end),
        Cycle("魔胎之境", "FASS" if is_day else "VOME", cetus_end),
    ]
    zariman_end = _syndicate_expiry(missions, "ZarimanSyndicate", now, 18_100)
    if zariman_end is not None:
        cycles.append(zariman_cycle_from_expiry(zariman_end))
    cycles.append(duviri_emotion_cycle(now))
    return cycles


def parse_duviri_choices(
    worldstate: dict[str, Any], weapons_en: dict[str, str]
) -> list[tuple[str, list[str]]]:
    """Extract Normal and Steel Path Duviri circuit choices from WorldState."""
    raw_choices: Any = None
    schedule = worldstate.get("EndlessXpSchedule")
    if isinstance(schedule, list) and schedule and isinstance(schedule[0], dict):
        raw_choices = schedule[0].get("CategoryChoices")
    if not isinstance(raw_choices, list):
        raw_choices = worldstate.get("EndlessXpChoices")
    if not isinstance(raw_choices, list):
        return []
    result: list[tuple[str, list[str]]] = []
    for entry in raw_choices:
        if not isinstance(entry, dict):
            continue
        category = str(entry.get("Category") or "")
        items = entry.get("Choices")
        if not isinstance(items, list):
            continue
        if category == "EXC_HARD":
            translated = []
            for raw_name in items:
                spaced = split_camel_case(str(raw_name))
                translated.append(weapons_en.get(spaced.casefold(), spaced))
            result.append(("钢铁之路", translated))
        elif category == "EXC_NORMAL":
            result.append(("普通", [str(item) for item in items]))
    return result


def utc_time(timestamp: float) -> str:
    """Format a source timestamp independently of the machine's timezone."""
    return datetime.fromtimestamp(timestamp, UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
