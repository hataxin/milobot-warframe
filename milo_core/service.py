"""Shared business entry points for commands and future model tools."""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

from .arbitration import (
    ARBYS_TTL,
    arbitration_summary,
    build_arbitration_card,
    build_arbitration_list_card,
    parse_arbys,
)
from .auctions import (
    RivenDisplayOptions,
    RivenQuery,
    build_lich_sister_card,
    build_riven_auctions_card,
    parse_riven_query,
    resolve_stat_filters,
)
from .cache import CachedResponse
from .card_model import Card
from .client import (
    ALIAS_URL,
    ARBYS_URL,
    AUCTIONS_SEARCH_URL,
    DUCATS_URL,
    ITEM_STATS_URL,
    MARKET_URL,
    WORLDSTATE_URL,
    DataClient,
)
from .command_flags import page_caption, paginate
from .cycles import calculate_cycles, utc_time
from .dictionary import (
    DictionaryService,
    NodeInfo,
    RivenStatInfo,
    TranslationIndex,
    WeaponMeta,
)
from .ducats import build_ducats_card
from .errors import QueryError
from .market import (
    Item,
    MarketQuery,
    enrich_item,
    filter_all_orders,
    normalize,
    parse_items,
    parse_query,
    parse_wm_stats,
    resolve_item,
)
from .relics import (
    build_relic_help_card,
    build_relics_card,
    is_tier_only,
    search_relics,
)
from .riven_analyse import build_riven_analyse_card, build_riven_analyse_help_card
from .subscription import (
    DetectedEvent,
    PendingNotification,
    SubscriptionStore,
    detect_alerts,
    detect_arbitration,
    detect_archon,
    detect_cycles,
    detect_fissures,
    detect_invasions,
    detect_sortie,
    detect_void_trader,
    match_notifications,
)
from .tools_calc import (
    RelicValuationContext,
    build_fusion_card,
    build_relic_value_card,
    build_translate_card,
    build_upgrade_cost_card,
)
from .whisper import order_whisper
from .worldstate import (
    QueryMeta,
    build_alerts_card,
    build_archon_card,
    build_calendar_card,
    build_conquest_card,
    build_daily_deals_card,
    build_duviri_card,
    build_fissures_card,
    build_invasions_card,
    build_news_card,
    build_nightwave_card,
    build_sortie_card,
    build_steel_path_card,
    build_syndicate_card,
    build_timings_card,
    build_varzia_card,
    build_void_trader_card,
)

_DELIVERY_RETENTION_SECONDS = 30 * 86_400


@dataclass(frozen=True)
class _PollContext:
    ws: dict[str, Any]
    arb_entries: list[list[Any]]
    nodes: dict[str, NodeInfo]
    trans: TranslationIndex
    tiers: dict[str, str]
    meta: QueryMeta


