"""End-to-end and unit tests for v0.6.0 features (flags, tools, worldstate, foundry)."""

from __future__ import annotations

import sqlite3
import time
from contextlib import closing
from pathlib import Path
from typing import Any

import httpx

from milo_core.arbitration import build_arbitration_list_card
from milo_core.auctions import (
    RivenDisplayOptions,
    build_riven_auctions_card,
    parse_riven_query,
    resolve_stat_filters,
)
from milo_core.cache import ResponseCache
from milo_core.command_flags import page_caption, paginate, parse_command_flags
from milo_core.dictionary import (
    NodeInfo,
    RelicEntry,
    RelicReward,
    RivenStatInfo,
    RivenTrendEntry,
    TranslationIndex,
    WeaponMeta,
)
from milo_core.ducats import build_ducats_card
from milo_core.market import Item, parse_wm_stats
from milo_core.subscription import (
    DetectedEvent,
    FoundryStore,
    SubscriptionRule,
    build_foundry_list_card,
    format_filter_summary,
    match_notifications,
    parse_foundry_spec,
    parse_subscribe_spec,
)
from milo_core.tools_calc import (
    RelicValuationContext,
    build_fusion_card,
    build_relic_value_card,
    build_translate_card,
    build_upgrade_cost_card,
)
from milo_core.worldstate import (
    QueryMeta,
    build_conquest_card,
    build_fissures_card,
    build_news_card,
    build_timings_card,
    build_varzia_card,
)

NOW = 1_800_000_000.0
META = QueryMeta(NOW, NOW - 5, [])
NODES = {
    "SolNode122": NodeInfo("Stephano", "天王星", 8, 0),
    "SolNode310": NodeInfo("Mot", "虚空", 2, 4),
    "EarthHUB": NodeInfo("Strata 中继站", "地球", 100, 0),
}
TRANS = TranslationIndex(
    {
        "/Lotus/Types/Items/Primes/VoltPrimeSet": "伏特 Prime 一套",
        "/Lotus/StoreItems/Types/Items/Primes/VoltPack": "Volt Prime 组合包",
        "/Lotus/Variables/Conquest/TestDev": "超载护盾",
        "/Lotus/Variables/Conquest/TestRisk": "能量枯竭",
    },
    {},
)


def _mongo_ts(seconds: float) -> dict[str, dict[str, str]]:
    return {"$date": {"$numberLong": str(int(seconds * 1000))}}


def test_command_flags_and_pagination() -> None:
    f1 = parse_command_flags("MK1-Braton -en -2 -w")
    assert f1.cleaned == "MK1-Braton"
    assert f1.english is True
    assert f1.text_only is True
    assert f1.page == 2

    f2 = parse_command_flags("托里德-3")
    assert f2.cleaned == "托里德"
    assert f2.page == 3

    f3 = parse_command_flags("托里德 +180% 暴击 -2", allow_page=False)
    assert f3.cleaned == "托里德 +180% 暴击 -2"
    assert f3.page == 1

    sliced, page, total = paginate(list(range(1, 20)), 2, 8)
    assert sliced == list(range(9, 17))
    assert (page, total) == (2, 3)
    assert "第 2/3 页" in page_caption(page, total)


def test_wm_stats_and_copper_ducats() -> None:
    stats_body = {
        "payload": {
            "statistics_closed": {
                "48hours": [{"volume": 10, "wa_price": 90.0, "min_price": 80, "max_price": 100}],
                "90days": [{"volume": 100, "wa_price": 95.0, "min_price": 70, "max_price": 120}],
            }
        }
    }
    summary = parse_wm_stats(stats_body)
    assert "48h：均价 90.0p (80~100p · 成交 10)" in summary
    assert "90d：均价 95.0p (70~120p · 成交 100)" in summary

    ducat_body = {
        "payload": {
            "previous_day": [
                {
                    "item": "id_cu15",
                    "ducats": 15,
                    "wa_price": 1.5,
                    "ducats_per_platinum_wa": 10.0,
                    "volume": 50,
                },
                {
                    "item": "id_ag45",
                    "ducats": 45,
                    "wa_price": 3.0,
                    "ducats_per_platinum_wa": 15.0,
                    "volume": 20,
                },
            ],
            "previous_hour": [],
        }
    }
    card = build_ducats_card("copper", ducat_body, {"id_cu15": "铜零件", "id_ag45": "银零件"}, META)
    assert card.title == "杜卡德铜垃圾排行"
    assert [r[1] for r in card.rows] == ["铜零件"]


