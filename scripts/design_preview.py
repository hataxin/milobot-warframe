"""Render candidate and empty-state design fixtures without network or chat."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from milo_core.card_model import Card  # noqa: E402
from milo_core.render import render_card  # noqa: E402


def main() -> None:
    """Save clearly labeled sample cards, including long text stress cases."""
    output = ROOT / "artifacts"
    output.mkdir(exist_ok=True)
    cards = {
        "candidates": Card(
            "请选择物品",
            [
                ("1", "伏特 Prime 一套"),
                ("2", "伏特 Prime 蓝图"),
                ("3", "伏特 Prime 机体蓝图"),
                ("4", "伏特 Prime 神经光元蓝图"),
                ("5", "Volt Prime Systems Blueprint"),
            ],
            "排版演示数据 · 60 秒内在当前会话回复 /wm 编号",
            columns=("序号", "物品名称"),
            kind="candidates",
        ),
        "empty": Card(
            "压迫点 Prime",
            [],
            "排版演示数据 · PC · 买家 · 满级",
            columns=("玩家", "状态", "单价 / 白金", "数量", "等级"),
            kind="market",
            empty_message="暂无符合条件的在线订单",
        ),
        "long-text": Card(
            "长文本排版检查",
            [
                ("长名称与换行", "这是一段用于检查中文自动换行的演示文本。" * 7),
                ("英文名称", "A-Long-Warframe-Player-Name-For-Layout-Preview"),
                ("显式换行", "第一行\n第二行"),
            ],
            "排版演示数据 · 不代表新增查询功能",
            columns=("项目", "内容"),
        ),
        "subscriptions": Card(
            "当前会话订阅",
            [
                ("警报", "关键词“奥罗金”", "2026-11-16 03:00:00 UTC"),
                ("裂缝", "钢铁 · 后纪 · 捕获/虚空覆涌", "2026-11-16 03:05:00 UTC"),
                ("平原周期", "夜灵平原 · 夜晚", "2026-11-16 03:06:00 UTC"),
            ],
            "国际服 PC · 后台自动检测变更并推送到本会话",
            columns=("类型", "过滤条件", "订阅时间"),
            kind="subscriptions",
        ),
        "subscription-help": Card(
            "订阅指令帮助",
            [
                ("警报 / 入侵", "/订阅 警报 [关键词]", "按奖励或节点过滤（如 反应堆 / Forma）"),
                (
                    "裂缝 / 风暴",
                    "/订阅 裂缝 [钢铁|九重天] [纪元] [任务]",
                    "支持组合过滤（如 钢铁 后纪 捕获）",
                ),
                (
                    "平原周期",
                    "/订阅 平原 [区域] [状态]",
                    "默认监控夜灵平原，支持 地球/双衍/扎里曼/全部",
                ),
                ("管理订阅", "/订阅列表 | /退订 <类型|全部>", "查看本会话规则或退订"),
            ],
            "国际服 PC · 同一会话对同类型重复订阅会覆盖更新条件",
            columns=("类别", "示例指令", "说明"),
            kind="subscription_help",
        ),
        "ducats": Card(
            "杜卡德金垃圾排行",
            [
                ("当天", "Volt Prime 头部神经光元", "100", "9.09", "11.0 / 42"),
                ("当天", "Mirage Prime 蓝图", "100", "8.70", "11.5 / 31"),
                ("每小时", "Wisp Prime 蓝图", "100", "8.33", "12.0 / 18"),
            ],
            "国际服 PC · 排版演示数据",
            columns=("时段", "物品名称", "杜卡德", "性价比", "均价 / 库存"),
            kind="ducats",
            highlight="筛选条件：100 杜卡德币",
        ),
        "riven": Card(
            "托里德 紫卡拍卖",
            [
                (
                    "1",
                    "Torid Visi-critacan (MR14)\n+182.4% 暴击几率\n+141.0% 暴击伤害\n-45.2% 变焦",
                    "R8·V槽\n12 洗",
                    "买断 1500",
                    "TennoTrader\n游戏中",
                ),
                (
                    "2",
                    "Torid Sati-acricron (MR11)\n+112.0% 多重射击\n+165.5% 暴击伤害",
                    "R0·D槽\n0 洗",
                    "起拍 1200\n当前 1350",
                    "RivenMaster\n在线",
                ),
            ],
            "国际服 PC · 正面：爆率,爆伤 · 负面：无",
            columns=("序号", "紫卡与词条", "等级 / 极性", "价格 / 白金", "卖家"),
            kind="riven",
        ),
        "lich": Card(
            "赤毒 布拉玛 · 赤毒巫妖拍卖",
            [
                ("1", "火焰 58% · 含幻纹", "买断 320", "KuvaDealer", "游戏中"),
                ("2", "毒素 55%", "买断 240", "CrossTenno", "在线"),
            ],
            "国际服 PC · 排版演示数据",
            columns=("序号", "元素 / 加成", "价格 / 白金", "卖家", "状态"),
            kind="lich_sister",
        ),
        "fissures-v060": Card(
            "虚空裂隙",
            [
                ("§古纪 (T1)", "", ""),
                ("O系 · 捕获", "Hepit(虚空)", "12m34s"),
                ("G系 · 歼灭", "Mariana(地球)", "28m10s"),
                ("§后纪 (T4)", "", ""),
                ("C系 · 拦截", "Berehynia(塞德娜)", "41m05s"),
            ],
            "国际服 PC · 第 1/2 页（加 -2 翻页）",
            columns=("派系 / 任务", "节点", "剩余时间"),
            kind="fissures",
            stats_line="古纪 (T1) 2  ·  前纪 (T2) 3  ·  中纪 (T3) 2  ·  后纪 (T4) 1",
        ),
        "market-stats": Card(
            "伏特 Prime 一套",
            [
                ("TennoTrader", "游戏中", "92", "1"),
                ("VoidSeller", "在线", "95", "2"),
            ],
            "PC · 卖家 · 价格从低到高",
            columns=("玩家", "状态", "单价 / 白金", "数量"),
            kind="market",
            stats_line=(
                "48h：均价 92.4p (85~102p · 成交 148)  |  "
                "90d：均价 95.8p (80~118p · 成交 4120)\n"
                "快捷私聊 /w 1：/w TennoTrader Hi! I want to buy Volt Prime Set for 92p."
            ),
        ),
        "timings-v060": Card(
            "全局时效总览",
            [
                ("§开放世界与周期", "", ""),
                ("地球", "白昼", "01:12:45"),
                ("夜灵平原", "夜晚", "00:31:20"),
                ("奥布山谷", "温暖", "00:05:10"),
                ("双衍王境", "喜悦", "01:14:00"),
                ("§日常与轮换节点", "", ""),
                ("每日突击", "进行中", "6h12m"),
                ("虚空商人", "营业中", "1d 08h"),
                ("当前仲裁", "Hydron [A] G系 · 防御", "42m10s"),
            ],
            "国际服 PC · 排版演示数据",
            columns=("项目", "当前状态", "切换 / 剩余"),
            kind="timings",
        ),
        "fusion-v060": Card(
            "赤毒 / 信条武器融合计算",
            [
                ("§25% 胚子逐次合成路线", "", ""),
                ("第 1 次", "38.5% → 42.4%", "+3.9%"),
                ("第 2 次", "42.4% → 46.6%", "+4.2%"),
                ("第 3 次", "46.6% → 51.3%", "+4.7%"),
                ("第 4 次", "51.3% → 56.4%", "+5.1%"),
                ("第 5 次", "56.4% → 60%", "+3.6%"),
            ],
            "国际服 PC · 排版演示数据",
            columns=("次数", "合成后加成", "单次提升"),
            kind="fusion",
            highlight="从 38.5% 升至 60% 预计所需胚子数量",
            stats_line="胚子参考数量：25%胚×5把  ·  40%胚×4把  ·  50%胚×2把",
        ),
    }
    for name, card in cards.items():
        path = output / f"{name}.png"
        path.write_bytes(render_card(card))
        print(f"Rendered {name}: {path}")


if __name__ == "__main__":
    main()
