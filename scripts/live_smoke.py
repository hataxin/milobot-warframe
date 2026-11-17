"""Run real public queries through the SDK and capture replies locally.

No connection to a running Milo bot host or chat platform is made. Only the final
Host send boundary is captured; HTTP, business logic and image rendering run.
"""

import asyncio
import base64
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

from maibot_sdk.context import PluginContext, PluginPaths

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts"


async def _run_subscription_smoke(plugin: Any, set_current: Any) -> None:
    set_current("subscribe-alert")
    assert (await plugin.handle_wf(matched_groups={"args": "订阅 警报"}, stream_id="local-smoke"))[
        0
    ]
    set_current("subscriptions")
    assert (await plugin.handle_wf(matched_groups={"args": "订阅列表"}, stream_id="local-smoke"))[0]
    set_current("unsubscribe-all")
    assert (await plugin.handle_wf(matched_groups={"args": "退订 全部"}, stream_id="local-smoke"))[
        0
    ]


async def _run_phase_d_smoke(plugin: Any, set_current: Any) -> None:
    set_current("ducats-gold")
    assert (
        await plugin.handle_market(matched_groups={"query": "金垃圾"}, stream_id="local-smoke")
    )[0]
    set_current("ducats-silver")
    assert (
        await plugin.handle_market(matched_groups={"query": "银垃圾"}, stream_id="local-smoke")
    )[0]
    set_current("ducats-copper")
    assert (
        await plugin.handle_market(matched_groups={"query": "铜垃圾"}, stream_id="local-smoke")
    )[0]
    set_current("riven")
    assert (await plugin.handle_riven(matched_groups={"query": "托里德"}, stream_id="local-smoke"))[
        0
    ]
    set_current("whisper-riven")
    await plugin.handle_whisper(matched_groups={"arg": "1"}, stream_id="local-smoke")
    set_current("lich")
    assert (await plugin.handle_lich(matched_groups={"query": "布拉玛"}, stream_id="local-smoke"))[
        0
    ]
    set_current("sister")
    assert (await plugin.handle_sister(matched_groups={"query": "典客"}, stream_id="local-smoke"))[
        0
    ]
    set_current("riven-analyse-help")
    assert (await plugin.handle_wf(matched_groups={"args": "紫卡分析"}, stream_id="local-smoke"))[0]
    set_current("riven-analyse")
    assert (
        await plugin.handle_wf(
            matched_groups={"args": "紫卡分析 托里德 +180% 暴击几率 +140% 暴击伤害 -45% 变焦"},
            stream_id="local-smoke",
        )
    )[0]
    for key, args in (
        ("help", "帮助"),
        ("varzia", "瓦奇娅"),
        ("conquest", "科研"),
        ("news", "新闻"),
        ("timings", "时效"),
        ("translate", "翻译 Volt Prime"),
        ("fusion", "融合 38.5 60"),
        ("upgrade-cost", "升级消耗 10 传奇"),
        ("relic-value", "开核桃 全部 白金"),
        ("foundry-add", "铸造提醒 Forma 23h"),
        ("foundry-list", "铸造列表"),
        ("foundry-clear", "取消铸造 全部"),
    ):
        set_current(key)
        assert (await plugin.handle_wf(matched_groups={"args": args}, stream_id="local-smoke"))[0]


async def main() -> None:
    """Exercise cycle and market commands, saving their SDK image payloads."""
    spec = importlib.util.spec_from_file_location(
        "milobot_live_smoke", ROOT / "plugin.py", submodule_search_locations=[str(ROOT)]
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    OUTPUT.mkdir(exist_ok=True)
    current = "status"
    replies: list[dict[str, Any]] = []

    async def capture(method: str, plugin_id: str, payload: dict[str, Any] | None) -> Any:
        assert method == "cap.call" and plugin_id == "github.hataxin.milobot-warframe"
        assert payload is not None
        args = payload["args"]
        if payload["capability"] == "send.image":
            image = base64.b64decode(args["image_base64"])
            (OUTPUT / f"{current}.png").write_bytes(image)
            replies.append({"query": current, "reply": "image", "bytes": len(image)})
        else:
            (OUTPUT / f"{current}.txt").write_text(args["text"], encoding="utf-8")
            replies.append({"query": current, "reply": "text", "text": args["text"]})
        return {"success": True}

    plugin = module.create_plugin()
    plugin.set_plugin_config({})
    plugin._set_context(
        PluginContext(
            "github.hataxin.milobot-warframe",
            capture,
            PluginPaths(OUTPUT / "data", OUTPUT / "temp"),
        )
    )
    await plugin.on_load()
    try:
        assert (await plugin.handle_wf(matched_groups={"args": "状态"}, stream_id="local-smoke"))[0]
        current = "cycles"
        assert (await plugin.handle_wf(matched_groups={"args": "平原"}, stream_id="local-smoke"))[0]
        current = "market"
        assert (
            await plugin.handle_market(matched_groups={"query": "电男"}, stream_id="local-smoke")
        )[0]
        current = "max-rank"
        assert (
            await plugin.handle_market(
                matched_groups={"query": "压迫点p 买家 满级"}, stream_id="local-smoke"
            )
        )[0]
        for key, args in (
            ("alerts", "警报"),
            ("fissures", "裂缝"),
            ("steel-fissures", "钢铁裂缝"),
            ("storm-fissures", "九重天裂缝"),
            ("sortie", "突击"),
            ("archon", "猎杀"),
            ("invasions", "入侵"),
            ("void-trader", "奸商"),
            ("steel-path", "钢铁"),
            ("nightwave", "电波"),
            ("daily-deals", "每日特惠"),
            ("calendar", "1999"),
            ("syndicate-cetus", "地球赏金"),
            ("duviri", "轮换"),
            ("arbitration", "仲裁"),
            ("arbitration-list", "仲裁表"),
            ("relics", "遗物 电男"),
            ("subscription-help", "订阅"),
        ):
            current = key
            assert (await plugin.handle_wf(matched_groups={"args": args}, stream_id="local-smoke"))[
                0
            ]

        def set_current(name: str) -> None:
            nonlocal current
            current = name

        await _run_subscription_smoke(plugin, set_current)
        await _run_phase_d_smoke(plugin, set_current)
        world_tool = await plugin.handle_world_tool(topic="金垃圾", stream_id="local-smoke")
        assert "杜卡德金垃圾" in world_tool["content"]
        market_tool = await plugin.handle_market_tool(
            item_name="Volt Prime Set", order_type="sell", stream_id="local-smoke"
        )
        assert "Volt Prime" in market_tool["content"] or "暂无符合条件" in market_tool["content"]
        replies.append(
            {"query": "tool-world", "reply": "tool", "chars": len(world_tool["content"])}
        )
        replies.append(
            {"query": "tool-market", "reply": "tool", "chars": len(market_tool["content"])}
        )
        item_count = plugin._service.item_count
    finally:
        await plugin.on_unload()
    result = {
        "queries": replies,
        "item_count": item_count,
        "closed": True,
        "chat_platform_contacted": False,
    }
    (OUTPUT / "live-smoke.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