def test_riven_slang_filters_faction_mult_and_omega_badges() -> None:
    parsed = parse_riven_query("托里德 基伤,g伤 零洗 v槽 3+1 1000p")
    assert parsed.weapon == "托里德"
    assert parsed.positive == "基伤,g伤"
    assert parsed.negative == "有"
    assert parsed.reroll == "zero"
    assert parsed.polarity == "madurai"
    assert parsed.stat_count == "3+1"
    assert parsed.max_price == 1000

    stats = [
        RivenStatInfo("base_damage_/_melee_damage", "基础伤害", "percent"),
        RivenStatInfo("damage_vs_grineer", "对 Grineer 伤害", "percent"),
        RivenStatInfo("critical_chance", "暴击几率", "percent"),
        RivenStatInfo("zoom", "变焦", "percent"),
    ]
    pos, neg = resolve_stat_filters("基伤,g伤", "有", stats, {})
    assert pos == "base_damage_/_melee_damage,damage_vs_grineer"
    assert neg == "has"

    raw_body = {
        "payload": {
            "auctions": [
                {
                    "closed": False,
                    "visible": True,
                    "platform": "pc",
                    "buyout_price": 800,
                    "owner": {"ingame_name": "TennoOne", "status": "ingame", "locale": "zh-hans"},
                    "item": {
                        "name": "critacan",
                        "mastery_level": 8,
                        "mod_rank": 8,
                        "re_rolls": 0,
                        "polarity": "madurai",
                        "attributes": [
                            {
                                "url_name": "base_damage_/_melee_damage",
                                "value": 180.0,
                                "positive": True,
                            },
                            {"url_name": "damage_vs_grineer", "value": 1.39, "positive": True},
                            {"url_name": "critical_chance", "value": 160.0, "positive": True},
                            {"url_name": "zoom", "value": -45.0, "positive": False},
                        ],
                    },
                },
                {
                    "closed": False,
                    "visible": True,
                    "platform": "pc",
                    "buyout_price": 1500,
                    "owner": {"ingame_name": "TennoExpensive", "status": "online"},
                    "item": {
                        "name": "highprice",
                        "re_rolls": 12,
                        "polarity": "vazarin",
                        "attributes": [
                            {"url_name": "critical_chance", "value": 120.0, "positive": True},
                        ],
                    },
                },
            ]
        }
    }
    weapon = Item("w1", "torid", "托里德", "Torid")
    meta = WeaponMeta("u1", "托里德", "Torid", "LongGuns", 1.3)
    trends = {"暴击几率": RivenTrendEntry("暴击几率", rifle=150.0)}
    card = build_riven_auctions_card(
        weapon,
        raw_body,
        {s.url_name: s for s in stats},
        "正面：基伤",
        META,
        options=RivenDisplayOptions(filters=parsed, weapon_meta=meta, trends=trends),
    )
    assert len(card.rows) == 1
    assert "×1.39 对 Grineer 伤害" in card.rows[0][1]
    assert "%" in card.rows[0][1]
    assert "快捷私聊 /w 1：" in card.stats_line


