"""Riven, Kuva Lich, and Tenet Sister auction search, filtering, and Card builders."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

from .card_model import Card
from .command_flags import page_caption, paginate
from .dictionary import RivenStatInfo, RivenTrendEntry, WeaponMeta
from .errors import QueryError
from .market import Item, normalize
from .riven_analyse import compute_diff, compute_low_high, lookup_trend_optional, select_base_value
from .whisper import WhisperEntry, element_label, lich_whisper, riven_whisper
from .worldstate import QueryMeta, subtitle

_RIVEN_POLARITIES: dict[str, str] = {
    "madurai": "V槽",
    "vazarin": "D槽",
    "naramon": "—槽",
    "zenurik": "=槽",
}

_STATUS_LABELS: dict[str, str] = {
    "ingame": "游戏中",
    "online": "在线",
}

_POLARITY_TOKENS: dict[str, str] = {
    "v": "madurai",
    "v槽": "madurai",
    "d": "vazarin",
    "d槽": "vazarin",
    "—槽": "naramon",
    "-槽": "naramon",
    "n槽": "naramon",
    "=槽": "zenurik",
    "z槽": "zenurik",
}

_REROLL_TOKENS: dict[str, str] = {
    "零洗": "zero",
    "0洗": "zero",
    "低洗": "low",
    "废洗": "trash",
}

_STAT_COUNT_TOKENS: set[str] = {"2+", "2+1", "3+", "3+1"}

_SLANG_HINTS: dict[str, str] = {
    "基伤": "base_damage_/_melee_damage",
    "伤害": "base_damage_/_melee_damage",
    "爆率": "critical_chance",
    "暴率": "critical_chance",
    "爆伤": "critical_damage",
    "暴伤": "critical_damage",
    "多重": "multishot",
    "多射": "multishot",
    "射速": "fire_rate_/_attack_speed",
    "攻速": "fire_rate_/_attack_speed",
    "g伤": "damage_vs_grineer",
    "c伤": "damage_vs_corpus",
    "i伤": "damage_vs_infested",
    "触发": "status_chance",
    "触率": "status_chance",
    "触时": "status_duration",
    "装填": "reload_speed",
    "弹匣": "magazine_capacity",
    "弹药": "ammo_maximum",
    "范围": "range",
    "穿透": "punch_through",
    "后坐": "recoil",
    "后座": "recoil",
    "变焦": "zoom",
    "冰伤": "cold_damage",
    "火伤": "heat_damage",
    "毒伤": "toxin_damage",
    "电伤": "electric_damage",
    "滑暴": "critical_chance_on_slide_attack",
    "重击效率": "heavy_attack_efficiency",
    "初始连击": "initial_combo",
    "连击时间": "combo_duration",
}


@dataclass(frozen=True)
class RivenDisplayOptions:
    """Optional filtering, Omega badge lookup and pagination parameters for `/wr`."""

    filters: RivenQuery | None = None
    weapon_meta: WeaponMeta | None = None
    trends: dict[str, RivenTrendEntry] | None = None
    page: int = 1
    page_size: int = 8


@dataclass(frozen=True)
class RivenQuery:
    """Parsed `/wr` command query including weapon, stat filters and local filters."""

    weapon: str
    positive: str = ""
    negative: str = ""
    reroll: str = ""
    polarity: str = ""
    stat_count: str = ""
    max_price: int | None = None


def split_riven_args(text: str) -> tuple[str, str, str]:
    """Split `/wr` args into `(weapon_keyword, positive_stats, negative_stat)`."""
    normalized = " ".join(text.split())
    if not normalized:
        return "", "", ""
    tokens = normalized.split(" ")
    pos, neg = "", ""
    index = len(tokens) - 1
    while index >= 1:
        token = tokens[index]
        if not neg and token in {"有", "无"}:
            neg = token
        elif not pos and "-" not in token and ("," in token or "，" in token):
            pos = token
        else:
            break
        index -= 1
    weapon_part = " ".join(tokens[: index + 1])
    if not pos and not neg and "-" in weapon_part:
        prefix = weapon_part[:4] if weapon_part[:4].upper() == "MK1-" else ""
        body = weapon_part[len(prefix) :]
        if "-" in body:
            parts = [part.strip() for part in body.split("-")]
            weapon_part = prefix + parts[0]
            pos = parts[1] if len(parts) >= 2 else ""
            neg = parts[2] if len(parts) >= 3 else ""
    return weapon_part.strip(), pos.strip(), neg.strip()


def parse_riven_query(text: str) -> RivenQuery:
    """Parse `/wr` arguments including reroll, polarity, stat-shape and price filters."""
    tokens = " ".join(text.split()).split()
    kept: list[str] = []
    reroll = ""
    polarity = ""
    stat_count = ""
    max_price: int | None = None
    for index, token in enumerate(tokens):
        low = token.casefold()
        if index > 0 and low in _REROLL_TOKENS:
            reroll = _REROLL_TOKENS[low]
        elif index > 0 and low in _POLARITY_TOKENS:
            polarity = _POLARITY_TOKENS[low]
        elif index > 0 and low in _STAT_COUNT_TOKENS:
            stat_count = low
        elif index > 0 and (m := re.fullmatch(r"(\d+)p", low)):
            max_price = int(m.group(1))
        else:
            kept.append(token)
    weapon, pos, neg = split_riven_args(" ".join(kept))
    if not neg and stat_count in {"2+1", "3+1"}:
        neg = "有"
    elif not neg and stat_count in {"2+", "3+"}:
        neg = "无"
    return RivenQuery(weapon, pos, neg, reroll, polarity, stat_count, max_price)


def _lookup_stat_url(
    part: str,
    by_effect: dict[str, str],
    by_url: dict[str, str],
    aliases: dict[str, str],
) -> str | None:
    key = normalize(part)
    url = by_effect.get(key) or by_url.get(part.casefold()) or aliases.get(part.casefold())
    if url is not None and url:
        return url
    hint = _SLANG_HINTS.get(part.casefold())
    if hint is not None and hint in by_url:
        return by_url[hint]
    if hint is not None and hint:
        hint_prefix = hint.split("_/_")[0]
        for known in by_url.values():
            if known == hint_prefix or known.endswith(f"_{hint_prefix}"):
                return known
    return None


def resolve_stat_filters(
    positive_raw: str,
    negative_raw: str,
    stats: list[RivenStatInfo],
    aliases: dict[str, str],
) -> tuple[str, str]:
    """Resolve Chinese/English stat names and aliases into WM `/v1/auctions/search` params."""
    neg_param = ""
    if negative_raw:
        if negative_raw in {"有", "has"}:
            neg_param = "has"
        elif negative_raw in {"无", "none"}:
            neg_param = "none"
        else:
            raise QueryError("负面词条筛选仅支持“有”或“无”，例如：/wr 托里德 爆率,爆伤 无。")

    cleaned = positive_raw.replace("，", ",").strip()
    if not cleaned:
        return "", neg_param
    by_effect = {normalize(stat.effect): stat.url_name for stat in stats}
    by_url = {stat.url_name.casefold(): stat.url_name for stat in stats}
    resolved: list[str] = []
    for part in (token.strip() for token in cleaned.split(",") if token.strip()):
        url_name = _lookup_stat_url(part, by_effect, by_url, aliases)
        if url_name is None or not url_name:
            raise QueryError(
                f"未能识别紫卡词条“{part}”，可尝试：暴击几率、暴击伤害、多重射击、爆率、爆伤。"
            )
        if url_name not in resolved:
            resolved.append(url_name)
    return ",".join(resolved), neg_param


def _sort_price(auction: dict[str, Any]) -> int:
    for field in ("buyout_price", "starting_price", "top_bid"):
        val = auction.get(field)
        if isinstance(val, int) and val > 0:
            return val
    return 999_999_999


def _matches_riven_filters(auction: dict[str, Any], filters: RivenQuery | None) -> bool:
    if filters is None:
        return True
    if filters.max_price is not None and _sort_price(auction) > filters.max_price:
        return False
    item = _dict_field(auction, "item")
    if filters.polarity and str(item.get("polarity") or "").casefold() != filters.polarity:
        return False
    rolls = item.get("re_rolls")
    if filters.reroll == "zero" and rolls != 0:
        return False
    if filters.reroll == "low" and (not isinstance(rolls, int) or rolls > 9):
        return False
    if filters.reroll == "trash" and (not isinstance(rolls, int) or rolls < 10):
        return False
    attrs = [a for a in (item.get("attributes") or []) if isinstance(a, dict)]
    if filters.stat_count:
        pos_count = sum(1 for a in attrs if a.get("positive") is not False)
        neg_count = sum(1 for a in attrs if a.get("positive") is False)
        want_pos, _, want_neg = filters.stat_count.partition("+")
        want_neg_bool = bool(want_neg)
        if pos_count != int(want_pos) or (want_neg_bool and neg_count == 0):
            return False
        if not want_neg_bool and neg_count > 0:
            return False
    return True


def filter_online_auctions(
    raw_body: Any,
    *,
    top_n: int | None = 10,
    filters: RivenQuery | None = None,
) -> list[dict[str, Any]]:
    """Validate `/v1/auctions/search` payload and return sorted online/crossplay rows."""
    payload = raw_body.get("payload") if isinstance(raw_body, dict) else None
    raw_auctions = payload.get("auctions") if isinstance(payload, dict) else None
    if not isinstance(raw_auctions, list):
        raise QueryError("拍卖行数据格式已变化，请稍后重试。")
    active = [
        row
        for row in raw_auctions
        if isinstance(row, dict)
        and not row.get("closed")
        and row.get("visible") is not False
        and (row.get("owner") or {}).get("status") in _STATUS_LABELS
        and (row.get("platform") in (None, "pc") or bool(row.get("crossplay")))
        and _matches_riven_filters(row, filters)
    ]
    active.sort(key=_sort_price)
    return active[:top_n] if top_n is not None else active


def _format_price_cell(auction: dict[str, Any]) -> str:
    buyout = auction.get("buyout_price")
    starting = auction.get("starting_price")
    if isinstance(buyout, int) and buyout > 0:
        if isinstance(starting, int) and 0 < starting != buyout:
            return f"一口 {buyout}\n起拍 {starting}"
        return f"一口 {buyout}"
    if isinstance(starting, int) and starting > 0:
        return f"起拍 {starting}"
    top_bid = auction.get("top_bid")
    return f"当前 {top_bid}" if isinstance(top_bid, int) else "面议"


def _is_faction_damage(url: str, label: str, val: float) -> bool:
    return ("damage_vs_" in url or ("对" in label and "伤害" in label)) and abs(val) < 5


@dataclass(frozen=True)
class _AttrContext:
    total_attrs: int
    has_curse: bool
    weapon_meta: WeaponMeta | None
    trends: dict[str, RivenTrendEntry] | None


def _format_attr_badge(
    label: str,
    val: float,
    ctx: _AttrContext,
    *,
    is_curse: bool,
    is_mult: bool,
) -> str:
    if ctx.weapon_meta is None or ctx.weapon_meta.omega_attenuation <= 0 or ctx.trends is None:
        return ""
    matched = lookup_trend_optional(label, ctx.trends)
    if matched is None:
        return ""
    trend_name, trend = matched
    base_val = select_base_value(trend, ctx.weapon_meta)
    if base_val <= 0:
        return ""
    bounds = compute_low_high(
        base_val,
        ctx.weapon_meta.omega_attenuation,
        max(2, min(4, ctx.total_attrs)),
        has_curse=ctx.has_curse,
        is_curse=is_curse,
    )
    diff = compute_diff(trend_name, val, bounds, is_mult=is_mult)
    return f" ({diff})" if diff else ""


def _format_attr_line(
    attr: dict[str, Any],
    stat_map: dict[str, RivenStatInfo],
    ctx: _AttrContext | None = None,
) -> str:
    url = str(attr.get("url_name") or "")
    info = stat_map.get(url)
    label = info.effect if info else url
    val = attr.get("value")
    if not isinstance(val, (int, float)):
        return label
    is_curse = attr.get("positive") is False
    is_mult = _is_faction_damage(url, label, float(val))
    badge = (
        _format_attr_badge(label, float(val), ctx, is_curse=is_curse, is_mult=is_mult)
        if ctx is not None
        else ""
    )
    if is_mult:
        return f"×{val:g} {label}{badge}"
    unit = "%" if (info and info.units == "percent") else ""
    sign = "+" if val > 0 else ""
    return f"{sign}{val:g}{unit} {label}{badge}"


def _dict_field(raw: dict[str, Any], key: str) -> dict[str, Any]:
    val = raw.get(key)
    return val if isinstance(val, dict) else {}


def build_riven_auctions_card(
    weapon: Item,
    raw_body: Any,
    stat_map: dict[str, RivenStatInfo],
    filter_note: str,
    meta: QueryMeta,
    *,
    options: RivenDisplayOptions | None = None,
) -> Card:
    """Build paginated PC/crossplay Riven auction Card with `/w` whispers & Omega badges."""
    opts = options or RivenDisplayOptions()
    all_auctions = filter_online_auctions(raw_body, top_n=None, filters=opts.filters)
    auctions, cur_page, total_pages = paginate(all_auctions, opts.page, opts.page_size)
    rows: list[tuple[str, ...]] = []
    whispers: list[WhisperEntry] = []
    for auction in auctions:
        item = _dict_field(auction, "item")
        owner = _dict_field(auction, "owner")
        whisper = riven_whisper(
            owner,
            str(item.get("name") or ""),
            weapon.name,
            weapon.english_name,
        )
        if whisper is None:
            continue
        whispers.append(whisper)
        idx = len(whispers)
        riven_name = str(item.get("name") or "紫卡").strip().capitalize()
        mr = item.get("mastery_level")
        head = f"{riven_name} (MR{mr})" if mr is not None else riven_name
        raw_attrs = [a for a in (item.get("attributes") or []) if isinstance(a, dict)]
        has_curse = any(a.get("positive") is False for a in raw_attrs)
        mod_rank = item.get("mod_rank")
        use_omega = opts.weapon_meta if mod_rank == 8 else None
        attr_ctx = _AttrContext(len(raw_attrs), has_curse, use_omega, opts.trends)
        attrs = [_format_attr_line(a, stat_map, attr_ctx) for a in raw_attrs]
        attr_block = "\n".join(attrs) if attrs else "无词条明细"
        rank = item.get("mod_rank")
        re_rolls = item.get("re_rolls")
        polarity = _RIVEN_POLARITIES.get(str(item.get("polarity") or "").casefold(), "未知")
        spec = f"R{rank if rank is not None else '?'}·{polarity}\n{re_rolls or 0} 洗"
        status_cn = _STATUS_LABELS.get(str(owner.get("status") or ""), "在线")
        rows.append(
            (
                str(idx),
                f"{head}\n{attr_block}",
                spec,
                _format_price_cell(auction),
                f"{whisper.ingame_name}\n{status_cn}",
            )
        )
    notes = [item for item in (filter_note, page_caption(cur_page, total_pages)) if item]
    sub = subtitle(meta, *notes)
    stats_line = f"快捷私聊 /w 1：{whispers[0].text}" if whispers else ""
    return Card(
        f"{weapon.name} 紫卡拍卖",
        rows,
        sub,
        columns=("序号", "紫卡与词条", "等级 / 极性", "价格 / 白金", "卖家"),
        kind="riven",
        empty_message="暂无符合条件的在线紫卡拍卖",
        whispers=whispers,
        stats_line=stats_line,
    )


def build_lich_sister_card(
    kind: Literal["lich", "sister"],
    weapon: Item,
    raw_body: Any,
    meta: QueryMeta,
    *,
    page: int = 1,
    page_size: int = 8,
) -> Card:
    """Build paginated Kuva Lich or Tenet Sister auction Card with `/w` whispers."""
    all_auctions = filter_online_auctions(raw_body, top_n=None)
    auctions, cur_page, total_pages = paginate(all_auctions, page, page_size)
    rows: list[tuple[str, ...]] = []
    whispers: list[WhisperEntry] = []
    for auction in auctions:
        item = _dict_field(auction, "item")
        owner = _dict_field(auction, "owner")
        whisper = lich_whisper(owner, item, weapon.name, weapon.english_name)
        if whisper is None:
            continue
        whispers.append(whisper)
        idx = len(whispers)
        elem = element_label(str(item.get("element") or ""), "zh") or "未知"
        damage = item.get("damage")
        dmg_text = f"{damage}%" if damage is not None else "?"
        ephemera = " · 含幻纹" if item.get("having_ephemera") else ""
        status_cn = _STATUS_LABELS.get(str(owner.get("status") or ""), "在线")
        rows.append(
            (
                str(idx),
                f"{elem} {dmg_text}{ephemera}",
                _format_price_cell(auction),
                whisper.ingame_name,
                status_cn,
            )
        )
    label = "赤毒巫妖" if kind == "lich" else "信条姐妹"
    stats_line = f"快捷私聊 /w 1：{whispers[0].text}" if whispers else ""
    return Card(
        f"{weapon.name} · {label}拍卖",
        rows,
        subtitle(meta, page_caption(cur_page, total_pages)),
        columns=("序号", "元素 / 加成", "价格 / 白金", "卖家", "状态"),
        kind="lich_sister",
        empty_message=f"暂无在线{label}拍卖",
        whispers=whispers,
        stats_line=stats_line,
    )


def extract_candidate_choice(raw: str) -> tuple[int, str] | None:
    """Parse leading candidate selection index plus any trailing stat options."""
    cleaned = raw.strip()
    if not cleaned:
        return None
    head, _, tail = cleaned.partition(" ")
    if not head.isdigit():
        return None
    return int(head), re.sub(r"^\s+", "", tail)
