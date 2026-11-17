"""Render every card with the local Phase Transition stationery theme."""

from __future__ import annotations

import io
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .card_model import Card

ASSETS = Path(__file__).resolve().parents[1] / "assets"
WIDTH = 1080
PAD = 44
INNER = WIDTH - PAD * 2
BLUE = "#236787"
INK = "#294554"
PURPLE = "#8862AA"
MUTED = "#7A8990"
LINE = "#D9E4E6"
GREEN = "#42866D"
GOLD = "#A37D36"
AMBER = "#B27639"
RED = "#A64949"

_PROPORTIONS: dict[tuple[str, int], tuple[float, ...]] = {
    ("cycles", 3): (0.37, 0.25, 0.38),
    ("market", 4): (0.42, 0.18, 0.24, 0.16),
    ("market", 5): (0.36, 0.17, 0.21, 0.13, 0.13),
    ("candidates", 2): (0.13, 0.87),
    ("alerts", 4): (0.25, 0.23, 0.32, 0.20),
    ("fissures", 4): (0.12, 0.39, 0.29, 0.20),
    ("fissures", 3): (0.31, 0.49, 0.20),
    ("sortie", 4): (0.14, 0.17, 0.33, 0.36),
    ("archon", 3): (0.16, 0.26, 0.58),
    ("invasions", 4): (0.26, 0.20, 0.40, 0.14),
    ("void_trader", 3): (0.50, 0.20, 0.30),
    ("steel_path", 3): (0.20, 0.58, 0.22),
    ("nightwave", 4): (0.12, 0.25, 0.49, 0.14),
    ("daily_deals", 5): (0.32, 0.12, 0.20, 0.16, 0.20),
    ("calendar", 3): (0.16, 0.13, 0.71),
    ("syndicate", 3): (0.30, 0.22, 0.48),
    ("duviri", 2): (0.22, 0.78),
    ("arbitration", 4): (0.37, 0.29, 0.12, 0.22),
    ("arbitration_list", 4): (0.24, 0.38, 0.27, 0.11),
    ("relics", 4): (0.22, 0.28, 0.26, 0.24),
    ("relic_help", 3): (0.16, 0.34, 0.50),
    ("subscriptions", 3): (0.18, 0.44, 0.38),
    ("subscription_help", 3): (0.20, 0.40, 0.40),
    ("ducats", 5): (0.13, 0.37, 0.13, 0.16, 0.21),
    ("riven", 5): (0.06, 0.41, 0.16, 0.18, 0.19),
    ("lich_sister", 5): (0.08, 0.31, 0.19, 0.27, 0.15),
    ("riven_analyse", 4): (0.22, 0.18, 0.41, 0.19),
    ("riven_analyse_help", 3): (0.16, 0.48, 0.36),
    ("relic_value", 3): (0.22, 0.56, 0.22),
    ("translate", 3): (0.22, 0.39, 0.39),
    ("fusion", 3): (0.26, 0.24, 0.50),
    ("varzia", 3): (0.50, 0.24, 0.26),
    ("conquest", 3): (0.16, 0.30, 0.54),
    ("news", 3): (0.20, 0.58, 0.22),
    ("timings", 3): (0.24, 0.48, 0.28),
    ("help", 3): (0.16, 0.46, 0.38),
}

_CENTER_COLS: dict[str, set[int]] = {
    "cycles": {1, 2},
    "market": {1, 2, 3, 4},
    "candidates": {0},
    "alerts": {3},
    "fissures": {0, 2, 3},
    "sortie": {0},
    "archon": {0},
    "invasions": {3},
    "void_trader": {1, 2},
    "steel_path": {0, 2},
    "nightwave": {0, 3},
    "daily_deals": {1, 2, 3, 4},
    "calendar": {1},
    "syndicate": {1},
    "duviri": {0},
    "arbitration": {2, 3},
    "arbitration_list": {0, 3},
    "relics": set(),
    "relic_help": {0},
    "subscriptions": {0, 2},
    "subscription_help": {0},
    "ducats": {0, 2, 3, 4},
    "riven": {0, 2, 3},
    "lich_sister": {0, 2, 4},
    "riven_analyse": {1, 2, 3},
    "riven_analyse_help": {0},
    "relic_value": {2},
    "translate": {0},
    "fusion": {0, 1},
    "varzia": {1, 2},
    "conquest": {0},
    "news": {0, 2},
    "timings": {0, 2},
    "help": {0},
    "summary": set(),
}