WORLD_CARD_ROUTES: dict[str, Callable[[WarframeService], Awaitable[Card]]] = {
    "平原": lambda s: s.cycles(),
    "全周期": lambda s: s.cycles(),
    "平原周期": lambda s: s.cycles(),
    "开放世界": lambda s: s.cycles(),
    "夜灵平原": lambda s: s.cycles(),
    "夜灵": lambda s: s.cycles(),
    "地球": lambda s: s.cycles(),
    "奥布山谷": lambda s: s.cycles(),
    "魔胎之境": lambda s: s.cycles(),
    "扎里曼": lambda s: s.cycles(),
    "cycle": lambda s: s.cycles(),
    "cycles": lambda s: s.cycles(),
    "轮换": lambda s: s.duviri(),
    "双衍王境": lambda s: s.duviri(),
    "双衍": lambda s: s.duviri(),
    "无尽回廊": lambda s: s.duviri(),
    "回廊": lambda s: s.duviri(),
    "duviri": lambda s: s.duviri(),
    "警报": lambda s: s.alerts(),
    "警报任务": lambda s: s.alerts(),
    "alert": lambda s: s.alerts(),
    "alerts": lambda s: s.alerts(),
    "裂缝": lambda s: s.fissures("normal"),
    "裂隙": lambda s: s.fissures("normal"),
    "虚空裂缝": lambda s: s.fissures("normal"),
    "虚空裂隙": lambda s: s.fissures("normal"),
    "普通裂缝": lambda s: s.fissures("normal"),
    "fissure": lambda s: s.fissures("normal"),
    "fissures": lambda s: s.fissures("normal"),
    "钢铁裂缝": lambda s: s.fissures("steel"),
    "钢铁裂隙": lambda s: s.fissures("steel"),
    "钢铁之路裂缝": lambda s: s.fissures("steel"),
    "九重天裂缝": lambda s: s.fissures("storm"),
    "九重天裂隙": lambda s: s.fissures("storm"),
    "九重天": lambda s: s.fissures("storm"),
    "虚空风暴": lambda s: s.fissures("storm"),
    "突击": lambda s: s.sortie(),
    "今日突击": lambda s: s.sortie(),
    "突击任务": lambda s: s.sortie(),
    "sortie": lambda s: s.sortie(),
    "sorties": lambda s: s.sortie(),
    "猎杀": lambda s: s.archon(),
    "执刑官猎杀": lambda s: s.archon(),
    "执刑官": lambda s: s.archon(),
    "执行官": lambda s: s.archon(),
    "执政官": lambda s: s.archon(),
    "archon": lambda s: s.archon(),
    "入侵": lambda s: s.invasions(),
    "入侵任务": lambda s: s.invasions(),
    "invasion": lambda s: s.invasions(),
    "invasions": lambda s: s.invasions(),
    "奸商": lambda s: s.void_trader(),
    "虚空商人": lambda s: s.void_trader(),
    "baro": lambda s: s.void_trader(),
    "void": lambda s: s.void_trader(),
    "钢铁": lambda s: s.steel_path(),
    "钢铁之路": lambda s: s.steel_path(),
    "钢铁奖励": lambda s: s.steel_path(),
    "钢铁兑换": lambda s: s.steel_path(),
    "steel": lambda s: s.steel_path(),
    "steelpath": lambda s: s.steel_path(),
    "电波": lambda s: s.nightwave(),
    "午夜电波": lambda s: s.nightwave(),
    "电波任务": lambda s: s.nightwave(),
    "nightwave": lambda s: s.nightwave(),
    "每日特惠": lambda s: s.daily_deals(),
    "特惠": lambda s: s.daily_deals(),
    "达尔沃": lambda s: s.daily_deals(),
    "deals": lambda s: s.daily_deals(),
    "1999": lambda s: s.calendar(),
    "1999日历": lambda s: s.calendar(),
    "日历": lambda s: s.calendar(),
    "calendar": lambda s: s.calendar(),
    "地球赏金": lambda s: s.syndicate("CetusSyndicate"),
    "希图斯": lambda s: s.syndicate("CetusSyndicate"),
    "希图斯赏金": lambda s: s.syndicate("CetusSyndicate"),
    "cetus": lambda s: s.syndicate("CetusSyndicate"),
    "金星赏金": lambda s: s.syndicate("SolarisSyndicate"),
    "索拉里斯": lambda s: s.syndicate("SolarisSyndicate"),
    "索拉里斯赏金": lambda s: s.syndicate("SolarisSyndicate"),
    "solaris": lambda s: s.syndicate("SolarisSyndicate"),
    "火卫二赏金": lambda s: s.syndicate("EntratiSyndicate"),
    "英择谛": lambda s: s.syndicate("EntratiSyndicate"),
    "英择谛赏金": lambda s: s.syndicate("EntratiSyndicate"),
    "entrati": lambda s: s.syndicate("EntratiSyndicate"),
    "仲裁": lambda s: s.arbitration(lookahead=False),
    "当前仲裁": lambda s: s.arbitration(lookahead=False),
    "arbitration": lambda s: s.arbitration(lookahead=False),
    "仲裁表": lambda s: s.arbitration(lookahead=True),
    "仲裁排期": lambda s: s.arbitration(lookahead=True),
    "仲裁前瞻": lambda s: s.arbitration(lookahead=True),
    "未来仲裁": lambda s: s.arbitration(lookahead=True),
    "金垃圾": lambda s: s.ducats("gold"),
    "杜卡德金垃圾": lambda s: s.ducats("gold"),
    "银垃圾": lambda s: s.ducats("silver"),
    "杜卡德银垃圾": lambda s: s.ducats("silver"),
    "铜垃圾": lambda s: s.ducats("copper"),
    "杜卡德铜垃圾": lambda s: s.ducats("copper"),
    "瓦奇娅": lambda s: s.varzia(),
    "圣装重生": lambda s: s.varzia(),
    "重生": lambda s: s.varzia(),
    "varzia": lambda s: s.varzia(),
    "科研": lambda s: s.conquest(),
    "深层科研": lambda s: s.conquest(),
    "时光科研": lambda s: s.conquest(),
    "archimedea": lambda s: s.conquest(),
    "conquest": lambda s: s.conquest(),
    "新闻": lambda s: s.news(),
    "公告": lambda s: s.news(),
    "活动": lambda s: s.news(),
    "news": lambda s: s.news(),
    "时效": lambda s: s.timings(),
    "总览": lambda s: s.timings(),
    "timings": lambda s: s.timings(),
    "升级消耗": lambda s: s.upgrade_cost(""),
    "开核桃": lambda s: s.relic_value(""),
}

_RIVEN_ANALYSE_PREFIX_RE = re.compile(
    r"^(?:紫卡分析|分析紫卡|wfen(?=\s|$)|rivenanalyse(?=\s|$))",
    re.IGNORECASE,
)


def _extract_prefixed_args(raw_args: str, prefixes: tuple[str, ...]) -> str | None:
    cleaned = raw_args.strip()
    if not cleaned:
        return None
    parts = cleaned.split(maxsplit=1)
    if parts[0].casefold() in prefixes:
        return parts[1].strip() if len(parts) > 1 else ""
    for prefix in prefixes:
        if len(prefix) >= 2 and prefix.isascii() is False and cleaned.startswith(prefix):
            return cleaned[len(prefix) :].strip()
    return None


def extract_relic_keyword(raw_args: str) -> str | None:
    """Extract relic lookup keyword if raw_args addresses relics/核桃."""
    return _extract_prefixed_args(raw_args, ("遗物", "核桃", "relic", "relics"))