def test_worldstate_new_builders_and_compact_fissures() -> None:
    ws = {
        "ActiveMissions": [
            {
                "Node": "SolNode122",
                "MissionType": "MT_CAPTURE",
                "Modifier": "VoidT1",
                "Hard": False,
                "Expiry": _mongo_ts(NOW + 900),
            },
            {
                "Node": "SolNode310",
                "MissionType": "MT_SURVIVAL",
                "Modifier": "VoidT4",
                "Hard": False,
                "Expiry": _mongo_ts(NOW + 1200),
            },
        ],
        "PrimeVaultTraders": [
            {
                "Node": "EarthHUB",
                "Expiry": _mongo_ts(NOW + 36000),
                "Manifest": [
                    {
                        "ItemType": "/Lotus/StoreItems/Types/Items/Primes/VoltPack",
                        "PrimePrice": 6,
                        "RegularPrice": 0,
                    }
                ],
                "ScheduleInfo": [],
            }
        ],
        "Conquests": [
            {
                "Type": "CT_HEX",
                "Expiry": _mongo_ts(NOW + 86400),
                "Missions": [
                    {
                        "missionType": "MT_SURVIVAL",
                        "faction": "FC_SCALDRA",
                        "difficulties": [
                            {
                                "deviation": "TechrotConjunction",
                                "riskVariables": ["EximusGrenadiers"],
                            }
                        ],
                    },
                    {
                        "missionType": "MT_ENDLESS_CAPTURE",
                        "faction": "FC_TECHROT",
                        "difficulties": [
                            {
                                "deviation": "DoubleTroubleLegacyte",
                                "riskVariables": ["FortifiedFoes"],
                            }
                        ],
                    },
                ],
                "Variables": [
                    "ContactDamage",
                    "Undersupplied",
                    "DecayingFlesh",
                    "Framecurse",
                    "RangeDebuff",
                    "AntiGuard",
                    "AoeDebuff",
                    "InfectedWounds",
                ],
            }
        ],
        "Events": [
            {
                "Priority": True,
                "Date": _mongo_ts(NOW - 600),
                "Messages": [{"LanguageCode": "zh", "Message": "热修公告 0.6"}],
            }
        ],
        "SyndicateMissions": [
            {"Tag": "CetusSyndicate", "Expiry": _mongo_ts(NOW + 4500)},
            {"Tag": "ZarimanSyndicate", "Expiry": _mongo_ts(NOW + 4500)},
        ],
    }

    filtered = build_fissures_card(ws, NODES, "normal", META, filter_kw="捕获")
    assert len(filtered.rows) == 2
    assert filtered.rows[0][0] == "§古纪 (T1)"
    assert filtered.rows[1][0] == "G系 · 捕获"

    varzia = build_varzia_card(ws, NODES, TRANS, META)
    assert varzia.rows[0] == ("Volt Prime 组合包", "6 御品阿耶", "当期轮换")

    conquest = build_conquest_card(ws, TRANS, META)
    assert conquest.rows[0][0] == "§时光科研"
    assert "蜂拥污染" in conquest.rows[1][2]
    assert "传承细胞收割" in conquest.rows[2][1]
    assert "有丝分裂" in conquest.rows[2][2]
    for english_code in (
        "TechrotConjunction",
        "DoubleTroubleLegacyte",
        "Framecurse",
        "Undersupplied",
        "RangeDebuff",
        "AntiGuard",
        "AoeDebuff",
        "InfectedWounds",
    ):
        assert english_code not in conquest.text()

    news = build_news_card(ws, META)
    assert news.rows[0][:2] == ("置顶", "热修公告 0.6")

    timings = build_timings_card(ws, META, arbys_summary=("Hydron [A] G系 · 防御", "42m00s"))
    assert any(r[0] == "当前仲裁" for r in timings.rows)

    arb_list = build_arbitration_list_card(
        [[int(NOW + 3600), "SolNode122"], [int(NOW + 7200), "SolNode310"]],
        NODES,
        {"SolNode122": "S", "SolNode310": "D"},
        META,
        show_all=False,
    )
    assert len(arb_list.rows) == 1 and arb_list.rows[0][2] == "G系 · 防御"


