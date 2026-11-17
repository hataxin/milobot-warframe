"""Exercise shared card layout with bundled fonts and structured data."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from milo_core.card_model import Card
from milo_core.render import render_card


def dimensions(card: Card) -> tuple[int, int]:
    with Image.open(io.BytesIO(render_card(card))) as image:
        image.load()
        assert image.format == "PNG"
        return image.size


@pytest.mark.parametrize(
    "card",
    [
        Card(
            "平原周期",
            [
                ("地球", "白昼", "01:23:45"),
                ("扎里曼", "Grineer", "01:02:03"),
                ("双衍王境", "喜悦", "00:45:00"),
            ],
            kind="cycles",
            columns=("区域", "状态", "剩余时间"),
        ),
        Card(
            "伏特 Prime 一套",
            [("Tenno", "游戏中", "120", "2")],
            kind="market",
            columns=("玩家", "状态", "单价 / 白金", "数量"),
        ),
        Card(
            "压迫点 Prime",
            [("Tenno", "在线", "95", "1", "10")],
            kind="market",
            columns=("玩家", "状态", "单价 / 白金", "数量", "等级"),
        ),
        Card(
            "请选择物品",
            [("1", "伏特 Prime 一套")],
            kind="candidates",
            columns=("序号", "物品名称"),
        ),
        Card(
            "警报任务",
            [("Stephano(天王星)", "防御 · Grineer", "10,000 星币，Forma ×3", "13天 20:00:00")],
            kind="alerts",
            columns=("节点", "任务 / 派系", "奖励", "剩余时间"),
        ),
        Card(
            "虚空裂隙",
            [
                ("§古纪 (T1)", "", ""),
                ("O系 · 捕获", "Hepit(虚空)", "34m12s"),
            ],
            kind="fissures",
            columns=("派系 / 任务", "节点", "剩余时间"),
            stats_line="古纪 (T1) 1  ·  前纪 (T2) 2",
        ),
        Card(
            "突击任务",
            [("阶段 1", "间谍", "Earth(地球)", "敌人护甲强化")],
            kind="sortie",
            columns=("阶段", "任务类型", "节点", "状态变异"),
            highlight="Boss：Vay Hek 委员（Grineer）",
        ),
        Card(
            "执刑官猎杀",
            [("阶段 1", "破坏", "Node(星球)")],
            kind="archon",
            columns=("阶段", "任务类型", "节点"),
            highlight="执刑官：混沌蛇主（合一众）",
        ),
        Card(
            "入侵任务",
            [("Node(星球)", "Corpus\nvs Grineer", "攻：1x 蓝图\n守：1x 枪机", "38.8%")],
            kind="invasions",
            columns=("节点", "对抗阵营", "进攻 / 防守奖励", "进度"),
        ),
        Card(
            "虚空商人",
            [("Strata 中继站(地球)", "尚未到达", "11天 10:00:00")],
            kind="void_trader",
            columns=("目的地", "状态", "到达倒计时"),
            highlight="Baro Ki'Teer · 即将抵达",
        ),
        Card(
            "钢铁之路奖励",
            [("本周", "Umbra Forma 蓝图", "150 精华")],
            kind="steel_path",
            columns=("周期", "奖励内容", "消耗"),
            highlight="本周：Umbra Forma 蓝图",
        ),
        Card(
            "午夜电波",
            [("精英", "任务", "击杀 100 名敌人", "7,000")],
            kind="nightwave",
            columns=("类型", "任务名称", "任务说明", "声望"),
            highlight="第 18 季",
        ),
        Card(
            "每日特惠",
            [("爆燃喷射器", "-10%", "9 / 10", "50 / 200", "01:20:00")],
            kind="daily_deals",
            columns=("物品名称", "折扣", "现价 / 原价", "余量 / 总量", "剩余时间"),
        ),
        Card(
            "1999 日历",
            [("1月9日", "任务", "惩罚炽蛇军")],
            kind="calendar",
            columns=("日期", "类型", "内容"),
            highlight="冬季 · 第 2 次迭代",
        ),
        Card(
            "希图斯 · Ostron 赏金",
            [("取回物资", "Lv.5-15\n声望 1,290", "1,500 现金匣、Gara 机体 蓝图")],
            kind="syndicate",
            columns=("赏金任务", "等级 / 声望", "奖励池"),
        ),
        Card(
            "双衍王境轮换",
            [("普通", "Gara / Khora"), ("钢铁之路", "玻之武杖 / 拉特昂")],
            kind="duviri",
            columns=("类别", "本周可选列表"),
            highlight="当前情绪：喜悦 · 剩余 01:00:00",
        ),
        Card(
            "当前仲裁",
            [("Hydron(塞德娜)", "防御 · Grineer", "A", "00:42:10")],
            kind="arbitration",
            columns=("节点", "任务 / 派系", "评级", "剩余时间"),
        ),
        Card(
            "仲裁前瞻表",
            [("11-16 14:00", "Seimeni(谷神星)", "I系 · 防御", "S")],
            kind="arbitration_list",
            columns=("开始时间 (UTC+8)", "节点", "派系 / 任务", "评级"),
            stats_line="共筛选 1 条排期",
        ),
        Card(
            "开核桃期望推荐 (光辉)",
            [("前纪 G5", "圣装高斯 蓝图 (45p)", "9.8 白金")],
            kind="relic_value",
            columns=("遗物", "稀有金档与单价", "单车期望收益"),
        ),
        Card(
            "中英词典检索",
            [("狂暴化", "Fury", "WM 市场")],
            kind="translate",
            columns=("中文名称", "英文名称", "来源"),
        ),
        Card(
            "赤毒 / 信条武器融合计算",
            [("§25% 胚子逐次合成路线", "", ""), ("第 1 次", "25% → 27.5%", "+2.5%")],
            kind="fusion",
            columns=("次数", "合成后加成", "单次提升"),
            stats_line="胚子参考数量：25%胚×9把  ·  40%胚×5把  ·  50%胚×3把",
        ),
        Card(
            "瓦奇娅 · 圣装重生",
            [("Volt Prime 组合包", "6 御品阿耶", "当期轮换")],
            kind="varzia",
            columns=("商品 / 轮换", "消耗", "状态"),
        ),
        Card(
            "每周科研",
            [("§深层科研", "", ""), ("阶段 1", "低语 · 生存", "极限消耗")],
            kind="conquest",
            columns=("阶段", "派系 / 任务", "偏差与风险变量"),
        ),
        Card(
            "官方新闻与活动",
            [("置顶", "新版热修公告已发布", "11-16 12:00")],
            kind="news",
            columns=("类型", "标题 / 内容", "时间 / 剩余"),
        ),
        Card(
            "全局时效总览",
            [("§开放世界与周期", "", ""), ("地球昼夜", "白昼", "01:20:00")],
            kind="timings",
            columns=("项目", "当前状态", "切换 / 剩余"),
        ),
        Card(
            "遗物查询",
            [("中纪 A1 遗物", "Forma 蓝图", "Volt Prime 机体", "Volt Prime 头部")],
            kind="relics",
            columns=("遗物名称", "常见 (铜)", "罕见 (银)", "稀有 (金)"),
            highlight="关键词：Volt Prime",
        ),
        Card(
            "遗物查询帮助",
            [("按遗物名", "/遗物 中纪 A1", "精确查询")],
            kind="relic_help",
            columns=("方式", "示例指令", "说明"),
        ),
        Card(
            "Warframe 助手指令菜单",
            [("基础总览", "/时效 | /状态 | /帮助", "一图全局倒计时总览")],
            kind="help",
            columns=("分类", "指令与常用参数", "功能说明"),
        ),
        Card(
            "当前会话订阅",
            [("警报", "关键词“Forma”", "2026-11-16 02:00:00 UTC")],
            kind="subscriptions",
            columns=("类型", "过滤条件", "订阅时间"),
        ),
        Card(
            "订阅指令帮助",
            [("警报 / 入侵", "/订阅 警报 [关键词]", "按奖励或节点过滤")],
            kind="subscription_help",
            columns=("类别", "示例指令", "说明"),
        ),
        Card(
            "杜卡德金垃圾排行",
            [
                ("当天", "Volt Prime 头部神经光元", "100", "9.09", "11.0 / 42"),
                ("每小时", "Wisp Prime 蓝图", "100", "8.33", "12.0 / 18"),
            ],
            kind="ducats",
            columns=("时段", "物品名称", "杜卡德", "性价比", "均价 / 库存"),
            highlight="筛选条件：100 杜卡德币",
        ),
        Card(
            "托里德 紫卡拍卖",
            [
                (
                    "1",
                    "Torid Visi-critacan (MR14)\n+182.4% 暴击几率\n+141.0% 暴击伤害",
                    "R8 · V 槽\n12 洗",
                    "买断 1500",
                    "SellerOne\n游戏中",
                )
            ],
            kind="riven",
            columns=("序号", "紫卡与词条", "等级 / 极性", "价格 / 白金", "卖家"),
        ),
        Card(
            "赤毒 布拉玛 · 赤毒巫妖拍卖",
            [("1", "火焰 58% · 含幻纹", "买断 320", "LichTrader", "在线")],
            kind="lich_sister",
            columns=("序号", "元素 / 加成", "价格 / 白金", "卖家", "状态"),
        ),
        Card(
            "托里德 · 紫卡倾向分析",
            [
                ("暴击几率", "180%", "159.4% ～ 194.8%", "+1.6%"),
                ("变焦", "-45%", "-51% ～ -41%", "+4.3%"),
            ],
            kind="riven_analyse",
            columns=("词条", "当前数值", "理论区间", "中位偏差"),
            highlight="武器类型：步枪 · 倾向：●●●●● (1.30)",
        ),
        Card(
            "紫卡倾向分析帮助",
            [("单行格式", "/紫卡分析 托里德 +180% 暴击几率", "空格分隔武器与词条")],
            kind="riven_analyse_help",
            columns=("方式", "示例指令", "说明"),
        ),
        Card("摘要", [("项目", "内容")]),
    ],
)
def test_card_variants_render_without_system_fonts(card: Card) -> None:
    width, height = dimensions(card)
    assert width == 1080 and height > 300


def test_long_chinese_and_explicit_newlines_expand_rows() -> None:
    short = Card("标题", [("名称", "短值")])
    long = Card("标题", [("名称" * 20, "第一行\n" + "很长的中文内容" * 20)])
    assert dimensions(long)[1] > dimensions(short)[1]


def test_long_title_and_subtitle_expand_header() -> None:
    short = Card("标题", [], subtitle="副标题")
    long = Card("长标题" * 20, [], subtitle="很长的副标题文本" * 15)
    assert dimensions(long)[1] > dimensions(short)[1]


def test_empty_market_card_renders_and_preserves_text_fallback() -> None:
    card = Card(
        "压迫点 Prime",
        [],
        kind="market",
        columns=("玩家", "状态", "单价 / 白金", "数量"),
        empty_message="暂无符合条件的在线订单",
        highlight="测试高亮",
    )
    assert dimensions(card)[0] == 1080
    assert card.empty_message in card.text()
    assert "测试高亮" in card.text()
    assert "玩家 · 状态 · 单价 / 白金 · 数量" in card.text()


def test_render_source_contains_no_old_branding() -> None:
    from pathlib import Path

    render_src = (Path(__file__).resolve().parents[1] / "milo_core" / "render.py").read_text(
        encoding="utf-8"
    )
    assert "nyxbot" not in render_src.casefold()
    assert "maibot" not in render_src.casefold()
    assert "麦麦" not in render_src
    assert "nyx /" not in render_src.casefold()
    assert "Warframe × Milo bot" in render_src


def test_mismatched_columns_fail_instead_of_omitting_values() -> None:
    with pytest.raises(ValueError, match="列"):
        render_card(Card("标题", [("名称", "内容", "额外数据")], columns=("名称", "内容")))


def test_missing_explicit_font_path_raises_value_error() -> None:
    with pytest.raises(ValueError, match="font_path"):
        render_card(Card("标题", []), font_path="missing-cjk-font.ttf")