_PILL_COLS: dict[str, set[int]] = {
    "cycles": {1},
    "market": {1, 4},
    "candidates": {0},
    "fissures": {0},
    "sortie": {0},
    "archon": {0},
    "steel_path": {0},
    "nightwave": {0},
    "calendar": {1},
    "duviri": {0},
    "arbitration": {2},
    "arbitration_list": {3},
    "relic_help": {0},
    "subscriptions": {0},
    "subscription_help": {0},
    "ducats": {0},
    "riven": {0},
    "lich_sister": {0, 4},
    "riven_analyse": {3},
    "riven_analyse_help": {0},
    "translate": {0},
    "fusion": {0},
    "conquest": {0},
    "news": {0},
    "timings": {0},
    "help": {0},
}

_NUMBER_COLS: dict[str, set[int]] = {
    "cycles": {2},
    "market": {2},
    "alerts": {3},
    "fissures": {2, 3},
    "invasions": {3},
    "void_trader": {1, 2},
    "steel_path": {2},
    "nightwave": {3},
    "daily_deals": {1, 2},
    "arbitration": {3},
    "ducats": {3},
    "riven": {3},
    "lich_sister": {2},
    "riven_analyse": {1},
    "relic_value": {2, 3},
    "fusion": {1},
    "varzia": {1},
    "timings": {2},
}

_PILL_TEXT_COLORS: dict[str, str] = {
    "白昼": GOLD,
    "夜晚": PURPLE,
    "温暖": AMBER,
    "寒冷": BLUE,
    "FASS": GREEN,
    "VOME": PURPLE,
    "Corpus": BLUE,
    "Grineer": RED,
    "悲伤": BLUE,
    "恐惧": PURPLE,
    "喜悦": GOLD,
    "愤怒": RED,
    "嫉妒": GREEN,
    "游戏中": GREEN,
    "在线": BLUE,
    "古纪": AMBER,
    "前纪": GOLD,
    "中纪": INK,
    "后纪": PURPLE,
    "安魂": RED,
    "全能": GREEN,
    "每日": AMBER,
    "每周": BLUE,
    "精英": PURPLE,
    "普通": INK,
    "钢铁之路": RED,
    "任务": RED,
    "奖励": GREEN,
    "加成": GOLD,
    "本周": PURPLE,
    "下周": BLUE,
    "常驻": INK,
    "S": GOLD,
    "A": PURPLE,
    "B": BLUE,
    "C": GREEN,
    "D": MUTED,
    "F": MUTED,
    "尚未到达": AMBER,
    "营业中": GREEN,
    "警报": RED,
    "裂缝": PURPLE,
    "突击": BLUE,
    "执刑官猎杀": RED,
    "入侵": AMBER,
    "虚空商人": GOLD,
    "平原周期": GREEN,
    "仲裁": PURPLE,
    "当天": BLUE,
    "每小时": AMBER,
}

_FACTION_PREFIX_COLORS: tuple[tuple[str, str], ...] = (
    ("G系", RED),
    ("C系", BLUE),
    ("I系", GREEN),
    ("O系", GOLD),
    ("低语", PURPLE),
    ("合一", PURPLE),
    ("炽蛇", AMBER),
    ("科腐", GREEN),
)