def test_local_calculators_and_relic_value() -> None:
    items = [Item("id_v", "volt_prime_set", "伏特 Prime 一套", "Volt Prime Set")]
    tr = build_translate_card("Volt Prime", TRANS, items, {}, META)
    assert tr.rows[0][:2] == ("伏特 Prime 一套", "Volt Prime Set")

    fusion = build_fusion_card("25 60", META)
    assert "25%胚×" in fusion.stats_line
    assert any("60%" in row[1] for row in fusion.rows)

    upgrade = build_upgrade_cost_card("10 传奇", META)
    assert "40,920 内融核心" in upgrade.stats_line
    assert "1,976,436 星币" in upgrade.stats_line

    arcane = build_upgrade_cost_card("5 赋能", META)
    assert "21 个" in arcane.highlight

    ws = {
        "ActiveMissions": [
            {
                "Node": "SolNode122",
                "MissionType": "MT_CAPTURE",
                "Modifier": "VoidT1",
                "Expiry": _mongo_ts(NOW + 900),
            }
        ]
    }
    relics = [
        RelicEntry(
            "r1",
            "古纪 V1 遗物",
            (RelicReward("伏特 Prime 蓝图", "RARE", 1), RelicReward("Forma", "COMMON", 1)),
        )
    ]
    ctx = RelicValuationContext(
        ws=ws,
        nodes=NODES,
        relics=relics,
        items=[Item("i_volt", "volt_prime_blueprint", "伏特 Prime 蓝图", "Volt Prime Blueprint")],
        ducats_body={
            "payload": {"previous_hour": [{"item": "i_volt", "ducats": 100, "wa_price": 40.0}]}
        },
    )
    rv = build_relic_value_card("速刷 白金", ctx, META)
    assert rv.rows and rv.rows[0][0] == "古纪 V1 遗物"
    assert "4.0 白金" in rv.rows[0][2]


def test_subscription_schedule_and_foundry_store(tmp_path: Path) -> None:
    ev_type, filters = parse_subscribe_spec("警报 土豆 时段 9-22 单次")
    assert ev_type == "alerts"
    assert filters == {"keyword": "土豆", "active_hours": [9, 22], "once": True}
    assert "时段 09-22" in format_filter_summary(ev_type, filters)
    assert "单次" in format_filter_summary(ev_type, filters)

    # Timestamp at 2026-11-16 14:00 UTC+8 (06:00 UTC) -> inside 9-22.
    # Timestamp at 2026-11-16 03:00 UTC+8 (prev day 19:00 UTC) -> outside 9-22.
    rule = SubscriptionRule("s1", "alerts", filters, NOW)
    events = {"alerts": [DetectedEvent("alerts", "k1", ("n", "m", "土豆", "1h"), "土豆")]}
    meta_in = QueryMeta(1_794_808_800.0, 1_794_808_800.0, [])
    meta_out = QueryMeta(1_794_769_200.0, 1_794_769_200.0, [])
    inside = match_notifications([rule], events, {}, meta_in)
    outside = match_notifications([rule], events, {}, meta_out)
    assert len(inside) == 1 and inside[0].once is True
    assert outside == []

    cache = ResponseCache(tmp_path)
    cache.initialize()
    foundry = FoundryStore(cache.path)
    name, dur, due = parse_foundry_spec("Forma 23h", NOW)
    assert (name, dur) == ("Forma", 23 * 3600.0)
    rec = foundry.add("s1", name, due, user_id="u1")
    card = build_foundry_list_card(foundry.list_for_stream("s1"), NOW)
    assert card.rows[0][1] == "Forma"
    assert foundry.pop_due(NOW + 100) == []
    popped = foundry.pop_due(due + 1)
    assert [p.reminder_id for p in popped] == [rec.reminder_id]
    assert foundry.list_for_stream("s1") == []

    # Cancel single / all API.
    r2 = foundry.add("s1", "圣装系统", NOW + 1000)
    assert foundry.remove("s1", r2.reminder_id) is True
    assert foundry.remove_all("s1") == 0


