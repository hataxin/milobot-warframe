import base64
import io
import re
import time
from typing import Any

import httpx
from maibot_sdk.components import collect_components
from PIL import Image


async def use_transport(plugin: Any, handler: Any) -> None:
    client = plugin._service.client
    await client.http.aclose()
    client.http = httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_sdk_discovery_and_status_do_not_require_network(
    loaded_plugin: tuple[Any, list[dict[str, Any]]],
) -> None:
    plugin, calls = loaded_plugin
    components = collect_components(plugin)
    assert {component["name"] for component in components} == {
        "wf_dispatch",
        "wf_market",
        "wf_riven",
        "wf_lich",
        "wf_sister",
        "wf_whisper",
        "warframe_world_query",
        "warframe_market_query",
    }
    assert not any("nyx" in component["name"].casefold() for component in components)
    market = next(component for component in components if component["name"] == "wf_market")
    match = re.fullmatch(market["metadata"]["command_pattern"], "/wm Frost Prime Set 买家")
    assert match is not None and match.group("query") == "Frost Prime Set 买家"

    world_tool = next(c for c in components if c["name"] == "warframe_world_query")
    assert world_tool["type"] == "TOOL"
    assert [p["name"] for p in world_tool["metadata"]["parameters"]] == ["topic", "keyword"]
    market_tool = next(c for c in components if c["name"] == "warframe_market_query")
    assert market_tool["type"] == "TOOL"
    assert [p["name"] for p in market_tool["metadata"]["parameters"]] == [
        "item_name",
        "order_type",
        "max_rank",
    ]

    result = await plugin.handle_wf(matched_groups={"args": "状态"}, stream_id="chat-a")
    assert result[0] is True and result[2] == 2
    assert calls[-1]["capability"] == "send.text"
    assert calls[-1]["args"]["stream_id"] == "chat-a"
    assert "本地物品索引" in calls[-1]["args"]["text"]
    assert "本会话订阅：0 条" in calls[-1]["args"]["text"]
    assert "Milo bot · Warframe 助手 1.0.0" in calls[-1]["args"]["text"]
    assert "nyx" not in calls[-1]["args"]["text"].casefold()
    assert "maibot" not in calls[-1]["args"]["text"].casefold()
    help_res = await plugin.handle_wf(matched_groups={"args": "帮助"}, stream_id="chat-a")
    assert help_res[0] is True
    assert calls[-1]["capability"] == "send.image"
    help_text_res = await plugin.handle_wf(matched_groups={"args": "帮助 -1"}, stream_id="chat-a")
    assert help_text_res[0] is True
    assert calls[-1]["capability"] == "send.text"
    assert "nyx" not in calls[-1]["args"]["text"].casefold()
    assert "maibot" not in calls[-1]["args"]["text"].casefold()


async def test_cycles_run_through_real_sdk_image_capability(
    loaded_plugin: tuple[Any, list[dict[str, Any]]],
) -> None:
    plugin, calls = loaded_plugin
    expiry = str(int((time.time() + 5000) * 1000))
    body = {
        "SyndicateMissions": [
            {"Tag": "CetusSyndicate", "Expiry": {"$date": {"$numberLong": expiry}}}
        ]
    }
    await use_transport(plugin, lambda _: httpx.Response(200, json=body))
    component = next(c for c in collect_components(plugin) if c["name"] == "wf_dispatch")
    match = re.search(component["metadata"]["command_pattern"], "@Milo  /平原")
    assert match is not None
    result = await plugin.handle_wf(matched_groups=match.groupdict(), stream_id="chat-a")
    assert result[0] is True
    assert calls[-1]["capability"] == "send.image"
    image = base64.b64decode(calls[-1]["args"]["image_base64"])
    with Image.open(io.BytesIO(image)) as card:
        assert card.format == "PNG" and card.width == 1080