_FOOTER_NOTES: dict[str, str] = {
    "cycles": "周期与剩余时间均为本次查询快照",
    "market": "仅显示符合筛选条件的在线订单 · 可用 /w 序号 生成私聊",
    "candidates": "候选编号只在当前会话内有效",
    "arbitration": "仲裁排期来自 browse.wf 公共数据",
    "arbitration_list": "按 Tier 筛选未来 30 天内 S/A/B 级推荐节点（支持 -页码 翻页）",
    "fissures": "按虚空纪元分组展示，支持关键词筛选与 -页码 翻页",
    "relics": "遗物数据来自官方 PublicExport（已过滤机密条目）",
    "relic_value": "参考掉落期望按 WM 近 48 小时奸商加权均价计算（白金仅作估价参考）",
    "translate": "词条来自官方 PublicExport 与本地词库双向匹配",
    "fusion": "按单次最高 +10% 合成规则估算所需武器数量",
    "varzia": "来自 Warframe 官方 worldState 瓦奇娅轮换排期",
    "conquest": "来自 Warframe 官方 worldState 每周科研任务与惩罚",
    "news": "来自 Warframe 官方公告与活动流（已按时间倒序）",
    "timings": "整合地球/夜灵/福图纳/魔胎之境/双衍王境/突击/虚空商人实时节点",
    "help": (
        "所有指令附加 -1 或 -w 返回纯文本；多页列表附加 -2 翻页；可直接在对话中向 Milo bot 提问"
    ),
    "subscriptions": "可使用 /退订 <类型|全部> 管理本会话推送规则",
    "subscription_help": "同一会话再次订阅相同类型将更新该类型的过滤条件",
    "ducats": "按加权均价性价比降序展示，支持 -页码 翻页与 /铜垃圾 筛选",
    "riven": "仅展示在线玩家的 PC/跨平台紫卡拍卖 · 2 分钟内可用 /w 序号 获取私聊语句",
    "lich_sister": "仅展示在线玩家的 PC/跨平台玄骸拍卖 · 2 分钟内可用 /w 序号 获取私聊语句",
    "riven_analyse": "数值区间与中位差按官方武器倾向（Omega）计算",
    "riven_analyse_help": "纯本地文本倾向分析，无需上传截图或 OCR 模型",
}


@dataclass(frozen=True)
class _Fonts:
    title: ImageFont.FreeTypeFont
    body: ImageFont.FreeTypeFont
    small: ImageFont.FreeTypeFont
    header: ImageFont.FreeTypeFont
    emphasis: ImageFont.FreeTypeFont


@dataclass(frozen=True)
class _Row:
    lines: list[list[str]]
    height: int
    is_group: bool = False
    gauge: float | None = None


@dataclass(frozen=True)
class _Layout:
    columns: tuple[str, ...]
    widths: list[int]
    rows: list[_Row]
    title: list[str]
    item: list[str]
    subtitle: list[str]
    stats_lines: list[str]
    table_y: int
    height: int


@lru_cache(maxsize=4)
def _read_font_bytes(resolved_path: str) -> bytes:
    return Path(resolved_path).read_bytes()