def extract_riven_analyse_input(raw_args: str) -> str | None:
    """Extract text body if raw_args invokes local Riven disposition analysis."""
    cleaned = raw_args.strip()
    match = _RIVEN_ANALYSE_PREFIX_RE.match(cleaned)
    if match is None:
        return None
    return cleaned[match.end() :].strip()


def _candidate_card(cmd: str, subject: str, matches: list[Item]) -> Card:
    rows: list[tuple[str, ...]] = [(str(i), item.name) for i, item in enumerate(matches, 1)]
    return Card(
        f"请选择{subject}",
        rows,
        f"60 秒内在当前会话回复 /{cmd} 编号",
        matches,
        columns=("序号", f"{subject}名称"),
        kind="candidates",
    )


def _riven_filter_note(pos_raw: str, neg_raw: str) -> str:
    parts: list[str] = []
    if pos_raw:
        parts.append(f"正面：{pos_raw}")
    if neg_raw:
        parts.append(f"负面：{neg_raw}")
    return " · ".join(parts)


def _resolve_riven_target(
    weapon_raw: str,
    pos_raw: str,
    riven_items: list[Item],
    aliases: dict[str, str],
    stats_bundle: tuple[list[RivenStatInfo], dict[str, str]],
) -> tuple[list[Item], str]:
    matches = resolve_item(weapon_raw, riven_items, aliases)
    if matches or pos_raw or " " not in weapon_raw:
        return matches, pos_raw
    head, tail = weapon_raw.rsplit(" ", 1)
    stats, stat_aliases = stats_bundle
    try:
        resolve_stat_filters(tail, "", stats, stat_aliases)
    except QueryError:
        return matches, pos_raw
    head_matches = resolve_item(head, riven_items, aliases)
    if head_matches:
        return head_matches, tail
    return matches, pos_raw


