"""Unit tests for Phase D: ducats, auctions, whispers, and pure-Python Riven analysis."""

from __future__ import annotations

from pathlib import Path

import pytest

from milo_core.auctions import (
    build_lich_sister_card,
    build_riven_auctions_card,
    extract_candidate_choice,
    filter_online_auctions,
    resolve_stat_filters,
    split_riven_args,
)
from milo_core.dictionary import RivenStatInfo, RivenTrendEntry, WeaponMeta
from milo_core.ducats import build_ducats_card
from milo_core.errors import QueryError
from milo_core.market import Item, Order
from milo_core.riven_analyse import (
    build_riven_analyse_card,
    build_riven_analyse_help_card,
    compute_diff,
    compute_low_high,
    dot_from_omega,
)
from milo_core.whisper import (
    WhisperEntry,
    WhisperStore,
    lich_whisper,
    order_whisper,
    pick_lang,
    riven_whisper,
)
from milo_core.worldstate import QueryMeta


def test_ducats_ranks_gold_and_silver_separately_with_fallback_names() -> None:
    day = [
        {
            "item": f"g{i}",
            "ducats": 100,
            "ducats_per_platinum_wa": float(i),
            "wa_price": 10,
            "volume": i,
        }
        for i in range(1, 13)
    ] + [
        {"item": "s1", "ducats": 45, "ducats_per_platinum_wa": 7.5, "wa_price": 6.0, "volume": 12},
        {"item": "bad", "ducats": 15, "ducats_per_platinum_wa": 15.0, "wa_price": 1.0, "volume": 5},
    ]
    hour = [
        {
            "item": "g12",
            "ducats": 100,
            "ducats_per_platinum_wa": 14.0,
            "wa_price": 7.1,
            "volume": 3,
        },
        {"item": "s1", "ducats": 45, "ducats_per_platinum_wa": 8.2, "wa_price": 5.5, "volume": 4},
    ]
    names = {"g12": "Volt Prime 头部", "s1": "Loki Prime 系统"}
    meta = QueryMeta(1_700_000_000.0, 1_700_000_000.0, [])

    gold_card = build_ducats_card(
        "gold", {"payload": {"previous_day": day, "previous_hour": hour}}, names, meta
    )
    assert gold_card.kind == "ducats"
    day_rows = [row for row in gold_card.rows if row[0] == "当天"]
    hour_rows = [row for row in gold_card.rows if row[0] == "每小时"]
    assert len(day_rows) == 10
    assert day_rows[0][1] == "Volt Prime 头部"
    assert day_rows[1][1] == "g11"  # falls back cleanly when item_id missing from catalogue
    assert hour_rows[0][3] == "14.00"

    silver_card = build_ducats_card(
        "silver", {"payload": {"previous_day": day, "previous_hour": hour}}, names, meta
    )
    assert [row[1] for row in silver_card.rows] == ["Loki Prime 系统", "Loki Prime 系统"]

    with pytest.raises(QueryError):
        build_ducats_card("gold", {"error": "bad"}, names, meta)


def test_split_riven_args_preserves_mk1_and_extracts_filters() -> None:
    assert split_riven_args("托里德 爆率,爆伤 无") == ("托里德", "爆率,爆伤", "无")
    assert split_riven_args("Braton Prime") == ("Braton Prime", "", "")
    assert split_riven_args("MK1-Braton") == ("MK1-Braton", "", "")
    assert split_riven_args("MK1-Braton-爆率,爆伤-无") == ("MK1-Braton", "爆率,爆伤", "无")
    assert extract_candidate_choice("2 爆率,爆伤 有") == (2, "爆率,爆伤 有")
    assert extract_candidate_choice("abc") is None


