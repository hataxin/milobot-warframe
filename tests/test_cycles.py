from typing import Any

import pytest

from milo_core.cycles import (
    VALLIS_EPOCH,
    calculate_cycles,
    duviri_emotion_cycle,
    utc_time,
    zariman_cycle_from_expiry,
)
from milo_core.errors import QueryError


def snapshot(expiry: float, *, zariman_expiry: float | None = None) -> dict[str, Any]:
    missions = [
        {"Tag": "CetusSyndicate", "Expiry": {"$date": {"$numberLong": str(int(expiry * 1000))}}}
    ]
    if zariman_expiry is not None:
        missions.append(
            {
                "Tag": "ZarimanSyndicate",
                "Expiry": {"$date": {"$numberLong": str(int(zariman_expiry * 1000))}},
            }
        )
    return {"SyndicateMissions": missions}


def test_cetus_day_and_night_boundary() -> None:
    now = 1_800_000_000.0
    day = calculate_cycles(snapshot(now + 4000), now)
    assert day[1].state == "白昼"
    assert day[1].expires_at == now + 1000
    assert day[3].state == "FASS"
    night = calculate_cycles(snapshot(now + 3000), now)
    assert night[1].state == "夜晚"
    assert night[1].expires_at == now + 3000
    assert night[3].state == "VOME"


def test_vallis_phase_boundary_has_positive_remaining_time() -> None:
    now = float(VALLIS_EPOCH + 400)
    cycle = calculate_cycles(snapshot(now + 5000), now)[2]
    assert cycle.state == "寒冷"
    assert cycle.expires_at - now == 1200
    now = float(VALLIS_EPOCH + 1600)
    cycle = calculate_cycles(snapshot(now + 5000), now)[2]
    assert cycle.state == "温暖"
    assert cycle.expires_at - now == 400


def test_zariman_and_duviri_cycles_match_live_polarities() -> None:
    # Verified against live worldState + warframestat.us: 1794800283.659 -> Grineer.
    zariman = zariman_cycle_from_expiry(1794800283.659)
    assert zariman.state == "Grineer"
    assert zariman.expires_at == 1794800280.0

    # 9000s earlier should be Corpus.
    corpus = zariman_cycle_from_expiry(1794800283.659 - 9000)
    assert corpus.state == "Corpus"

    all_cycles = calculate_cycles(
        snapshot(1_794_800_283.659, zariman_expiry=1_794_800_283.659), 1_794_796_466.0
    )
    assert [cycle.name for cycle in all_cycles] == [
        "地球",
        "夜灵平原",
        "奥布山谷",
        "魔胎之境",
        "扎里曼",
        "双衍王境",
    ]
    assert all_cycles[4].state == "Grineer"

    emo = duviri_emotion_cycle(52.0)
    assert emo.state == "悲伤"
    assert emo.expires_at == 52.0 + 7200.0
    assert duviri_emotion_cycle(52.0 + 7200.0).state == "恐惧"


@pytest.mark.parametrize("body", [{}, {"SyndicateMissions": []}, snapshot(1)])
def test_missing_or_expired_live_data_is_not_reported_as_current(body: dict[str, Any]) -> None:
    with pytest.raises(QueryError):
        calculate_cycles(body, 1_800_000_000)


def test_timestamp_display_is_explicit_utc() -> None:
    assert utc_time(0) == "1970-01-01 00:00:00 UTC"