class WarframeService:
    """Query the international PC server using an instance-owned data client."""

    def __init__(self, client: DataClient) -> None:
        self.client = client
        self.item_count = 0
        self.dicts = DictionaryService(client)

    async def cycles(self) -> Card:
        """Return current phases of the supported open-world cycle areas."""
        response = await self.client.get(WORLDSTATE_URL, "worldstate", 30)
        now = time.time()
        cycles = calculate_cycles(response.body, now)
        rows: list[tuple[str, ...]] = [
            (cycle.name, cycle.state, cycle.remaining(now)) for cycle in cycles
        ]
        return Card(
            "平原周期",
            rows,
            f"国际服 PC · 数据获取于 {utc_time(response.fetched_at)}",
            columns=("区域", "状态", "剩余时间"),
            kind="cycles",
        )

    async def alerts(self) -> Card:
        """Return active alerts with localized nodes and rewards."""
        ws, meta = await self._worldstate()
        nodes, trans = await asyncio.gather(
            self._safe_nodes(meta.warnings), self._safe_translations(meta.warnings)
        )
        return build_alerts_card(ws, nodes, trans, meta)

    async def fissures(self, mode: str = "normal", *, filter_kw: str = "", page: int = 1) -> Card:
        """Return active Void Fissures ('normal', 'steel', or 'storm') with filter & pagination."""
        ws, meta = await self._worldstate()
        nodes = await self._safe_nodes(meta.warnings)
        return build_fissures_card(ws, nodes, mode, meta, filter_kw=filter_kw, page=page)

    async def sortie(self) -> Card:
        """Return today's Sortie stages."""
        ws, meta = await self._worldstate()
        nodes = await self._safe_nodes(meta.warnings)
        return build_sortie_card(ws, nodes, meta)

    async def archon(self) -> Card:
        """Return this week's Archon Hunt stages."""
        ws, meta = await self._worldstate()
        nodes = await self._safe_nodes(meta.warnings)
        return build_archon_card(ws, nodes, meta)

    async def invasions(self) -> Card:
        """Return ongoing Invasions with rewards and progress."""
        ws, meta = await self._worldstate()
        nodes, trans = await asyncio.gather(
            self._safe_nodes(meta.warnings), self._safe_translations(meta.warnings)
        )
        return build_invasions_card(ws, nodes, trans, meta)

    async def void_trader(self) -> Card:
        """Return Baro Ki'Teer arrival status or active inventory."""
        ws, meta = await self._worldstate()
        nodes, trans = await asyncio.gather(
            self._safe_nodes(meta.warnings), self._safe_translations(meta.warnings)
        )
        return build_void_trader_card(ws, nodes, trans, meta)

    async def steel_path(self) -> Card:
        """Return Teshin Steel Path weekly offering rotation."""
        return build_steel_path_card(time.time())

    async def nightwave(self) -> Card:
        """Return active Nightwave season challenges."""
        ws, meta = await self._worldstate()
        nw_dict = await self._safe_load(self.dicts.nightwave, meta.warnings, "电波词典暂不可用", {})
        return build_nightwave_card(ws, nw_dict, meta)

    async def daily_deals(self) -> Card:
        """Return Darvo's Daily Deals."""
        ws, meta = await self._worldstate()
        trans = await self._safe_translations(meta.warnings)
        return build_daily_deals_card(ws, trans, meta)

    async def calendar(self) -> Card:
        """Return 1999 Calendar season schedule."""
        ws, meta = await self._worldstate()
        trans = await self._safe_translations(meta.warnings)
        return build_calendar_card(ws, trans, meta)

    async def syndicate(self, tag: str) -> Card:
        """Return active Syndicate bounty missions for the specified tag."""
        ws, meta = await self._worldstate()
        pools, trans = await asyncio.gather(
            self._safe_load(self.dicts.reward_pool, meta.warnings, "赏金奖励池暂不可用", {}),
            self._safe_translations(meta.warnings),
        )
        return build_syndicate_card(ws, tag, pools, trans, meta)

    async def duviri(self) -> Card:
        """Return Duviri mood cycle and Endless Circuit options."""
        ws, meta = await self._worldstate()
        weapons_en = await self._safe_load(
            self.dicts.weapons_en, meta.warnings, "武器翻译词典暂不可用", {}
        )
        return build_duviri_card(ws, weapons_en, meta)

    async def arbitration(
        self, *, lookahead: bool = False, show_all: bool = False, page: int = 1
    ) -> Card:
        """Return the current Arbitration mission or upcoming paginated lookahead."""
        warnings: list[str] = []
        cached_at, entries = await self._arbys()
        nodes = await self._safe_nodes(warnings)
        if lookahead:
            tiers = await self.dicts.arbitration_tiers()
        else:
            tiers = await self._safe_tiers(warnings)
        meta = QueryMeta(time.time(), cached_at, warnings)
        if lookahead:
            return build_arbitration_list_card(
                entries, nodes, tiers, meta, page=page, show_all=show_all
            )
        return build_arbitration_card(entries, nodes, tiers, meta)

    async def varzia(self, *, page: int = 1) -> Card:
        """Return Varzia Prime Resurgence offerings and schedule."""
        ws, meta = await self._worldstate()
        nodes, trans = await asyncio.gather(
            self._safe_nodes(meta.warnings), self._safe_translations(meta.warnings)
        )
        return build_varzia_card(ws, nodes, trans, meta, page=page)

    async def conquest(self) -> Card:
        """Return weekly Deep/Temporal Archimedea (`Conquests`) stages & modifiers."""
        ws, meta = await self._worldstate()
        trans = await self._safe_translations(meta.warnings)
        return build_conquest_card(ws, trans, meta)

    async def news(self, *, page: int = 1) -> Card:
        """Return recent official Warframe announcements and events."""
        ws, meta = await self._worldstate()
        return build_news_card(ws, meta, page=page)

    async def timings(self) -> Card:
        """Return consolidated overview of cycles, daily timers, Baro, and Arbitration."""
        ws, meta = await self._worldstate()
        arb_summary = None
        try:
            _, entries = await self._arbys()
            nodes, tiers = await asyncio.gather(
                self._safe_nodes(meta.warnings), self._safe_tiers(meta.warnings)
            )
            arb_summary = arbitration_summary(entries, nodes, tiers, meta.now)
        except QueryError:
            meta.warnings.append("仲裁排期暂不可用")
        return build_timings_card(ws, meta, arbys_summary=arb_summary)

    async def translate_term(self, keyword: str, *, page: int = 1) -> Card:
        """Search bidirectional EN<->ZH names using Market catalogue & PublicExport."""
        warnings: list[str] = []
        catalogue, trans, aliases = await asyncio.gather(
            self.client.get(MARKET_URL + "/items", "items", 86_400),
            self._safe_translations(warnings),
            self._aliases(warnings),
        )
        items = parse_items(catalogue.body)
        self.item_count = len(items)
        meta = QueryMeta(time.time(), catalogue.fetched_at, warnings)
        return build_translate_card(keyword, trans, items, aliases, meta, page=page)

    async def fusion_calc(self, raw_args: str) -> Card:
        """Compute Kuva/Tenet Valence Fusion step progression locally."""
        now = time.time()
        return build_fusion_card(raw_args, QueryMeta(now, now, []))

    async def upgrade_cost(self, raw_args: str) -> Card:
        """Compute Mod Endo/Credits or Arcane upgrade costs locally."""
        now = time.time()
        return build_upgrade_cost_card(raw_args, QueryMeta(now, now, []))

    async def relic_value(self, raw_args: str, *, page: int = 1) -> Card:
        """Rank Radiant Void Relics by expected ducats or platinum across active fissures."""
        ws, meta = await self._worldstate()
        nodes, relics, catalogue, ducats_cached = await asyncio.gather(
            self._safe_nodes(meta.warnings),
            self.dicts.relics(),
            self.client.get(MARKET_URL + "/items", "items", 86_400),
            self._ducats(),
        )
        items = parse_items(catalogue.body)
        self.item_count = len(items)
        ctx = RelicValuationContext(ws, nodes, relics, items, ducats_cached.body)
        return build_relic_value_card(raw_args, ctx, meta, page=page)

    async def _resolve_prefixed_world(self, raw: str, page: int) -> Card | None:
        if (tr_kw := _extract_prefixed_args(raw, ("翻译", "translate"))) is not None:
            return await self.translate_term(tr_kw, page=page)
        if (fu_args := _extract_prefixed_args(raw, ("融合", "valence", "fusion"))) is not None:
            return await self.fusion_calc(fu_args)
        if (up := _extract_prefixed_args(raw, ("升级消耗", "mod消耗", "赋能消耗"))) is not None:
            return await self.upgrade_cost(up)
        if (rv_args := _extract_prefixed_args(raw, ("开核桃", "核桃收益"))) is not None:
            return await self.relic_value(rv_args, page=page)
        if (fl_kw := _extract_prefixed_args(raw, ("钢铁裂缝", "钢铁裂隙"))) is not None:
            return await self.fissures("steel", filter_kw=fl_kw, page=page)
        st = _extract_prefixed_args(raw, ("九重天裂缝", "九重天裂隙", "虚空风暴"))
        if st is not None:
            return await self.fissures("storm", filter_kw=st, page=page)
        fr = _extract_prefixed_args(raw, ("裂缝", "裂隙", "虚空裂缝", "虚空裂隙"))
        if fr is not None:
            mode = "steel" if "钢铁" in fr else ("storm" if "九重天" in fr else "normal")
            cleaned = fr.replace("钢铁", "").replace("九重天", "").strip()
            return await self.fissures(mode, filter_kw=cleaned, page=page)
        if (arb := _extract_prefixed_args(raw, ("仲裁表", "仲裁排期", "仲裁前瞻"))) is not None:
            show_all = any(t in arb for t in ("所有", "全部", "all"))
            return await self.arbitration(lookahead=True, show_all=show_all, page=page)
        return None

    async def resolve_world_card(
        self, topic: str, *, keyword: str = "", page: int = 1
    ) -> Card | None:
        """Resolve a shared direct command or Tool query topic into a Card, or None if unknown."""
        raw = topic.strip()
        if extra := keyword.strip():
            raw = f"{raw} {extra}".strip() if raw else f"遗物 {extra}"
        if (card := await self._resolve_prefixed_world(raw, page)) is not None:
            return card
        if (relic_kw := extract_relic_keyword(raw)) is not None:
            return await self.relics(relic_kw)
        if (analyse_input := extract_riven_analyse_input(raw)) is not None:
            return await self.riven_analyse(analyse_input)
        key = "".join(raw.split()).casefold()
        if key in {"瓦奇娅", "圣装重生", "重生", "varzia"}:
            return await self.varzia(page=page)
        if key in {"新闻", "公告", "活动", "news"}:
            return await self.news(page=page)
        if route := WORLD_CARD_ROUTES.get(key):
            return await route(self)
        return None

    async def market_for_tool(
        self,
        item_name: str,
        *,
        order_type: str = "sell",
        max_rank: bool = False,
        english: bool = False,
        page: int = 1,
    ) -> Card:
        """Query Warframe Market orders cleanly from a natural-language tool call."""
        cleaned = item_name.strip()
        if not cleaned:
            raise QueryError("请提供要查询的 Warframe Market 物品名称。")
        key = "".join(cleaned.split()).casefold()
        if key in {"金垃圾", "杜卡德金垃圾"}:
            return await self.ducats("gold")
        if key in {"银垃圾", "杜卡德银垃圾"}:
            return await self.ducats("silver")
        if key in {"铜垃圾", "杜卡德铜垃圾"}:
            return await self.ducats("copper")
        parsed = parse_query(cleaned)
        mode = order_type.strip().casefold()
        buyer = parsed.buyer or mode in {"buy", "买家", "购买"}
        return await self.market(
            MarketQuery(parsed.keyword, buyer=buyer, max_rank=parsed.max_rank or max_rank),
            english=english,
            page=page,
        )

    async def ducats(self, kind: Literal["gold", "silver", "copper"]) -> Card:
        """Rank top-10 gold (`100`), silver (`45-99`), or copper (`15-44`) parts by DPP."""
        catalogue, cached = await asyncio.gather(
            self.client.get(MARKET_URL + "/items", "items", 86_400),
            self._ducats(),
        )
        items = parse_items(catalogue.body)
        self.item_count = len(items)
        name_map = {item.item_id: item.name for item in items}
        meta = QueryMeta(time.time(), cached.fetched_at, [])
        return build_ducats_card(kind, cached.body, name_map, meta)

    @staticmethod
    def _match_weapon_meta(selected: Item, weapons: list[WeaponMeta]) -> WeaponMeta | None:
        key_zh, key_en = normalize(selected.name), normalize(selected.english_name)
        for weapon in weapons:
            if weapon.omega_attenuation > 0 and (
                normalize(weapon.name) == key_zh
                or (weapon.english_name and normalize(weapon.english_name) == key_en)
            ):
                return weapon
        return None

    async def riven_market(
        self,
        raw_args: str,
        selected: Item | None = None,
        *,
        parsed: RivenQuery | tuple[str, str, str] | None = None,
        page: int = 1,
    ) -> Card:
        """Search paginated online PC/crossplay Riven auctions with `/w` whispers."""
        filters = (
            parsed
            if isinstance(parsed, RivenQuery)
            else RivenQuery(*parsed)
            if parsed is not None
            else parse_riven_query(raw_args)
        )
        if selected is None and not filters.weapon:
            raise QueryError(
                "用法：/wr 武器名 [词条1,词条2] [有|无]，例如：/wr 托里德 爆率,爆伤 无。"
            )
        warnings: list[str] = []
        (stats, stat_aliases), aliases = await asyncio.gather(
            self.dicts.riven_tions(),
            self._aliases(warnings),
        )
        pos_raw = filters.positive
        if selected is None:
            riven_items = await self.dicts.riven_weapons()
            matches, pos_raw = _resolve_riven_target(
                filters.weapon, pos_raw, riven_items, aliases, (stats, stat_aliases)
            )
            if not matches:
                raise QueryError("没有找到该紫卡武器，请尝试完整中文名、英文名或武器 slug。")
            if len(matches) > 1:
                return _candidate_card("wr", "紫卡武器", matches)
            selected = matches[0]
        pos_param, neg_param = resolve_stat_filters(pos_raw, filters.negative, stats, stat_aliases)
        params: dict[str, Any] = {
            "type": "riven",
            "weapon_url_name": selected.slug,
            "sort_by": "price_asc",
            "polarity": filters.polarity or "any",
        }
        if pos_param:
            params["positive_stats"] = pos_param
        if neg_param:
            params["negative_stats"] = neg_param
        key = f"market:riven:{selected.slug}:{pos_param}:{neg_param}:{filters.polarity}"
        cached, weapons, trends = await asyncio.gather(
            self._auction_search(key, params),
            self._safe_silent(self.dicts.weapons_meta, []),
            self._safe_silent(self.dicts.riven_analyse_trends, {}),
        )
        meta = QueryMeta(time.time(), cached.fetched_at, warnings)
        stat_map = {stat.url_name: stat for stat in stats}
        return build_riven_auctions_card(
            selected,
            cached.body,
            stat_map,
            _riven_filter_note(pos_raw, filters.negative),
            meta,
            options=RivenDisplayOptions(
                filters=filters,
                weapon_meta=self._match_weapon_meta(selected, weapons),
                trends=trends,
                page=page,
            ),
        )

    async def lich_sister_market(
        self,
        kind: Literal["lich", "sister"],
        keyword: str,
        selected: Item | None = None,
        *,
        page: int = 1,
    ) -> Card:
        """Search paginated online PC/crossplay Kuva Lich or Tenet Sister auctions."""
        cmd = "cd" if kind == "lich" else "xt"
        label = "赤毒武器" if kind == "lich" else "信条武器"
        cleaned = keyword.strip()
        if selected is None and not cleaned:
            example = "布拉玛" if kind == "lich" else "典客"
            raise QueryError(f"用法：/{cmd} 武器名，例如：/{cmd} {example}。")
        warnings: list[str] = []
        if selected is None:
            catalog, aliases = await asyncio.gather(
                self.dicts.lich_weapons() if kind == "lich" else self.dicts.sister_weapons(),
                self._aliases(warnings),
            )
            matches = resolve_item(cleaned, catalog, aliases)
            if not matches:
                raise QueryError(f"没有找到该{label}，请尝试完整中文名、英文名或武器 slug。")
            if len(matches) > 1:
                return _candidate_card(cmd, label, matches)
            selected = matches[0]
        params: dict[str, Any] = {
            "type": "lich" if kind == "lich" else "sister",
            "weapon_url_name": selected.slug,
            "sort_by": "price_asc",
        }
        cached = await self._auction_search(f"market:{kind}:{selected.slug}", params)
        meta = QueryMeta(time.time(), cached.fetched_at, warnings)
        return build_lich_sister_card(kind, selected, cached.body, meta, page=page)

    async def riven_analyse(self, raw_text: str) -> Card:
        """Compute local pure-Python Riven stat intervals and median deviation."""
        cleaned = raw_text.strip()
        if not cleaned:
            return build_riven_analyse_help_card()
        warnings: list[str] = []
        weapons, trends, aliases = await asyncio.gather(
            self.dicts.weapons_meta(),
            self.dicts.riven_analyse_trends(),
            self._aliases(warnings),
        )
        return build_riven_analyse_card(cleaned, weapons, trends, aliases)

    async def relics(self, keyword: str) -> Card:
        """Search Void Relics by relic code, alias, or reward name."""
        cleaned = keyword.strip()
        if not cleaned:
            return build_relic_help_card()
        if is_tier_only(cleaned):
            raise QueryError(
                f"“{cleaned}”仅包含纪元档位，请补充编号或奖励名称，"
                "例如：/遗物 中纪 A1 或 /遗物 Volt Prime。"
            )
        warnings: list[str] = []
        relic_entries, aliases = await asyncio.gather(
            self.dicts.relics(),
            self._aliases(warnings),
        )
        matches = search_relics(cleaned, relic_entries, aliases)
        meta = QueryMeta(time.time(), time.time(), warnings)
        return build_relics_card(cleaned, matches, meta)

    async def _resolve_market_item(self, query: MarketQuery, warnings: list[str]) -> Item | Card:
        catalogue = await self.client.get(MARKET_URL + "/items", "items", 86_400)
        items = parse_items(catalogue.body)
        self.item_count = len(items)
        aliases = await self._aliases(warnings)
        matches = resolve_item(query.keyword, items, aliases)
        if not matches:
            raise QueryError("没有找到该物品，请尝试完整中文名、英文名或市场 slug。")
        if len(matches) > 1:
            return _candidate_card("wm", "物品", matches)
        return matches[0]

    async def _item_stats_line(self, slug: str) -> str:
        async def _load() -> str:
            cached = await self.client.get_or_build(
                f"market:stats:{slug}",
                300,
                lambda: self.client.fetch_market_json(ITEM_STATS_URL.format(slug=slug)),
                persist=False,
            )
            return parse_wm_stats(cached.body)

        return await self._safe_silent(_load, "")

    async def market(
        self,
        query: MarketQuery,
        selected: Item | None = None,
        *,
        english: bool = False,
        page: int = 1,
    ) -> Card:
        """Resolve one item and return paginated online quotes or numbered candidates."""
        warnings: list[str] = []
        if selected is None:
            resolved = await self._resolve_market_item(query, warnings)
            if isinstance(resolved, Card):
                return resolved
            selected = resolved
        item = await self._enrich_for_max(selected, query)
        response, wm_stats = await asyncio.gather(
            self.client.get(MARKET_URL + "/orders/item/" + item.slug, "orders", 60),
            self._item_stats_line(item.slug),
        )
        orders, cur_page, total_pages = paginate(
            filter_all_orders(response.body, item, query), page, 8
        )
        has_rank = query.max_rank or any(order.rank is not None for order in orders)
        columns = ("玩家", "状态", "单价 / 白金", "数量") + (("等级",) if has_rank else ())
        rows: list[tuple[str, ...]] = [
            (
                order.player,
                order.status if english else {"ingame": "游戏中", "online": "在线"}[order.status],
                str(order.price),
                str(order.quantity),
                *((str(order.rank) if order.rank is not None else "—",) if has_rank else ()),
            )
            for order in orders
        ]
        whispers = [
            order_whisper(order, item.name, item.english_name, buyer=query.buyer)
            for order in orders
        ]
        direction = "买家 · 价格从高到低" if query.buyer else "卖家 · 价格从低到高"
        parts = [
            "PC",
            direction,
            "满级" if query.max_rank else "",
            page_caption(cur_page, total_pages),
            utc_time(response.fetched_at),
            "；".join(warnings),
        ]
        caption = " · ".join(p for p in parts if p)
        w_preview = f"快捷私聊 /w 1：{whispers[0].text}" if whispers else ""
        stats_parts = [x for x in (wm_stats, w_preview) if x]
        return Card(
            item.english_name if english else item.name,
            rows,
            caption,
            columns=columns,
            kind="market",
            empty_message="暂无符合条件的在线订单",
            whispers=whispers,
            stats_line="\n".join(stats_parts),
        )

    async def collect_notifications(
        self, store: SubscriptionStore, *, now: float | None = None
    ) -> list[PendingNotification]:
        """Evaluate active subscription rules and return unseen per-stream notifications."""
        rules = await asyncio.to_thread(store.list_all)
        if not rules:
            return []
        current = time.time() if now is None else now
        needed = {rule.event_type for rule in rules}
        ctx = await self._load_poll_context(needed, current)
        events_by_type = self._detect_events(needed, ctx)
        delivered = await self._delivered_lookup(store, rules, events_by_type)
        await asyncio.to_thread(store.prune_deliveries, current - _DELIVERY_RETENTION_SECONDS)
        return match_notifications(rules, events_by_type, delivered, ctx.meta)

    async def _load_poll_context(self, needed: set[str], current: float) -> _PollContext:
        ws_types = {"alerts", "fissures", "invasions", "sortie", "archon", "void_trader", "cycles"}
        needs_ws = bool(needed & ws_types)
        needs_arb = "arbitration" in needed
        ws_data: dict[str, Any] = {}
        fetched_at = current
        warnings: list[str] = []
        if needs_ws:
            ws_data, ws_meta = await self._worldstate()
            fetched_at = ws_meta.fetched_at
        arb_entries: list[list[Any]] = []
        if needs_arb:
            arb_at, arb_entries = await self._arbys()
            if not needs_ws:
                fetched_at = arb_at
        node_types = {
            "alerts",
            "fissures",
            "invasions",
            "sortie",
            "archon",
            "void_trader",
            "arbitration",
        }
        nodes = await self._safe_nodes(warnings) if (needed & node_types) else {}
        trans = (
            await self._safe_translations(warnings)
            if (needed & {"alerts", "invasions", "void_trader"})
            else TranslationIndex({}, {})
        )
        tiers = await self._safe_tiers(warnings) if needs_arb else {}
        return _PollContext(
            ws_data, arb_entries, nodes, trans, tiers, QueryMeta(current, fetched_at, warnings)
        )

    def _detect_events(self, needed: set[str], ctx: _PollContext) -> dict[str, list[DetectedEvent]]:
        detectors: dict[str, Callable[[], list[DetectedEvent]]] = {
            "alerts": lambda: detect_alerts(ctx.ws, ctx.nodes, ctx.trans, ctx.meta.now),
            "fissures": lambda: detect_fissures(ctx.ws, ctx.nodes, ctx.meta.now),
            "invasions": lambda: detect_invasions(ctx.ws, ctx.nodes, ctx.trans),
            "sortie": lambda: detect_sortie(ctx.ws, ctx.nodes, ctx.meta),
            "archon": lambda: detect_archon(ctx.ws, ctx.nodes, ctx.meta),
            "void_trader": lambda: detect_void_trader(ctx.ws, ctx.nodes, ctx.trans, ctx.meta),
            "cycles": lambda: detect_cycles(ctx.ws, ctx.meta.now),
            "arbitration": lambda: detect_arbitration(
                ctx.arb_entries, ctx.nodes, ctx.tiers, ctx.meta.now
            ),
        }
        return {
            event_type: detectors[event_type]() for event_type in needed if event_type in detectors
        }

    async def _delivered_lookup(
        self,
        store: SubscriptionStore,
        rules: list[Any],
        events_by_type: dict[str, list[DetectedEvent]],
    ) -> dict[str, set[str]]:
        keys_by_stream: dict[str, list[str]] = {}
        for rule in rules:
            keys = [evt.event_key for evt in events_by_type.get(rule.event_type, [])]
            if keys:
                keys_by_stream.setdefault(rule.stream_id, []).extend(keys)

        def _query_all() -> dict[str, set[str]]:
            return {
                sid: store.delivered_keys_for_stream(sid, keys)
                for sid, keys in keys_by_stream.items()
            }

        return await asyncio.to_thread(_query_all) if keys_by_stream else {}

    async def _arbys(self) -> tuple[float, list[list[Any]]]:
        async def _build_arbys() -> list[list[Any]]:
            raw = await self.client.fetch_text(ARBYS_URL)
            return parse_arbys(raw, time.time())

        cached = await self.client.get_or_build("raw:arbys:v1", ARBYS_TTL, _build_arbys)
        return cached.fetched_at, cached.body

    async def _ducats(self) -> CachedResponse:
        async def _build_ducats() -> Any:
            body = await self.client.fetch_market_json(DUCATS_URL)
            if not isinstance(body, dict) or not isinstance(body.get("payload"), dict):
                raise QueryError("杜卡德垃圾数据格式已变化，请稍后重试。")
            return body

        return await self.client.get_or_build("market:ducats:v1", 120, _build_ducats, persist=False)

    async def _auction_search(self, key: str, params: dict[str, Any]) -> CachedResponse:
        async def _build_auctions() -> Any:
            body = await self.client.fetch_market_json(
                AUCTIONS_SEARCH_URL,
                params=params,
                extra_headers={"Platform": "pc", "Crossplay": "true"},
            )
            payload = body.get("payload") if isinstance(body, dict) else None
            if not isinstance(payload, dict) or not isinstance(payload.get("auctions"), list):
                raise QueryError("拍卖行数据格式已变化，请稍后重试。")
            return body

        return await self.client.get_or_build(key, 120, _build_auctions, persist=False)

    async def cached_counts(self) -> dict[str, int]:
        """Return cached dictionary counts without network calls."""
        return await self.dicts.cached_counts()

    async def _worldstate(self) -> tuple[dict[str, Any], QueryMeta]:
        response = await self.client.get(WORLDSTATE_URL, "worldstate", 30)
        return response.body, QueryMeta(time.time(), response.fetched_at, [])

    async def _safe_silent[T](self, loader: Callable[[], Awaitable[T]], fallback: T) -> T:
        try:
            return await loader()
        except QueryError:
            return fallback

    async def _safe_load[T](
        self,
        loader: Callable[[], Awaitable[T]],
        warnings: list[str],
        message: str,
        fallback: T,
    ) -> T:
        try:
            return await loader()
        except QueryError:
            warnings.append(message)
            return fallback

    async def _safe_nodes(self, warnings: list[str]) -> dict[str, NodeInfo]:
        return await self._safe_load(
            self.dicts.nodes, warnings, "节点词典暂不可用，显示原始节点 ID", {}
        )

    async def _safe_translations(self, warnings: list[str]) -> TranslationIndex:
        return await self._safe_load(
            self.dicts.translations, warnings, "物品翻译词典暂不可用", TranslationIndex({}, {})
        )

    async def _safe_tiers(self, warnings: list[str]) -> dict[str, str]:
        return await self._safe_load(self.dicts.arbitration_tiers, warnings, "仲裁分级暂不可用", {})

    async def _aliases(self, warnings: list[str]) -> dict[str, str]:
        try:
            response = await self.client.get(ALIAS_URL, "alias", 604_800)
        except QueryError:
            warnings.append("别名数据暂不可用，可用完整名称查询")
            return {}
        aliases: dict[str, str] = {}
        for row in response.body:
            if (
                isinstance(row, dict)
                and isinstance(row.get("cn"), str)
                and isinstance(row.get("en"), str)
            ):
                aliases[normalize(row["cn"])] = row["en"]
        return aliases

    async def _enrich_for_max(self, item: Item, query: MarketQuery) -> Item:
        if not query.max_rank or item.max_rank is not None:
            return item
        response = await self.client.get(MARKET_URL + "/item/" + item.slug + "/set", "detail", 3600)
        return enrich_item(item, response.body)


def catalogue_size(body: Any) -> int:
    """Count cached items without a network request, for the status command."""
    return len(body.get("data", [])) if isinstance(body, dict) else 0