def test_resolve_stat_filters_and_auction_filtering() -> None:
    stats = [
        RivenStatInfo("critical_chance", "暴击几率", "percent", False, False),
        RivenStatInfo("critical_damage", "暴击伤害", "percent", False, False),
        RivenStatInfo("recoil", "武器后坐力", "percent", True, False),
    ]
    aliases = {"爆率": "critical_chance", "爆伤": "critical_damage"}
    pos, neg = resolve_stat_filters("爆率，暴击伤害", "无", stats, aliases)
    assert pos == "critical_chance,critical_damage"
    assert neg == "none"

    with pytest.raises(QueryError):
        resolve_stat_filters("未知词条", "", stats, aliases)
    with pytest.raises(QueryError):
        resolve_stat_filters("", "maybe", stats, aliases)

    raw_auctions = {
        "payload": {
            "auctions": [
                {
                    "closed": True,
                    "visible": True,
                    "platform": "pc",
                    "crossplay": True,
                    "buyout_price": 100,
                    "owner": {"ingame_name": "ClosedOne", "status": "ingame"},
                },
                {
                    "closed": False,
                    "visible": True,
                    "platform": "xbox",
                    "crossplay": False,
                    "buyout_price": 120,
                    "owner": {"ingame_name": "NoCrossplay", "status": "online"},
                },
                {
                    "closed": False,
                    "visible": True,
                    "platform": "ps4",
                    "crossplay": True,
                    "buyout_price": 300,
                    "owner": {"ingame_name": "OfflineSeller", "status": "offline"},
                },
                {
                    "closed": False,
                    "visible": True,
                    "platform": "xbox",
                    "crossplay": True,
                    "buyout_price": 250,
                    "owner": {"ingame_name": "CrossSeller", "status": "online", "locale": "en"},
                    "item": {
                        "name": "critacan",
                        "mastery_level": 14,
                        "mod_rank": 8,
                        "re_rolls": 3,
                        "polarity": "madurai",
                        "attributes": [
                            {"url_name": "critical_chance", "value": 182.4, "positive": True}
                        ],
                    },
                },
                {
                    "closed": False,
                    "visible": True,
                    "platform": "pc",
                    "crossplay": True,
                    "buyout_price": 190,
                    "owner": {"ingame_name": "PcCheaper", "status": "ingame", "locale": "zh-hans"},
                    "item": {"name": "acri", "attributes": []},
                },
            ]
        }
    }
    filtered = filter_online_auctions(raw_auctions)
    assert [a["owner"]["ingame_name"] for a in filtered] == ["PcCheaper", "CrossSeller"]

    weapon = Item("1", "torid", "托里德", "Torid")
    meta = QueryMeta(1_700_000_000.0, 1_700_000_000.0, [])
    card = build_riven_auctions_card(
        weapon, raw_auctions, {s.url_name: s for s in stats}, "正面：爆率", meta
    )
    assert len(card.rows) == 2
    assert len(card.whispers) == 2
    assert "你好! 我想购买你的「托里德」紫卡 Acri" in card.whispers[0].text
    assert 'Hi! I want to buy your Torid riven "Critacan"' in card.whispers[1].text

    lich_raw = {
        "payload": {
            "auctions": [
                {
                    "closed": False,
                    "visible": True,
                    "platform": "pc",
                    "crossplay": True,
                    "starting_price": 200,
                    "owner": {"ingame_name": "SisterEN", "status": "online", "locale": "en"},
                    "item": {"element": "magnetic", "damage": 59, "having_ephemera": False},
                }
            ]
        }
    }
    lich_card = build_lich_sister_card(
        "sister", Item("2", "tenet_envoy", "信条 典客", "Tenet Envoy"), lich_raw, meta
    )
    assert "磁力 59%" in lich_card.rows[0][1]
    assert "59% Magnetic" in lich_card.whispers[0].text