def _font(path: str, size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    name = "MiSans-Demibold.ttf" if bold else "MiSans-Regular.ttf"
    resolved = path or str(ASSETS / name)
    try:
        return ImageFont.truetype(io.BytesIO(_read_font_bytes(resolved)), size)
    except OSError as exc:
        raise ValueError(
            f"无法读取中文字体，请检查 font_path 或插件 assets 目录：{path or name}"
        ) from exc


def _wrap(text: str, font: ImageFont.FreeTypeFont, width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.split("\n"):
        current = ""
        for char in paragraph:
            if current and font.getlength(current + char) > width:
                lines.append(current.rstrip())
                current = char.lstrip()
            else:
                current += char
        lines.append(current.rstrip())
    return lines


def _column_widths(kind: str, count: int) -> list[int]:
    proportions = _PROPORTIONS.get((kind, count))
    if proportions is None:
        proportions = (
            (1.0,) if count == 1 else (0.36, *(0.64 / (count - 1) for _ in range(count - 1)))
        )
    widths = [int(INNER * value) for value in proportions]
    widths[-1] = INNER - sum(widths[:-1])
    return widths


def _parse_gauge(card_kind: str, row: tuple[str, ...]) -> float | None:
    if card_kind != "riven_analyse" or len(row) <= 3:
        return None
    diff_text = row[3].strip()
    if diff_text == "均值":
        return 0.0
    if not diff_text.endswith("%"):
        return None
    try:
        value = float(diff_text[:-1].replace("+", ""))
    except ValueError:
        return None
    return max(-1.0, min(1.0, value / 12.0))


def _build_row(card: Card, row: tuple[str, ...], widths: list[int], fonts: _Fonts) -> _Row:
    if row and row[0].startswith("§"):
        return _Row([[row[0].lstrip("§").strip()]], 48, is_group=True)
    cells = [
        _wrap(
            text,
            fonts.emphasis if _cell_style(card.kind, index, text)[0] == "number" else fonts.body,
            width - 40,
        )
        for index, (text, width) in enumerate(zip(row, widths, strict=True))
    ]
    gauge = _parse_gauge(card.kind, row)
    minimum = 84 if gauge is not None else (90 if card.kind == "cycles" else 68)
    row_height = max(minimum, max(map(len, cells)) * 38 + (36 if gauge is not None else 28))
    return _Row(cells, row_height, gauge=gauge)


def _prepare(card: Card, fonts: _Fonts) -> _Layout:
    count = len(card.columns) or (len(card.rows[0]) if card.rows else 2)
    if count < 1 or any(len(row) != count for row in card.rows):
        raise ValueError("卡片的列名数量与数据列数量不一致。")
    columns = card.columns or (
        ("项目", "内容") if count == 2 else tuple(f"信息 {i + 1}" for i in range(count))
    )
    widths = _column_widths(card.kind, count)
    titles = {"market": "市场订单", "candidates": "物品检索"}
    title = _wrap(titles.get(card.kind, card.title), fonts.title, INNER - 120)
    banner = card.title if card.kind == "market" else card.highlight
    item = _wrap(banner, fonts.emphasis, INNER - 52) if banner else []
    subtitle = _wrap(card.subtitle, fonts.small, INNER - 40) if card.subtitle else []
    stats_lines = _wrap(card.stats_line, fonts.small, INNER - 48) if card.stats_line else []
    stats_block = (len(stats_lines) * 28 + 26) if stats_lines else 0
    table_y = 100 + len(title) * 52 + 36 + len(item) * 44 + len(subtitle) * 28
    prepared = [_build_row(card, row, widths, fonts) for row in card.rows]
    body_height = sum(row.height for row in prepared) if prepared else 210
    return _Layout(
        columns,
        widths,
        prepared,
        title,
        item,
        subtitle,
        stats_lines,
        table_y,
        table_y + 54 + body_height + stats_block + 142,
    )


@lru_cache(maxsize=16)
def _asset(name: str, size: tuple[int, int], opacity: float = 1.0) -> Image.Image:
    with Image.open(ASSETS / name) as original:
        image = original.convert("RGBA").resize(size, Image.Resampling.LANCZOS)
    if opacity != 1.0:
        image.putalpha(image.getchannel("A").point(lambda alpha: int(alpha * opacity)))
    image.load()
    return image


@lru_cache(maxsize=4)
def _paper_bg(name: str) -> Image.Image:
    with Image.open(ASSETS / name) as original:
        bg = original.convert("RGB")
    bg.load()
    return bg


def _paper(kind: str, height: int) -> Image.Image:
    name = {"cycles": "bg-cycles.png", "candidates": "bg-candidates.png"}.get(kind, "bg-table.png")
    background = _paper_bg(name).resize((WIDTH, height), Image.Resampling.LANCZOS)
    image = Image.blend(Image.new("RGB", (WIDTH, height), "#FDFEFC"), background, 0.30)
    motif = _asset("motif.png", (285, 292), 0.25)
    image.paste(motif, (WIDTH - 320, 28), motif)
    return image


def _header(image: Image.Image, layout: _Layout, fonts: _Fonts) -> None:
    draw = ImageDraw.Draw(image)
    draw.text((PAD, 31), "WARFRAME NOTES", font=fonts.small, fill=INK, anchor="lt")
    ribbon = _asset("ribbon.png", (142, 31))
    image.paste(ribbon, (WIDTH - PAD - 142, 26), ribbon)
    draw.text((WIDTH - PAD - 76, 41), "PC 国际服", font=fonts.small, fill=INK, anchor="mm")
    y = 91
    for number, line in enumerate(layout.title):
        text_width = int(fonts.title.getlength(line))
        x = (WIDTH - text_width) // 2
        if number == 0:
            icon = _asset("topic.png", (36, 36))
            image.paste(icon, (x - 54, y + 2), icon)
        draw.text((x, y), line, font=fonts.title, fill=BLUE, anchor="lt")
        y += 52
    y += 13
    draw.line((PAD, y, WIDTH - PAD, y), fill=LINE, width=2)
    draw.line((PAD, y, PAD + 88, y), fill="#BBDC39", width=3)
    y += 22
    if layout.item:
        marker = _asset("triangle.png", (16, 16))
        image.paste(marker, (PAD + 4, y + 10), marker)
        for line in layout.item:
            draw.text((PAD + 32, y), line, font=fonts.emphasis, fill=PURPLE, anchor="lt")
            y += 44
    for line in layout.subtitle:
        draw.text((PAD + 2, y + 2), line, font=fonts.small, fill=MUTED, anchor="lt")
        y += 28


def _cell_style(kind: str, index: int, text: str) -> tuple[str, str]:
    if kind == "riven_analyse" and index == 3:
        color = RED if text.startswith("-") else (GREEN if text.startswith("+") else MUTED)
        return "pill", color
    if index in _PILL_COLS.get(kind, set()):
        for prefix, color in _FACTION_PREFIX_COLORS:
            if text.startswith(prefix):
                return "pill", color
        return "pill", _PILL_TEXT_COLORS.get(text, BLUE)
    if kind == "void_trader" and index == 1 and text in _PILL_TEXT_COLORS:
        return "pill", _PILL_TEXT_COLORS[text]
    if index in _NUMBER_COLS.get(kind, set()):
        return "number", PURPLE
    return "text", BLUE if index == 0 or kind == "candidates" else INK


def _draw_riven_gauge(
    draw: ImageDraw.ImageDraw,
    bounds: tuple[int, int, int, int],
    offset: float,
) -> None:
    x, y, width, height = bounds
    cx = x + width // 2
    gy = y + height - 15
    half = min(56, max(28, width // 2 - 22))
    draw.line((cx - half, gy, cx + half, gy), fill=LINE, width=3)
    draw.line((cx, gy - 5, cx, gy + 5), fill=MUTED, width=2)
    dx = int(offset * (half - 4))
    dot_color = GREEN if offset > 0 else (RED if offset < 0 else MUTED)
    draw.ellipse((cx + dx - 5, gy - 5, cx + dx + 5, gy + 5), fill=dot_color)


@dataclass(frozen=True)
class _CellOptions:
    role: str
    color: str
    left: bool
    gauge: float | None = None


def _draw_cell(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    bounds: tuple[int, int, int, int],
    fonts: _Fonts,
    options: _CellOptions,
) -> None:
    x, y, width, height = bounds
    role, color, left, gauge = options.role, options.color, options.left, options.gauge
    font = fonts.emphasis if role == "number" else fonts.body
    if role == "pill" and len(lines) == 1:
        text = lines[0]
        pill_width = min(width - 28, int(fonts.small.getlength(text)) + 36)
        cx = x + width // 2
        cy = y + (height - 16 if gauge is not None else height) // 2
        draw.rounded_rectangle(
            (cx - pill_width // 2, cy - 18, cx + pill_width // 2, cy + 18),
            radius=18,
            fill="#F1F6F3",
            outline=LINE,
            width=1,
        )
        draw.text((cx, cy), text, font=fonts.small, fill=color, anchor="mm")
        if gauge is not None:
            _draw_riven_gauge(draw, bounds, gauge)
        return
    top = y + (height - len(lines) * 38) // 2 + 4
    for line in lines:
        draw.text(
            (x + 20 if left else x + width // 2, top),
            line,
            font=font,
            fill=color,
            anchor="lt" if left else "mt",
        )
        top += 38


def _left_aligned(kind: str, index: int) -> bool:
    return index not in _CENTER_COLS.get(kind, set())


def _draw_group_band(
    draw: ImageDraw.ImageDraw,
    label: str,
    y: int,
    height: int,
    fonts: _Fonts,
) -> None:
    draw.rectangle((PAD + 3, y, WIDTH - PAD - 3, y + height), fill="#EDF4F6")
    draw.rectangle((PAD + 3, y + 6, PAD + 7, y + height - 6), fill=BLUE)
    draw.text((PAD + 20, y + height // 2), label, font=fonts.header, fill=BLUE, anchor="lm")


def _table(image: Image.Image, card: Card, layout: _Layout, fonts: _Fonts) -> int:
    draw = ImageDraw.Draw(image)
    y = layout.table_y
    body = sum(row.height for row in layout.rows) if layout.rows else 210
    draw.rounded_rectangle(
        (PAD, y, WIDTH - PAD, y + 54 + body), radius=16, fill="#FFFFFF", outline=LINE, width=2
    )
    draw.rounded_rectangle((PAD + 1, y + 1, WIDTH - PAD - 1, y + 54), radius=15, fill="#EDF5F5")
    x = PAD
    for index, (label, width) in enumerate(zip(layout.columns, layout.widths, strict=True)):
        left = _left_aligned(card.kind, index)
        draw.text(
            (x + 20 if left else x + width // 2, y + 27),
            label,
            font=fonts.header,
            fill=BLUE,
            anchor="lm" if left else "mm",
        )
        x += width
    y += 54
    if not layout.rows:
        _empty(image, card.empty_message, y, fonts)
        return y + body
    stripe = 0
    for row_number, row in enumerate(layout.rows):
        if row.is_group:
            _draw_group_band(draw, row.lines[0][0], y, row.height, fonts)
            stripe = 0
        else:
            if stripe % 2:
                bounds = (PAD + 2, y, WIDTH - PAD - 2, y + row.height - 2)
                draw.rounded_rectangle(bounds, radius=14, fill="#F8FBFA")
                draw.rectangle((PAD + 2, y, WIDTH - PAD - 2, y + row.height - 16), fill="#F8FBFA")
            stripe += 1
            x = PAD
            for index, (lines, width) in enumerate(zip(row.lines, layout.widths, strict=True)):
                role, color = _cell_style(card.kind, index, " ".join(lines))
                _draw_cell(
                    draw,
                    lines,
                    (x, y, width, row.height),
                    fonts,
                    _CellOptions(
                        role,
                        color,
                        _left_aligned(card.kind, index),
                        row.gauge if index == 3 else None,
                    ),
                )
                x += width
        y += row.height
        if row_number < len(layout.rows) - 1:
            draw.line((PAD + 18, y, WIDTH - PAD - 18, y), fill=LINE, width=1)
    return y


def _empty(image: Image.Image, message: str, y: int, fonts: _Fonts) -> None:
    draw = ImageDraw.Draw(image)
    icon = _asset("topic.png", (46, 46), 0.7)
    image.paste(icon, ((WIDTH - 46) // 2, y + 36), icon)
    draw.text((WIDTH // 2, y + 105), message, font=fonts.body, fill=BLUE, anchor="mt")
    draw.text(
        (WIDTH // 2, y + 151),
        "可以稍后重试，或调整查询条件",
        font=fonts.small,
        fill=MUTED,
        anchor="mt",
    )


def _footer(
    image: Image.Image,
    card: Card,
    layout: _Layout,
    bottom: int,
    fonts: _Fonts,
) -> None:
    draw = ImageDraw.Draw(image)
    note_y = bottom + 23
    if layout.stats_lines:
        box_top = bottom + 14
        box_bottom = box_top + len(layout.stats_lines) * 28 + 16
        draw.rounded_rectangle(
            (PAD, box_top, WIDTH - PAD, box_bottom),
            radius=12,
            fill="#F1F6F3",
            outline=LINE,
            width=1,
        )
        line_y = box_top + 10
        for line in layout.stats_lines:
            draw.text((PAD + 18, line_y), line, font=fonts.small, fill=BLUE, anchor="lt")
            line_y += 28
        note_y = box_bottom + 14
    note = card.footer_note or _FOOTER_NOTES.get(card.kind, "Warframe 数据查询")
    draw.text(
        (PAD + 2, note_y),
        note,
        font=fonts.small,
        fill=MUTED,
        anchor="lt",
    )
    y = image.height - 55
    draw.line((PAD, y - 15, WIDTH - PAD, y - 15), fill=LINE, width=1)
    draw.text((PAD, y + 3), "Warframe × Milo bot", font=fonts.small, fill=BLUE, anchor="lt")
    marker = _asset("triangle.png", (15, 15))
    image.paste(marker, (WIDTH - PAD - 15, y + 5), marker)
    draw.text((WIDTH - PAD - 31, y + 3), "WARFRAME / PC", font=fonts.small, fill=MUTED, anchor="rt")


def render_card(card: Card, *, font_path: str = "") -> bytes:
    """Render structured table, candidate and empty cards with one shared theme.

    Only the backgrounds, geometric decorations and MiSans fonts explicitly
    selected from the user's local material folder are used.
    """
    fonts = _Fonts(
        _font(font_path, 40, bold=True),
        _font(font_path, 28),
        _font(font_path, 20),
        _font(font_path, 21, bold=True),
        _font(font_path, 32, bold=True),
    )
    layout = _prepare(card, fonts)
    image = _paper(card.kind, layout.height)
    _header(image, layout, fonts)
    bottom = _table(image, card, layout, fonts)
    _footer(image, card, layout, bottom, fonts)
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()
