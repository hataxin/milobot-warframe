"""Exercise command discovery against text arriving from the Host matcher."""

import re
from typing import Any

import pytest
from maibot_sdk.components import collect_components


@pytest.mark.parametrize(
    "text",
    ["wm 电男 p", "/wm 电男 p", "@Milo  wm 电男 p", " @Milo /WM 电男 p", "@Milo\u2005wm 电男 p"],
)
def test_market_command_accepts_host_mention_prefix(
    plugin_module: Any,
    text: str,
) -> None:
    plugin = plugin_module.create_plugin()
    command = next(c for c in collect_components(plugin) if c["name"] == "wf_market")
    match = re.search(command["metadata"]["command_pattern"], text)
    assert match is not None, "Command misses the message and falls through to ordinary chat"
    assert match.group("query") == "电男 p"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("/帮助", "帮助"),
        ("@Milo /状态", "状态"),
        ("/平原", "平原"),
        ("@Milo  /平原", "平原"),
        ("@Milo /警报", "警报"),
        ("/钢铁裂缝", "钢铁裂缝"),
        ("@Milo /九重天裂缝", "九重天裂缝"),
        ("/突击", "突击"),
        ("@Milo /执刑官猎杀", "执刑官猎杀"),
        ("/入侵", "入侵"),
        ("/奸商", "奸商"),
        ("/钢铁", "钢铁"),
        ("/电波", "电波"),
        ("/每日特惠", "每日特惠"),
        ("/1999", "1999"),
        ("/地球赏金", "地球赏金"),
        ("/轮换", "轮换"),
        ("@Milo /仲裁表", "仲裁表"),
        ("@Milo /遗物 中纪 A1", "遗物 中纪 A1"),
        ("/遗物中纪 A1", "遗物中纪 A1"),
        ("/订阅 警报 土豆", "订阅 警报 土豆"),
        ("@Milo /订阅 裂缝 钢铁 后纪", "订阅 裂缝 钢铁 后纪"),
        ("/退订 全部", "退订 全部"),
        ("@Milo /订阅列表", "订阅列表"),
        ("/金垃圾", "金垃圾"),
        ("@Milo /银垃圾", "银垃圾"),
        ("/铜垃圾", "铜垃圾"),
        ("@Milo /铜垃圾 -1", "铜垃圾 -1"),
        ("/裂缝 钢铁 捕获 -2", "裂缝 钢铁 捕获 -2"),
        ("/仲裁表 所有 -2", "仲裁表 所有 -2"),
        ("/瓦奇娅 -1", "瓦奇娅 -1"),
        ("/科研", "科研"),
        ("/新闻 -2", "新闻 -2"),
        ("/时效", "时效"),
        ("/翻译 Volt", "翻译 Volt"),
        ("/融合 38.5 60", "融合 38.5 60"),
        ("/升级消耗 10 传奇", "升级消耗 10 传奇"),
        ("/开核桃 速刷 白金 -2", "开核桃 速刷 白金 -2"),
        ("/铸造提醒 Forma 23h", "铸造提醒 Forma 23h"),
        ("/铸造列表", "铸造列表"),
        ("/取消铸造 1", "取消铸造 1"),
        ("/紫卡分析", "紫卡分析"),
        ("@Milo /赤毒 布拉玛", "赤毒 布拉玛"),
    ],
)
def test_direct_slash_commands_accept_subcommands_and_mentions(
    plugin_module: Any,
    text: str,
    expected: str,
) -> None:
    plugin = plugin_module.create_plugin()
    command = next(c for c in collect_components(plugin) if c["name"] == "wf_dispatch")
    match = re.search(command["metadata"]["command_pattern"], text)
    assert match is not None and match.group("args") == expected


@pytest.mark.parametrize(
    ("cmd_name", "text", "group", "expected"),
    [
        ("wf_market", "/wm 金垃圾", "query", "金垃圾"),
        ("wf_market", "@Milo wm 银垃圾", "query", "银垃圾"),
        ("wf_riven", "/wr 托里德 爆率,爆伤 无", "query", "托里德 爆率,爆伤 无"),
        ("wf_riven", "@Milo wr 托里德-爆率-无", "query", "托里德-爆率-无"),
        ("wf_lich", "/cd 布拉玛", "query", "布拉玛"),
        ("wf_lich", "@Milo cd 布拉玛", "query", "布拉玛"),
        ("wf_sister", "/xt 典客", "query", "典客"),
        ("wf_whisper", "/w", "arg", None),
        ("wf_whisper", "/w 1", "arg", "1"),
        ("wf_whisper", "@Milo /w abc", "arg", "abc"),
        ("wf_whisper", "w 2", "num", "2"),
        ("wf_whisper", "@Milo w 10", "num", "10"),
    ],
)
def test_phase_d_commands_match_with_and_without_slash_or_mention(
    plugin_module: Any,
    cmd_name: str,
    text: str,
    group: str,
    expected: str | None,
) -> None:
    plugin = plugin_module.create_plugin()
    command = next(c for c in collect_components(plugin) if c["name"] == cmd_name)
    match = re.search(command["metadata"]["command_pattern"], text)
    assert match is not None
    assert match.group(group) == expected


@pytest.mark.parametrize(
    "text",
    [
        "你觉得 wm 电男 p 怎么样",
        "@Milo 你觉得 wm 电男 p 怎么样",
        "wmarket 电男",
        "平原",
        "突击",
        "/wf 平原",
        "wf 平原",
        "/其他命令",
        "/subscribe_other",
        "@Milo 今天聊 平原",
        "刚才出了一个 警报",
        "@Milo 遗物中纪 A1 掉什么",
        "1999 日历怎么看",
        "我想订阅警报通知",
        "@Milo 帮我订阅 裂缝",
        "你觉得 wr 托里德怎么样",
        "刚才看到 cd 布拉玛很便宜",
        "这个 xt 典客多少伤害",
        "w",
        "w nice!",
        "哈哈哈哈 w 1",
        "warframe 真好玩",
    ],
)
def test_ordinary_chat_does_not_trigger_query(
    plugin_module: Any,
    text: str,
) -> None:
    plugin = plugin_module.create_plugin()
    commands = [c for c in collect_components(plugin) if c["type"] == "COMMAND"]
    assert not any(re.search(c["metadata"]["command_pattern"], text) for c in commands)