def test_whisper_templates_and_store_isolation(monkeypatch: pytest.MonkeyPatch) -> None:
    assert pick_lang("zh-Hant") == "zh"
    assert pick_lang("ko") == "en"

    ord_zh = order_whisper(
        Order("CnSeller", 120, 2, "ingame", rank=10, locale="zh-hans"),
        "压迫点 Prime",
        "Primed Pressure Point",
        buyer=False,
    )
    assert 'x2 "压迫点 Prime (等级 10)"' in ord_zh.text
    ord_en = order_whisper(
        Order("EnBuyer", 80, 1, "online", rank=None, locale="en"),
        "伏特 Prime 一套",
        "Volt Prime Set",
        buyer=True,
    )
    assert 'want to sell: "Volt Prime Set" for 80 platinum' in ord_en.text

    riv = riven_whisper({"ingame_name": "Alice", "locale": "en"}, "visicron", "托里德", "Torid")
    assert riv is not None and 'Torid riven "Visicron"' in riv.text
    lich = lich_whisper(
        {"ingame_name": "Bob", "locale": "zh-cn", "status": "offline"},
        {"element": "toxin", "damage": 60, "having_ephemera": True},
        "赤毒 布拉玛",
        "Kuva Bramma",
    )
    assert lich is not None and "（60% 毒素）（带幻纹）" in lich.text

    clock = [1000.0]
    monkeypatch.setattr("milo_core.whisper.time.monotonic", lambda: clock[0])
    store = WhisperStore(ttl=120.0)
    store.remember("s1", "u1", "cd", [WhisperEntry("Bob", "zh", "zh", lich.text, "offline")])
    assert "（对方当前离线，可能收不到）" in store.reply_for("s1", "u1", "1")
    with pytest.raises(QueryError):
        store.reply_for("s1", "u1", "2")
    with pytest.raises(QueryError):
        store.reply_for("s1", "u2", "1")
    assert "用法：/w <序号>" in store.reply_for("s1", "u1", "")
    clock[0] += 121.0
    with pytest.raises(QueryError):
        store.reply_for("s1", "u1", "1")


def test_riven_analyse_math_and_zero_ocr_dependency() -> None:
    assert dot_from_omega(0.55) == "●○○○○"
    assert dot_from_omega(1.30) == "●●●●●"

    low, high = compute_low_high(150.0, 1.3, 3, has_curse=True, is_curse=False)
    assert (low, high) == pytest.approx((217.1813, 265.4438), abs=0.01)
    assert compute_diff("暴击几率", 265.4438, (low, high), is_mult=False) == "+10.0%"
    assert compute_diff("后坐力", -80.0, (-90.0, -70.0), is_mult=False) == "0.0%"
    assert compute_diff("对Infested伤害", 1.50, (35.0, 65.0), is_mult=True) == "0.0%"

    weapons = [
        WeaponMeta("/Lotus/Torid", "托里德", "Torid", "LongGuns", 1.30, "Torid"),
        WeaponMeta("/Lotus/Cronus", "克洛诺斯", "Cronus", "Melee", 1.45, "Cronus"),
    ]
    trends = {
        "暴击几率": RivenTrendEntry("暴击几率", 150.0, 90.0, 150.0, 180.0, 100.0),
        "对Grineer伤害": RivenTrendEntry("对Grineer伤害", 45.0, 45.0, 45.0, 45.0, 45.0),
        "后坐力": RivenTrendEntry("后坐力", -90.0, -90.0, -90.0, 0.0, -90.0),
    }
    card = build_riven_analyse_card(
        "托里德 +180% 暴击几率 x1.52 对Grineer伤害 +85% 后坐力",
        weapons,
        trends,
        {},
    )
    assert card.kind == "riven_analyse"
    assert "含负面" in card.subtitle
    assert "x1.52" in card.rows[1][1]
    assert card.rows[2][2].startswith("52.1%")

    melee_card = build_riven_analyse_card(
        "克洛诺斯 暴击几率+250%, 暴击几率+200%", weapons, trends, {}
    )
    assert "近战" in melee_card.highlight
    assert len(melee_card.rows) == 2

    help_card = build_riven_analyse_help_card()
    assert help_card.kind == "riven_analyse_help"
    assert "暂未实现 OCR" in help_card.text()
    with pytest.raises(QueryError):
        build_riven_analyse_card("托里德 -40% 暴击几率 +180% 暴击几率", weapons, trends, {})

    milo_core_dir = Path(__file__).resolve().parents[1] / "milo_core"
    for py_file in milo_core_dir.glob("*.py"):
        source = py_file.read_text(encoding="utf-8").casefold()
        assert "paddleocr" not in source and "paddlepaddle" not in source