async def test_market_orders_are_sent_as_structured_text_rows(
    loaded_plugin: tuple[Any, list[dict[str, Any]]],
) -> None:
    plugin, calls = loaded_plugin
    settings = plugin.get_plugin_config_data()
    settings["output_mode"] = "text"
    plugin.set_plugin_config(settings)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/items"):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "1",
                            "slug": "volt_prime_set",
                            "i18n": {"en": {"name": "Volt Prime Set"}},
                        }
                    ]
                },
            )
        if request.url.path.endswith("alias.json"):
            return httpx.Response(200, json=[])
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "visible": True,
                        "itemId": "1",
                        "type": "sell",
                        "platinum": 42,
                        "quantity": 2,
                        "rank": 3,
                        "user": {"status": "ingame", "ingameName": "Tenno"},
                    }
                ]
            },
        )

    await use_transport(plugin, handler)
    assert (
        await plugin.handle_market(matched_groups={"query": "Volt Prime Set"}, stream_id="chat-a")
    )[0]
    text = calls[-1]["args"]["text"]
    assert "玩家 · 状态 · 单价 / 白金 · 数量 · 等级" in text
    assert "Tenno · 游戏中 · 42 · 2 · 3" in text


async def test_bad_font_falls_back_to_text_in_the_same_stream(
    loaded_plugin: tuple[Any, list[dict[str, Any]]],
) -> None:
    plugin, calls = loaded_plugin
    settings = plugin.get_plugin_config_data()
    settings["font_path"] = "does-not-exist.ttf"
    plugin.set_plugin_config(settings)
    expiry = str(int((time.time() + 5000) * 1000))
    await use_transport(
        plugin,
        lambda _: httpx.Response(
            200,
            json={
                "SyndicateMissions": [
                    {"Tag": "CetusSyndicate", "Expiry": {"$date": {"$numberLong": expiry}}}
                ]
            },
        ),
    )
    assert (await plugin.handle_wf(matched_groups={"args": "平原"}, stream_id="chat-a"))[0] is True
    assert calls[-1]["capability"] == "send.text"
    assert "夜灵平原" in calls[-1]["args"]["text"]


