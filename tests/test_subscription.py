"""Unit tests for subscription parsing, SQLite store, detectors, and matching."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest

from milo_core.cache import ResponseCache
from milo_core.dictionary import NodeInfo, TranslationIndex
from milo_core.errors import QueryError
from milo_core.subscription import (
    SubscriptionRule,
    SubscriptionStore,
    build_subscription_help_card,
    build_subscription_list_card,
    detect_alerts,
    detect_arbitration,
    detect_archon,
    detect_cycles,
    detect_fissures,
    detect_invasions,
    detect_sortie,
    detect_void_trader,
    format_filter_summary,
    match_notifications,
    parse_subscribe_spec,
    parse_unsubscribe_target,
)
from milo_core.worldstate import QueryMeta


def _ms(ts: float) -> dict[str, Any]:
    return {"$date": {"$numberLong": str(int(ts * 1000))}}


def test_parse_subscribe_spec_supports_filters_and_shortcuts() -> None:
    assert parse_subscribe_spec("警报 土豆") == ("alerts", {"keyword": "土豆"})
    assert parse_subscribe_spec("裂缝 钢铁 后纪 捕获 虚空") == (
        "fissures",
        {"mode": "steel", "tiers": ["后纪"], "missions": ["捕获"], "keyword": "虚空"},
    )
    assert parse_subscribe_spec("九重天裂缝 古纪") == (
        "fissures",
        {"mode": "storm", "tiers": ["古纪"]},
    )
    assert parse_subscribe_spec("平原") == ("cycles", {"areas": ["夜灵平原"]})
    assert parse_subscribe_spec("平原 喜悦") == (
        "cycles",
        {"areas": ["双衍王境"], "states": ["喜悦"]},
    )
    assert parse_subscribe_spec("平原 全部") == ("cycles", {"areas": ["all"]})
    assert parse_subscribe_spec("仲裁 s a") == ("arbitration", {"tiers": ["S", "A"]})
    assert parse_subscribe_spec("奸商") == ("void_trader", {})
    assert format_filter_summary("fissures", {"mode": "steel", "tiers": ["后纪"]}) == "钢铁 · 后纪"


@pytest.mark.parametrize("bad_spec", ["", "不存在", "奸商 多余参数", "平原 奇怪状态"])
def test_parse_subscribe_spec_rejects_invalid_inputs(bad_spec: str) -> None:
    with pytest.raises(QueryError):
        parse_subscribe_spec(bad_spec)


def test_parse_unsubscribe_target() -> None:
    assert parse_unsubscribe_target("全部") == "all"
    assert parse_unsubscribe_target("all") == "all"
    assert parse_unsubscribe_target("钢铁裂缝") == "fissures"
    with pytest.raises(QueryError):
        parse_unsubscribe_target("")
    with pytest.raises(QueryError):
        parse_unsubscribe_target("未知类型")


def test_subscription_store_crud_deliveries_and_pruning(tmp_path: Path) -> None:
    cache = ResponseCache(tmp_path)
    cache.initialize()
    store = SubscriptionStore(cache.path)
    now = 1_700_000_000.0

    store.upsert("chat-1", "alerts", {"keyword": "Forma"}, now=now)
    store.upsert("chat-1", "alerts", {"keyword": "催化剂"}, now=now + 10)
    store.upsert("chat-2", "sortie", {}, now=now + 20)

    rules = store.list_for_stream("chat-1")
    assert len(rules) == 1
    assert rules[0].filters == {"keyword": "催化剂"}
    assert len(store.list_all()) == 2

    store.record_deliveries("chat-1", ["alerts:1", "alerts:2"], now=now)
    assert store.has_delivered("chat-1", "alerts:1")
    assert not store.has_delivered("chat-2", "alerts:1")
    assert store.delivered_keys_for_stream("chat-1", ["alerts:1", "alerts:3"]) == {"alerts:1"}

    pruned = store.prune_deliveries(now + 1)
    assert pruned == 2
    assert not store.has_delivered("chat-1", "alerts:1")

    assert store.remove("chat-1", "alerts") is True
    assert store.remove("chat-1", "alerts") is False
    assert store.remove_all("chat-2") == 1


def test_detectors_and_rule_matching() -> None:
    now = time.time()
    future = now + 3600
    nodes = {"SolNode1": NodeInfo("E-Prime", "Earth", 1, 0)}
    trans = TranslationIndex({"/Lotus/Forma": "Forma 蓝图"}, {})
    ws: dict[str, Any] = {
        "Alerts": [
            {
                "_id": {"$oid": "a1"},
                "Expiry": _ms(future),
                "MissionInfo": {
                    "location": "SolNode1",
                    "missionType": "MT_CAPTURE",
                    "faction": "FC_GRINEER",
                    "missionReward": {
                        "countedItems": [{"ItemType": "/Lotus/Forma", "ItemCount": 1}]
                    },
                },
            },
            {
                "_id": {"$oid": "expired"},
                "Expiry": _ms(now - 10),
                "MissionInfo": {"location": "SolNode1"},
            },
        ],
        "ActiveMissions": [
            {
                "_id": {"$oid": "f1"},
                "Node": "SolNode1",
                "Modifier": "VoidT4",
                "MissionType": "MT_CAPTURE",
                "Faction": "FC_GRINEER",
                "Hard": True,
                "Expiry": _ms(future),
            }
        ],
        "VoidStorms": [
            {
                "_id": {"$oid": "s1"},
                "Node": "SolNode1",
                "ActiveMissionTier": "VoidT1",
                "Faction": "FC_CORPUS",
                "Expiry": _ms(future),
            }
        ],
        "Invasions": [
            {
                "_id": {"$oid": "i1"},
                "Node": "SolNode1",
                "Faction": "FC_GRINEER",
                "DefenderFaction": "FC_CORPUS",
                "Goal": 100,
                "Count": 25,
                "Completed": False,
                "AttackerReward": {"countedItems": [{"ItemType": "/Lotus/Forma", "ItemCount": 1}]},
                "DefenderReward": [],
            }
        ],
        "Sorties": [
            {
                "_id": {"$oid": "so1"},
                "Boss": "SORTIE_BOSS_VOR",
                "Expiry": _ms(future),
                "Variants": [
                    {
                        "missionType": "MT_RESCUE",
                        "node": "SolNode1",
                        "modifierType": "SORTIE_MODIFIER_ARMOR",
                    }
                ],
            }
        ],
        "LiteSorties": [
            {
                "_id": {"$oid": "ar1"},
                "Boss": "SORTIE_BOSS_NIRA",
                "Expiry": _ms(future),
                "Missions": [{"missionType": "MT_SABOTAGE", "node": "SolNode1"}],
            }
        ],
        "VoidTraders": [
            {
                "_id": {"$oid": "vt1"},
                "Node": "SolNode1",
                "Activation": _ms(now - 60),
                "Expiry": _ms(future),
                "Manifest": [
                    {"ItemType": "/Lotus/Forma", "PrimePrice": 100, "RegularPrice": 50000}
                ],
            }
        ],
        "SyndicateMissions": [{"Tag": "CetusSyndicate", "Expiry": _ms(future)}],
    }
    meta = QueryMeta(now, now, [])
    events_by_type = {
        "alerts": detect_alerts(ws, nodes, trans, now),
        "fissures": detect_fissures(ws, nodes, now),
        "invasions": detect_invasions(ws, nodes, trans),
        "sortie": detect_sortie(ws, nodes, meta),
        "archon": detect_archon(ws, nodes, meta),
        "void_trader": detect_void_trader(ws, nodes, trans, meta),
        "cycles": detect_cycles(ws, now),
        "arbitration": detect_arbitration(
            [[int(now) - 60, "SolNode1"]], nodes, {"SolNode1": "S"}, now
        ),
    }

    assert [e.event_key for e in events_by_type["alerts"]] == ["alerts:a1"]
    assert len(events_by_type["fissures"]) == 2
    assert events_by_type["void_trader"][0].event_key == "void_trader:arrived:vt1"
    assert events_by_type["arbitration"][0].tier == "S"

    rules = [
        SubscriptionRule("c1", "fissures", {"mode": "steel", "tiers": ["后纪"]}, now),
        SubscriptionRule("c1", "arbitration", {"tiers": ["S"]}, now),
        SubscriptionRule("c1", "sortie", {}, now),
    ]
    notifications = match_notifications(rules, events_by_type, {}, meta)
    assert len(notifications) == 3
    assert notifications[0].event_keys == ["fissures:f1"]
    assert "钢铁" in notifications[0].card.highlight
    assert notifications[2].card.title.startswith("订阅推送 ·")

    cycle_events_a = detect_cycles(ws, now)
    cycle_events_b = detect_cycles(ws, now + 2)
    assert [e.event_key for e in cycle_events_a] == [e.event_key for e in cycle_events_b]

    assert (
        "订阅列表" in build_subscription_list_card(rules).title
        or "订阅" in build_subscription_list_card(rules).title
    )
    assert build_subscription_help_card().kind == "subscription_help"