async def test_plugin_e2e_v060_flags_tools_and_foundry(
    loaded_plugin: tuple[Any, list[dict[str, Any]]],
) -> None:
    plugin, calls = loaded_plugin

    def _handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "worldState.php" in url:
            return httpx.Response(
                200,
                json={
                    "ActiveMissions": [
                        {
                            "Node": "SolNode122",
                            "MissionType": "MT_CAPTURE",
                            "Modifier": "VoidT1",
                            "Hard": False,
                            "Expiry": _mongo_ts(time.time() + 1800),
                        }
                    ],
                    "Events": [
                        {
                            "Priority": True,
                            "Date": _mongo_ts(time.time() - 60),
                            "Messages": [{"LanguageCode": "zh", "Message": "测试公告"}],
                        }
                    ],
                    "SyndicateMissions": [
                        {"Tag": "CetusSyndicate", "Expiry": _mongo_ts(time.time() + 4500)},
                        {"Tag": "ZarimanSyndicate", "Expiry": _mongo_ts(time.time() + 4500)},
                    ],
                },
            )
        if url.endswith("/v2/items"):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "i1",
                            "slug": "volt_prime_set",
                            "i18n": {
                                "zh-hans": {"name": "伏特 Prime 一套"},
                                "en": {"name": "Volt Prime Set"},
                            },
                        }
                    ]
                },
            )
        if "/v2/orders/item/volt_prime_set" in url:
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "visible": True,
                            "itemId": "i1",
                            "type": "sell",
                            "platinum": 95,
                            "quantity": 1,
                            "user": {"ingameName": "SellerA", "status": "online"},
                        }
                    ]
                },
            )
        if "/v1/items/volt_prime_set/statistics" in url:
            return httpx.Response(
                200,
                json={
                    "payload": {
                        "statistics_closed": {
                            "48hours": [
                                {"volume": 5, "wa_price": 92.0, "min_price": 85, "max_price": 100}
                            ],
                            "90days": [],
                        }
                    }
                },
            )
        if "alias.json" in url:
            return httpx.Response(200, json=[])
        return httpx.Response(404)

    client = plugin._service.client
    await client.http.aclose()
    client.http = httpx.AsyncClient(transport=httpx.MockTransport(_handler))
    # `-1` forces pure-text output even when output_mode='image'.
    res = await plugin.handle_wf(matched_groups={"args": "新闻 -1"}, stream_id="chat-e")
    assert res[0] is True
    assert calls[-1]["capability"] == "send.text"
    assert "测试公告" in calls[-1]["args"]["text"]

    # `/wm -en -1` shows English item name & WM 48h stats.
    res_wm = await plugin.handle_market(
        matched_groups={"query": "伏特 Prime 一套 -en -1"}, stream_id="chat-e"
    )
    assert res_wm[0] is True
    assert "Volt Prime Set" in calls[-1]["args"]["text"]
    assert "48h：均价 92.0p" in calls[-1]["args"]["text"]

    # LLM Tool exposes /翻译 /融合 /开核桃 /铸造提醒 cleanly.
    tr_tool = await plugin.handle_world_tool(topic="翻译", keyword="Volt Prime", stream_id="chat-e")
    assert "伏特 Prime 一套" in tr_tool["content"]

    f_tool = await plugin.handle_world_tool(
        topic="铸造提醒", keyword="Forma 1h", stream_id="chat-e"
    )
    assert "已添加铸造提醒" in f_tool["content"]

    # Fast-forward due_at in SQLite and trigger background poll delivery.
    with closing(sqlite3.connect(plugin._foundry.path)) as conn:
        conn.execute("UPDATE foundry_reminders SET due_at = ?", (time.time() - 5,))
        conn.commit()
    delivered = await plugin.poll_subscriptions_once()
    assert delivered == 1
    assert "Forma" in calls[-1]["args"]["text"]

    # Tool foundry without stream_id isolates by caller identity or rejects cleanly.
    anon_res = await plugin.handle_world_tool(topic="铸造提醒", keyword="Volt 1h")
    assert "缺少当前会话或调用者标识" in anon_res["content"]

    u1_add = await plugin.handle_world_tool(topic="铸造提醒", keyword="Nova 1h", user_id="u1")
    u2_list = await plugin.handle_world_tool(topic="铸造列表", user_id="u2")
    assert "已添加铸造提醒" in u1_add["content"]
    assert "Nova" not in u2_list["content"]