async def test_candidates_do_not_cross_chat_streams(
    loaded_plugin: tuple[Any, list[dict[str, Any]]],
) -> None:
    plugin, calls = loaded_plugin
    settings = plugin.get_plugin_config_data()
    settings["output_mode"] = "text"
    plugin.set_plugin_config(settings)
    items = [
        {"id": "1", "slug": "volt_prime_set", "i18n": {"en": {"name": "Volt Prime Set"}}},
        {
            "id": "2",
            "slug": "volt_prime_blueprint",
            "i18n": {"en": {"name": "Volt Prime Blueprint"}},
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("alias.json"):
            return httpx.Response(200, json=[])
        if request.url.path.endswith("/items"):
            return httpx.Response(200, json={"data": items})
        return httpx.Response(200, json={"data": []})

    await use_transport(plugin, handler)
    assert (await plugin.handle_market(matched_groups={"query": "prime"}, stream_id="chat-a"))[
        0
    ] is True
    assert "请选择" in calls[-1]["args"]["text"]
    assert (await plugin.handle_market(matched_groups={"query": "1"}, stream_id="chat-b"))[
        0
    ] is False
    assert "没有有效候选" in calls[-1]["args"]["text"]
    assert (await plugin.handle_market(matched_groups={"query": "1"}, stream_id="chat-a"))[
        0
    ] is True
    assert "暂无符合条件" in calls[-1]["args"]["text"]
    assert "玩家 · 状态 · 单价 / 白金 · 数量" in calls[-1]["args"]["text"]


async def test_config_reload_closes_old_http_and_keeps_new_instance_usable(
    loaded_plugin: tuple[Any, list[dict[str, Any]]],
) -> None:
    plugin, _ = loaded_plugin
    old_http = plugin._service.client.http
    settings = plugin.get_plugin_config_data()
    settings["output_mode"] = "text"
    await plugin.on_config_update("self", settings, "0.1.0")
    assert old_http.is_closed
    assert plugin._service.client.http is not old_http
    assert (await plugin.handle_wf(matched_groups={"args": "状态"}, stream_id="chat-a"))[0] is True


async def test_missing_stream_never_sends_messages(
    loaded_plugin: tuple[Any, list[dict[str, Any]]],
) -> None:
    plugin, calls = loaded_plugin
    assert (await plugin.handle_wf(matched_groups={"args": "平原"}))[0] is False
    assert (await plugin.handle_market(matched_groups={"query": "电男"}))[0] is False
    assert calls == []


async def test_phase_b_commands_route_and_degrade_safely(
    loaded_plugin: tuple[Any, list[dict[str, Any]]],
) -> None:
    import lzma

    plugin, calls = loaded_plugin
    now = time.time()
    expiry = str(int((now + 5000) * 1000))
    ws_body = {
        "SyndicateMissions": [
            {"Tag": "CetusSyndicate", "Expiry": {"$date": {"$numberLong": expiry}}},
            {"Tag": "ZarimanSyndicate", "Expiry": {"$date": {"$numberLong": expiry}}},
        ],
        "Alerts": [
            {
                "Expiry": {"$date": {"$numberLong": expiry}},
                "MissionInfo": {
                    "location": "SolNode1",
                    "missionType": "MT_DEFENSE",
                    "faction": "FC_GRINEER",
                    "missionReward": {"credits": 10000},
                },
            }
        ],
        "EndlessXpSchedule": [
            {"CategoryChoices": [{"Category": "EXC_NORMAL", "Choices": ["Gara"]}]}
        ],
    }
    index_bytes = lzma.compress(
        b"ExportRegions_zh.json!00_r1\nExportRelicArcane_zh.json!00_ra\n",
        format=lzma.FORMAT_ALONE,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "worldState.php" in url:
            return httpx.Response(200, json=ws_body)
        if "index_zh.txt.lzma" in url:
            return httpx.Response(200, content=index_bytes)
        if "ExportRegions_zh.json" in url:
            return httpx.Response(
                200,
                json={"ExportRegions": [{"uniqueName": "SolNode1", "name": "地球节点"}]},
            )
        if "ExportRelicArcane_zh.json" in url:
            return httpx.Response(
                200,
                json={
                    "ExportRelicArcane": [
                        {
                            "uniqueName": "/Lotus/Relics/A1",
                            "name": "中纪 A1 遗物",
                            "codexSecret": False,
                            "relicRewards": [
                                {
                                    "rewardName": "/Lotus/Types/Forma",
                                    "rarity": "COMMON",
                                    "itemCount": 1,
                                }
                            ],
                        }
                    ]
                },
            )
        if "arbys.txt" in url:
            return httpx.Response(
                200,
                text=f"{int(now) - 100},SolNode1\n{int(now) + 3600},SolNode1\n",
            )
        if "arbitration_tiers.json" in url:
            return httpx.Response(200, json=[{"key": "SolNode1", "tier": "S"}])
        if "alias.json" in url:
            return httpx.Response(200, json=[])
        return httpx.Response(404)

    await use_transport(plugin, handler)
    for cmd in ("钢铁", "警报", "轮换", "仲裁", "仲裁表", "遗物", "遗物 中纪 A1"):
        res = await plugin.handle_wf(matched_groups={"args": cmd}, stream_id="chat-a")
        assert res[0] is True, f"{cmd} failed: {calls[-1]}"
        assert calls[-1]["capability"] == "send.image"

    tier_only = await plugin.handle_wf(matched_groups={"args": "遗物 中纪"}, stream_id="chat-a")
    assert tier_only[0] is False
    assert "纪元档位" in calls[-1]["args"]["text"]


async def test_phase_b_upstream_failure_is_not_disguised_as_empty(
    loaded_plugin: tuple[Any, list[dict[str, Any]]],
) -> None:
    plugin, calls = loaded_plugin
    await use_transport(plugin, lambda _: httpx.Response(500))
    res = await plugin.handle_wf(matched_groups={"args": "仲裁表"}, stream_id="chat-a")
    assert res[0] is False
    assert calls[-1]["capability"] == "send.text"
    assert "重试" in calls[-1]["args"]["text"] or "无法访问" in calls[-1]["args"]["text"]


async def test_tools_share_service_and_never_send_messages(
    loaded_plugin: tuple[Any, list[dict[str, Any]]],
) -> None:
    plugin, calls = loaded_plugin
    expiry = str(int((time.time() + 5000) * 1000))
    items = [
        {"id": "1", "slug": "volt_prime_set", "i18n": {"en": {"name": "Volt Prime Set"}}},
        {
            "id": "2",
            "slug": "volt_prime_blueprint",
            "i18n": {"en": {"name": "Volt Prime Blueprint"}},
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "worldState.php" in url:
            return httpx.Response(
                200,
                json={
                    "SyndicateMissions": [
                        {"Tag": "CetusSyndicate", "Expiry": {"$date": {"$numberLong": expiry}}}
                    ]
                },
            )
        if url.endswith("/items"):
            return httpx.Response(200, json={"data": items})
        if url.endswith("alias.json"):
            return httpx.Response(200, json=[])
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "visible": True,
                        "itemId": "1",
                        "type": "sell",
                        "platinum": 55,
                        "quantity": 1,
                        "user": {"status": "online", "ingameName": "MiloPlayer"},
                    }
                ]
            },
        )

    await use_transport(plugin, handler)
    world_res = await plugin.handle_world_tool(topic="平原", stream_id="chat-a")
    assert world_res["name"] == "warframe_world_query"
    assert "平原周期" in world_res["content"] and "夜灵平原" in world_res["content"]

    unknown_res = await plugin.handle_world_tool(topic="未知测试主题", stream_id="chat-a")
    assert "可用主题" in unknown_res["content"]

    multi_res = await plugin.handle_market_tool(item_name="prime", stream_id="chat-a")
    assert "找到 2 个匹配物品" in multi_res["content"]
    assert "/wm 编号" not in multi_res["content"]
    assert plugin._pending == {}

    exact_res = await plugin.handle_market_tool(item_name="Volt Prime Set", order_type="sell")
    assert "MiloPlayer" in exact_res["content"] and "55" in exact_res["content"]
    assert calls == []

    disabled_cfg = plugin.get_plugin_config_data()
    disabled_cfg["enabled"] = False
    await plugin.on_config_update("self", disabled_cfg, "0.4.0")
    assert "已停用" in (await plugin.handle_world_tool(topic="平原"))["content"]
    assert "已停用" in (await plugin.handle_market_tool(item_name="Volt Prime Set"))["content"]
    assert calls == []


async def test_subscription_lifecycle_and_legacy_config_reload(
    loaded_plugin: tuple[Any, list[dict[str, Any]]],
) -> None:
    plugin, _ = loaded_plugin
    first_task = plugin._poll_task
    assert first_task is not None and not first_task.done()

    legacy_cfg = {
        "enabled": True,
        "output_mode": "text",
        "font_path": "",
        "timeout_seconds": 10.0,
        "plugin": {"config_version": "0.1.0"},
    }
    await plugin.on_config_update("self", legacy_cfg, "0.4.0")
    assert first_task.done()
    second_task = plugin._poll_task
    assert second_task is not None and second_task is not first_task and not second_task.done()
    assert plugin.settings.subscription_enabled is True
    assert plugin.settings.subscription_interval_seconds == 120

    no_sub_cfg = plugin.get_plugin_config_data()
    no_sub_cfg["subscription_enabled"] = False
    await plugin.on_config_update("self", no_sub_cfg, "0.4.0")
    assert second_task.done()
    assert plugin._poll_task is None


def _make_alert(alert_id: str, expiry_ms: str, location: str = "SolNode1") -> dict[str, Any]:
    return {
        "_id": {"$oid": alert_id},
        "Expiry": {"$date": {"$numberLong": expiry_ms}},
        "MissionInfo": {
            "location": location,
            "missionType": "MT_DEFENSE",
            "faction": "FC_GRINEER",
            "missionReward": {"credits": 15000},
        },
    }


async def test_subscription_commands_help_list_and_unsubscribe(
    loaded_plugin: tuple[Any, list[dict[str, Any]]],
) -> None:
    plugin, calls = loaded_plugin
    assert (await plugin.handle_wf(matched_groups={"args": "订阅"}, stream_id="chat-a"))[0]
    assert calls[-1]["capability"] == "send.image"

    assert (await plugin.handle_wf(matched_groups={"args": "订阅 警报 Forma"}, stream_id="chat-a"))[
        0
    ]
    assert "警报" in calls[-1]["args"]["text"]

    assert (await plugin.handle_wf(matched_groups={"args": "订阅列表"}, stream_id="chat-a"))[0]
    assert calls[-1]["capability"] == "send.image"

    assert (await plugin.handle_wf(matched_groups={"args": "退订 警报"}, stream_id="chat-a"))[0]
    assert "已退订" in calls[-1]["args"]["text"]
    assert (await plugin.handle_wf(matched_groups={"args": "退订 警报"}, stream_id="chat-a"))[0]
    assert "未订阅" in calls[-1]["args"]["text"]


def _make_failing_plugin(
    plugin_module: Any,
    tmp_path: Any,
    sent_records: list[dict[str, Any]],
    fail_streams: set[str],
) -> Any:
    from maibot_sdk.context import PluginContext, PluginPaths

    async def rpc(
        method: str, plugin_id: str, payload: dict[str, Any] | None, **kwargs: Any
    ) -> Any:
        del method, plugin_id, kwargs
        assert payload is not None
        cap = payload["capability"]
        stream_id = str(payload["args"].get("stream_id") or "")
        if cap in {"send.image", "send.text"} and stream_id in fail_streams:
            if cap == "send.image":
                return {"success": False}
            raise RuntimeError("transient network error on bad stream")
        sent_records.append(payload)
        return {"success": True}

    plugin = plugin_module.create_plugin()
    plugin.set_plugin_config({})
    text_cfg = plugin.get_plugin_config_data()
    text_cfg["output_mode"] = "text"
    plugin.set_plugin_config(text_cfg)
    plugin._set_context(
        PluginContext(
            "github.hataxin.milobot-warframe",
            rpc,
            PluginPaths(tmp_path / "data", tmp_path / "temp"),
        )
    )
    return plugin


async def test_subscription_end_to_end_dedup_reload_and_partial_failure(
    plugin_module: Any,
    tmp_path: Any,
) -> None:
    sent_records: list[dict[str, Any]] = []
    fail_streams: set[str] = {"chat-bad"}
    http_calls = 0
    plugin = _make_failing_plugin(plugin_module, tmp_path, sent_records, fail_streams)
    await plugin.on_load()
    try:
        expiry = str(int((time.time() + 5000) * 1000))
        alerts: list[dict[str, Any]] = [_make_alert("alert-1", expiry)]

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal http_calls
            http_calls += 1
            if "worldState.php" in str(request.url):
                return httpx.Response(200, json={"SyndicateMissions": [], "Alerts": alerts})
            return httpx.Response(404)

        await use_transport(plugin, handler)
        assert await plugin.poll_subscriptions_once() == 0
        assert http_calls == 0

        await plugin.handle_wf(matched_groups={"args": "订阅 警报"}, stream_id="chat-good")
        plugin._subscriptions.upsert("chat-bad", "alerts", {})
        sent_records.clear()

        assert await plugin.poll_subscriptions_once() == 1
        assert [r["args"]["stream_id"] for r in sent_records] == ["chat-good"]
        assert plugin._subscriptions.has_delivered("chat-good", "alerts:alert-1")
        assert not plugin._subscriptions.has_delivered("chat-bad", "alerts:alert-1")

        # Reload with identical WorldState: chat-bad retries cleanly, chat-good does not resend.
        fail_streams.clear()
        sent_records.clear()
        await plugin.on_config_update("self", plugin.get_plugin_config_data(), "0.4.0")
        await use_transport(plugin, handler)

        assert await plugin.poll_subscriptions_once() == 1
        assert [r["args"]["stream_id"] for r in sent_records] == ["chat-bad"]
        assert plugin._subscriptions.has_delivered("chat-bad", "alerts:alert-1")
        assert await plugin.poll_subscriptions_once() == 0

        # Mutate WorldState & switch to image mode: pushes new alert-2 PNG to both streams.
        from milo_core.client import WORLDSTATE_URL

        sent_records.clear()
        alerts.append(_make_alert("alert-2", expiry, location="SolNode2"))
        img_cfg = plugin.get_plugin_config_data()
        img_cfg["output_mode"] = "image"
        await plugin.on_config_update("self", img_cfg, "0.4.0")
        await use_transport(plugin, handler)
        plugin._service.client.cache.put(WORLDSTATE_URL, {}, fetched_at=time.time() - 60)
        assert await plugin.poll_subscriptions_once() == 2
        assert {r["args"]["stream_id"] for r in sent_records} == {"chat-good", "chat-bad"}
        assert all(r["capability"] == "send.image" for r in sent_records)
        assert (await plugin.handle_wf(matched_groups={"args": "退订 全部"}, stream_id="chat-bad"))[
            0
        ]
    finally:
        await plugin.on_unload()


_PHASE_D_STATIC_ROUTES: dict[str, Any] = {
    "/v2/items": {
        "data": [
            {
                "id": "volt_h",
                "slug": "volt_prime_neuroptics_blueprint",
                "i18n": {
                    "zh-hans": {"name": "Volt Prime 头部"},
                    "en": {"name": "Volt Prime Neuroptics"},
                },
            },
            {
                "id": "volt_s",
                "slug": "volt_prime_systems_blueprint",
                "i18n": {
                    "zh-hans": {"name": "Volt Prime 系统"},
                    "en": {"name": "Volt Prime Systems"},
                },
            },
        ]
    },
    "/v2/riven/weapons": {
        "data": [
            {
                "id": "braton_1",
                "slug": "braton_vandal",
                "i18n": {"zh-hans": {"name": "布莱顿 破坏者"}, "en": {"name": "Braton Vandal"}},
            },
            {
                "id": "braton_2",
                "slug": "braton_prime",
                "i18n": {"zh-hans": {"name": "布莱顿 Prime"}, "en": {"name": "Braton Prime"}},
            },
        ]
    },
    "/v2/lich/weapons": {
        "data": [
            {
                "id": "bramma_id",
                "slug": "kuva_bramma",
                "i18n": {"zh-hans": {"name": "赤毒 布拉玛"}, "en": {"name": "Kuva Bramma"}},
            }
        ]
    },
    "/v2/orders/item/volt_prime_neuroptics_blueprint": {
        "data": [
            {
                "visible": True,
                "itemId": "volt_h",
                "type": "sell",
                "platinum": 22,
                "quantity": 1,
                "user": {"ingameName": "OrderSeller", "status": "online", "locale": "en"},
            }
        ]
    },
    "/v1/tools/ducats": {
        "payload": {
            "previous_day": [
                {
                    "item": "volt_h",
                    "ducats": 100,
                    "ducats_per_platinum_wa": 9.1,
                    "wa_price": 11.0,
                    "volume": 25,
                }
            ],
            "previous_hour": [],
        }
    },
    "market_riven_tion.json": [
        {"url_name": "critical_chance", "effect": "暴击几率", "units": "percent"}
    ],
    "market_riven_tion_alias.json": [{"cn": "爆率", "en": "critical_chance"}],
    "ExportWeapons_zh.json": {
        "ExportWeapons": [
            {
                "uniqueName": "/Lotus/Weapons/Torid",
                "name": "托里德",
                "productCategory": "LongGuns",
                "omegaAttenuation": 1.3,
                "description": "<LOWERCASE>Torid</LOWERCASE>",
            }
        ]
    },
    "riven_analyse_trend.json": [
        {
            "name": "暴击几率",
            "rifle": 150.0,
            "shotgun": 90.0,
            "pistol": 150.0,
            "melle": 180.0,
            "archwing": 100.0,
        }
    ],
    "alias.json": [],
}

_PHASE_D_AUCTIONS: dict[str, Any] = {
    "riven": {
        "payload": {
            "auctions": [
                {
                    "closed": False,
                    "visible": True,
                    "platform": "pc",
                    "crossplay": True,
                    "buyout_price": 450,
                    "owner": {"ingame_name": "RivenSeller", "status": "ingame", "locale": "en"},
                    "item": {
                        "name": "critacan",
                        "mastery_level": 12,
                        "mod_rank": 8,
                        "re_rolls": 5,
                        "polarity": "madurai",
                        "attributes": [
                            {"url_name": "critical_chance", "value": 155.0, "positive": True}
                        ],
                    },
                }
            ]
        }
    },
    "lich": {
        "payload": {
            "auctions": [
                {
                    "closed": False,
                    "visible": True,
                    "platform": "xbox",
                    "crossplay": True,
                    "buyout_price": 260,
                    "owner": {"ingame_name": "LichSeller", "status": "online", "locale": "zh-hans"},
                    "item": {"element": "heat", "damage": 56, "having_ephemera": True},
                }
            ]
        }
    },
}


def _phase_d_handler(request: httpx.Request) -> httpx.Response:
    import lzma

    url = str(request.url)
    if "index_zh.txt.lzma" in url:
        return httpx.Response(200, content=lzma.compress(b"ExportWeapons_zh.json!abc\n"))
    if "/v1/auctions/search" in url:
        kind = request.url.params.get("type", "")
        if kind in _PHASE_D_AUCTIONS:
            return httpx.Response(200, json=_PHASE_D_AUCTIONS[kind])
    for suffix, payload in _PHASE_D_STATIC_ROUTES.items():
        if url.endswith(suffix) or suffix in url.split("?")[0]:
            return httpx.Response(200, json=payload)
    return httpx.Response(404)


async def test_phase_d_ducats_and_riven_analyse_placeholder_e2e(
    loaded_plugin: tuple[Any, list[dict[str, Any]]],
) -> None:
    plugin, calls = loaded_plugin
    cfg = plugin.get_plugin_config_data()
    cfg["output_mode"] = "text"
    plugin.set_plugin_config(cfg)
    await use_transport(plugin, _phase_d_handler)

    ok_ducat, _, _ = await plugin.handle_market(
        matched_groups={"query": "金垃圾"}, stream_id="s1", user_id="u1"
    )
    assert ok_ducat and "杜卡德金垃圾排行" in calls[-1]["args"]["text"]
    assert "Volt Prime 头部" in calls[-1]["args"]["text"]

    ok_placeholder, _, _ = await plugin.handle_wf(
        matched_groups={"args": "紫卡分析 托里德 +180% 暴击几率"},
        stream_id="s1",
        user_id="u1",
    )
    assert ok_placeholder and calls[-1]["args"]["text"] == "暂未添加紫卡分析功能。"

    tool_res = await plugin.handle_world_tool(topic="紫卡分析", stream_id="s1")
    assert tool_res["content"] == "暂未添加紫卡分析功能。"


async def test_phase_d_candidates_and_whispers_isolated_e2e(
    loaded_plugin: tuple[Any, list[dict[str, Any]]],
) -> None:
    plugin, calls = loaded_plugin
    cfg = plugin.get_plugin_config_data()
    cfg["output_mode"] = "text"
    plugin.set_plugin_config(cfg)
    await use_transport(plugin, _phase_d_handler)

    await plugin.handle_market(matched_groups={"query": "Volt Prime"}, stream_id="s1", user_id="u1")
    assert "请选择物品" in calls[-1]["args"]["text"]
    await plugin.handle_riven(matched_groups={"query": "布莱顿"}, stream_id="s1", user_id="u1")
    assert "请选择紫卡武器" in calls[-1]["args"]["text"]

    await plugin.handle_riven(matched_groups={"query": "2 爆率"}, stream_id="s1", user_id="u1")
    assert "布莱顿 Prime 紫卡拍卖" in calls[-1]["args"]["text"]
    assert "RivenSeller" in calls[-1]["args"]["text"]

    await plugin.handle_market(matched_groups={"query": "1"}, stream_id="s1", user_id="u1")
    assert "Volt Prime 头部" in calls[-1]["args"]["text"]
    ok_wm_w, _, _ = await plugin.handle_whisper(
        matched_groups={"arg": "1"}, stream_id="s1", user_id="u1"
    )
    assert ok_wm_w and "/w OrderSeller" in calls[-1]["args"]["text"]

    await plugin.handle_lich(matched_groups={"query": "布拉玛"}, stream_id="s1", user_id="u1")
    assert "赤毒 布拉玛 · 赤毒巫妖拍卖" in calls[-1]["args"]["text"]
    ok_u1, _, _ = await plugin.handle_whisper(
        matched_groups={"arg": "1"}, stream_id="s1", user_id="u1"
    )
    expected = "/w LichSeller 你好! 我想购买你的「赤毒 布拉玛」（56% 火焰）（带幻纹）"
    assert ok_u1 and calls[-1]["args"]["text"] == expected
    ok_u2, _, _ = await plugin.handle_whisper(
        matched_groups={"arg": "1"}, stream_id="s1", user_id="u2"
    )
    assert not ok_u2 and "当前没有可用的私聊记录" in calls[-1]["args"]["text"]


def test_manifest_and_config_schema_follow_maibot_spec() -> None:
    import json
    import pathlib

    from milo_core.sdk_plugin import MiloBotPlugin

    root = pathlib.Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "_manifest.json").read_text(encoding="utf-8"))
    required = {
        "manifest_version",
        "id",
        "version",
        "name",
        "description",
        "author",
        "license",
        "urls",
        "host_application",
        "sdk",
        "capabilities",
        "i18n",
    }
    assert required.issubset(manifest)
    assert manifest["manifest_version"] == 2
    assert manifest["plugin_type"] == "tool"
    assert (root / manifest["changelog"]).is_file()
    dep_names = {d["name"] for d in manifest["dependencies"] if d["type"] == "python_package"}
    assert {"httpx", "pillow"}.issubset(dep_names)

    schema = MiloBotPlugin.build_config_schema(
        plugin_id=manifest["id"],
        plugin_name=manifest["name"],
        plugin_version=manifest["version"],
    )
    assert schema["sections"]["plugin"]["title"] == "插件版本"
    assert schema["sections"]["general"]["fields"]["font_path"]["placeholder"]
    assert schema["sections"]["general"]["fields"]["proxy_url"]["placeholder"]


async def test_proxy_url_config_and_fallback(
    loaded_plugin: tuple[Any, list[dict[str, Any]]],
) -> None:
    plugin, _ = loaded_plugin
    cfg = plugin.get_plugin_config_data()
    cfg["proxy_url"] = "127.0.0.1:7890"
    await plugin.on_config_update("self", cfg, "0.1.0")
    mounts = plugin._service.client.http._mounts
    assert any(transport is not None for transport in mounts.values())

    bad_cfg = dict(cfg)
    bad_cfg["proxy_url"] = "ftp://127.0.0.1:7890"
    await plugin.on_config_update("self", bad_cfg, "0.1.0")
    assert plugin._service is not None
