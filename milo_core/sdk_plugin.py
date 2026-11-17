"""Milo bot entry point for the native Warframe assistant plugin."""

import asyncio
import base64
import contextlib
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, ClassVar, Literal, cast, override

import httpx
from maibot_sdk import (
    CONFIG_RELOAD_SCOPE_SELF,
    Command,
    MaiBotPlugin,
    PluginConfigBase,
    Tool,
)
from maibot_sdk.types import ToolParameterInfo, ToolParamType

from .auctions import RivenQuery, extract_candidate_choice, parse_riven_query
from .cache import ResponseCache
from .card_model import Card
from .client import MARKET_URL, DataClient
from .command_flags import parse_command_flags
from .config import MiloConfig
from .errors import QueryError
from .market import Item, MarketQuery, parse_query
from .render import render_card
from .service import WORLD_CARD_ROUTES, WarframeService, catalogue_size
from .subscription import (
    SUBSCRIPTION_LABELS,
    FoundryStore,
    SubscriptionStore,
    build_foundry_list_card,
    build_subscription_help_card,
    build_subscription_list_card,
    format_filter_summary,
    parse_foundry_spec,
    parse_subscribe_spec,
    parse_unsubscribe_target,
)
from .whisper import WhisperStore
from .worldstate import build_help_card

VERSION = "1.0.0"


def _build_direct_command_pattern() -> str:
    spaced = (
        "取消订阅",
        "订阅",
        "退订",
        "unsubscribe",
        "subscribe",
        "unsub",
        "sub",
        "铸造提醒",
        "取消铸造",
        "钢铁裂缝",
        "钢铁裂隙",
        "钢铁之路裂缝",
        "九重天裂缝",
        "九重天裂隙",
        "虚空风暴",
        "虚空裂缝",
        "虚空裂隙",
        "普通裂缝",
        "裂缝",
        "裂隙",
        "fissures",
        "fissure",
        "仲裁前瞻",
        "仲裁排期",
        "仲裁表",
        "未来仲裁",
        "开核桃",
        "核桃收益",
        "升级消耗",
        "mod消耗",
        "赋能消耗",
        "翻译",
        "translate",
        "融合",
        "valence",
        "fusion",
        "relics",
        "relic",
        "rivenanalyse",
        "wfen",
        "赤毒武器",
        "赤毒巫妖",
        "赤毒",
        "信条武器",
        "信条姐妹",
        "信条",
    )
    exact = sorted(
        {
            "帮助",
            "help",
            "状态",
            "status",
            "订阅列表",
            "我的订阅",
            "subscriptions",
            "sublist",
            "铸造列表",
            *WORLD_CARD_ROUTES.keys(),
        }
        - set(spaced),
        key=len,
        reverse=True,
    )
    cn_open = ("紫卡分析", "分析紫卡", "遗物", "核桃")
    exact_pat = "|".join(re.escape(k) for k in exact)
    spaced_pat = "|".join(re.escape(k) for k in spaced)
    cn_pat = "|".join(re.escape(k) for k in cn_open)
    flag_tail = r"(?:\s+(?:-(?:w|en|\d+)))*"
    return (
        r"(?is)^\s*(?:@\S+\s+)*/(?P<args>"
        rf"(?:{cn_pat}).*$"
        rf"|(?:{spaced_pat})(?=$|\s).*$"
        rf"|(?:{exact_pat}){flag_tail}\s*$"
        r")"
    )


@dataclass(frozen=True)
class PendingSelection:
    """An expiring candidate list scoped to one chat stream and command kind."""

    query: Any
    items: list[Item]
    expires_at: float


class MiloBotPlugin(MaiBotPlugin):
    """Adapt commands, tools, and subscription pushes for Milo bot through SDK."""

    config_model: ClassVar[type[PluginConfigBase] | None] = MiloConfig

    def __init__(self) -> None:
        super().__init__()
        self._service: WarframeService | None = None
        self._subscriptions: SubscriptionStore | None = None
        self._foundry: FoundryStore | None = None
        self._pending: dict[tuple[str, str], PendingSelection] = {}
        self._whispers = WhisperStore()
        self._poll_task: asyncio.Task[None] | None = None
        self._poll_lock: asyncio.Lock | None = None

    @property
    def settings(self) -> MiloConfig:
        """Return the declared typed configuration."""
        return cast(MiloConfig, self.config)

    @override
    async def on_load(self) -> None:
        """Open only local state and start background subscription polling if enabled."""
        if self._service is not None:
            return
        cache = ResponseCache(self.ctx.paths.data_dir)
        await asyncio.to_thread(cache.initialize)
        self._subscriptions = SubscriptionStore(cache.path)
        self._foundry = FoundryStore(cache.path)
        self._poll_lock = asyncio.Lock()
        http = httpx.AsyncClient(
            timeout=self.settings.timeout_seconds,
            follow_redirects=True,
            headers={
                "User-Agent": f"MiloBot-Warframe/{VERSION}",
                "Accept": "application/json",
                "Language": "zh-hans",
                "Platform": "pc",
                "Crossplay": "true",
            },
        )
        self._service = WarframeService(DataClient(cache, http))
        cached = await asyncio.to_thread(cache.get, MARKET_URL + "/items")
        if cached is not None:
            self._service.item_count = catalogue_size(cached.body)
        self._start_subscription_loop()
        self.ctx.logger.info("Milo bot Warframe 插件 %s 已加载，数据按需获取", VERSION)

    @override
    async def on_unload(self) -> None:
        """Stop background polling, close HTTP client, and discard transient selections."""
        await self._stop_subscription_loop()
        service, self._service = self._service, None
        self._subscriptions = None
        self._foundry = None
        self._poll_lock = None
        self._pending.clear()
        self._whispers.clear()
        if service is not None:
            await service.client.close()

    @override
    async def on_config_update(self, scope: str, config_data: dict[str, Any], version: str) -> None:
        """Apply plugin settings by replacing only owned resources."""
        if scope == CONFIG_RELOAD_SCOPE_SELF:
            self.set_plugin_config(config_data)
            await self.on_unload()
            await self.on_load()
            self.ctx.logger.info("Warframe 插件配置已更新：%s", version)

    def _start_subscription_loop(self) -> None:
        if self._poll_task is None and self.settings.enabled and self.settings.subscription_enabled:
            self._poll_task = asyncio.create_task(self._subscription_loop())

    async def _stop_subscription_loop(self) -> None:
        task, self._poll_task = self._poll_task, None
        if task is None:
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    async def _subscription_loop(self) -> None:
        interval = max(60, int(self.settings.subscription_interval_seconds))
        while True:
            try:
                await asyncio.sleep(interval)
                await self.poll_subscriptions_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                self.ctx.logger.exception("Warframe 订阅轮询异常")

    async def poll_subscriptions_once(self) -> int:
        """Run one subscription + Foundry detection & delivery cycle, returning count."""
        lock = self._poll_lock
        service = self._service
        store = self._subscriptions
        if (
            lock is None
            or service is None
            or store is None
            or not self.settings.enabled
            or not self.settings.subscription_enabled
        ):
            return 0
        async with lock:
            notifications = await service.collect_notifications(store)
            delivered = 0
            for item in notifications:
                if await self._deliver_notification(item.card, item.stream_id):
                    await asyncio.to_thread(
                        store.record_deliveries, item.stream_id, item.event_keys
                    )
                    if item.once:
                        await asyncio.to_thread(store.remove, item.stream_id, item.event_type)
                    delivered += 1
            delivered += await self._deliver_due_foundry()
            return delivered

    async def _deliver_due_foundry(self) -> int:
        foundry = self._foundry
        if foundry is None:
            return 0
        due_items = await asyncio.to_thread(foundry.pop_due, time.time())
        delivered = 0
        for item in due_items:
            msg = f"铸造完成提醒：你的【{item.item_name}】已完成铸造，记得上线领取！"
            ok, _, _ = await self._send_text(msg, item.stream_id)
            if ok:
                delivered += 1
        return delivered

    async def _deliver_notification(self, card: Card, stream_id: str) -> bool:
        try:
            ok, _, _ = await self._send_card(card, stream_id)
            return ok
        except Exception:
            self.ctx.logger.exception("Warframe 订阅推送失败：stream=%s", stream_id)
            return False

    def _get_service(self) -> WarframeService:
        if not self.settings.enabled:
            raise QueryError("Warframe 查询已停用。")
        if self._service is None:
            raise QueryError("Warframe 插件尚未加载完成，请稍后重试。")
        return self._service

    @Command("wf_dispatch", pattern=_build_direct_command_pattern())
    async def handle_wf(
        self,
        stream_id: str = "",
        matched_groups: dict[str, str | None] | None = None,
        **kwargs: Any,
    ) -> tuple[bool, str, int]:
        """Handle help, status, world state, arbitration, relics, and Riven analysis."""
        raw_args = ((matched_groups or {}).get("args") or "").strip()
        return await self._run_command(
            stream_id,
            "命令执行",
            kwargs,
            lambda service, user_id: self._dispatch_wf(service, raw_args, stream_id, user_id),
        )

    async def _dispatch_wf(
        self, service: WarframeService, raw_args: str, stream_id: str, user_id: str
    ) -> tuple[bool, str, int]:
        allow_page = (
            not raw_args.lstrip()
            .casefold()
            .startswith(("紫卡分析", "分析紫卡", "wfen", "rivenanalyse"))
        )
        flags = parse_command_flags(raw_args, allow_page=allow_page)
        cleaned = flags.cleaned
        key = "".join(cleaned.split()).casefold()
        if key in {"状态", "status"}:
            return await self._send_text(await self._status_text(service, stream_id), stream_id)
        sub_reply = await self._maybe_subscription_command(cleaned, stream_id, user_id)
        if sub_reply is not None:
            if isinstance(sub_reply, Card):
                return await self._send_card(sub_reply, stream_id, force_text=flags.text_only)
            return await self._send_text(sub_reply, stream_id)
        if auction := await self._maybe_wf_auction(service, cleaned, page=flags.page):
            cmd, kw, card = auction
            return await self._finalize_card(
                cmd, kw, card, stream_id, user_id, force_text=flags.text_only
            )
        if card := await service.resolve_world_card(cleaned, page=flags.page):
            return await self._send_card(card, stream_id, force_text=flags.text_only)
        return await self._send_card(build_help_card(), stream_id, force_text=flags.text_only)

    async def _maybe_wf_auction(
        self, service: WarframeService, raw_args: str, *, page: int = 1
    ) -> tuple[str, str, Card] | None:
        cleaned = raw_args.strip()
        if not cleaned:
            return None
        parts = cleaned.split(maxsplit=1)
        head = parts[0].casefold()
        tail = parts[1].strip() if len(parts) > 1 else ""
        if head in {"赤毒", "赤毒武器", "赤毒巫妖"}:
            return "cd", tail, await service.lich_sister_market("lich", tail, page=page)
        if head in {"信条", "信条武器", "信条姐妹"}:
            return "xt", tail, await service.lich_sister_market("sister", tail, page=page)
        return None

    async def _status_text(self, service: WarframeService, stream_id: str) -> str:
        counts = await service.cached_counts()
        sub_count = 0
        foundry_count = 0
        if self._subscriptions is not None and stream_id:
            sub_count = len(await asyncio.to_thread(self._subscriptions.list_for_stream, stream_id))
        if self._foundry is not None and stream_id:
            foundry_count = len(await asyncio.to_thread(self._foundry.list_for_stream, stream_id))
        return (
            f"Milo bot · Warframe 助手 {VERSION} · 国际服 PC\n"
            f"本地物品索引：{service.item_count} 项"
            f" | 节点：{counts.get('nodes', 0)}"
            f" | 翻译：{counts.get('translations', 0)}"
            f" | 遗物：{counts.get('relics', 0)}\n"
            f"本会话订阅：{sub_count} 条 | 铸造提醒：{foundry_count} 条\n"
            "已支持市场统计与 /w 私聊、/翻译 /融合 /开核桃、订阅时段及铸造提醒。"
        )

    async def _maybe_subscription_command(
        self, raw_args: str, stream_id: str, user_id: str = ""
    ) -> Card | str | None:
        if not raw_args:
            return None
        compact = "".join(raw_args.split()).casefold()
        store = self._subscriptions
        if compact in {"订阅列表", "我的订阅", "subscriptions", "sublist"}:
            if store is None:
                raise QueryError("订阅存储尚未初始化，请稍后重试。")
            rules = await asyncio.to_thread(store.list_for_stream, stream_id)
            return build_subscription_list_card(rules)
        if compact == "铸造列表":
            if self._foundry is None:
                raise QueryError("铸造提醒存储尚未初始化，请稍后重试。")
            items = await asyncio.to_thread(self._foundry.list_for_stream, stream_id)
            return build_foundry_list_card(items, time.time())
        parts = raw_args.split(maxsplit=1)
        head = parts[0].casefold()
        tail = parts[1].strip() if len(parts) > 1 else ""
        if head in {"订阅", "subscribe", "sub"}:
            return await self._subscribe_action(store, stream_id, tail)
        if head in {"退订", "取消订阅", "unsubscribe", "unsub"}:
            return await self._unsubscribe_action(store, stream_id, tail)
        if head == "铸造提醒":
            return await self._foundry_add_action(stream_id, tail, user_id=user_id)
        if head == "取消铸造":
            return await self._foundry_cancel_action(stream_id, tail)
        return None

    async def _foundry_add_action(self, stream_id: str, tail: str, *, user_id: str = "") -> str:
        foundry = self._foundry
        if foundry is None:
            raise QueryError("铸造提醒存储尚未初始化，请稍后重试。")
        now = time.time()
        item_name, duration_sec, due_at = parse_foundry_spec(tail, now)
        record = await asyncio.to_thread(foundry.add, stream_id, item_name, due_at, user_id=user_id)
        hours = duration_sec / 3_600
        return (
            f"已添加铸造提醒 #{record.reminder_id}：【{record.item_name}】"
            f"（预计 {hours:g} 小时后提醒完成）。"
        )

    async def _foundry_cancel_action(self, stream_id: str, tail: str) -> str:
        foundry = self._foundry
        if foundry is None:
            raise QueryError("铸造提醒存储尚未初始化，请稍后重试。")
        cleaned = tail.strip().casefold()
        if not cleaned:
            raise QueryError("用法：/取消铸造 <编号|全部>，可先用 /铸造列表 查看编号。")
        if cleaned in {"全部", "所有", "all"}:
            removed = await asyncio.to_thread(foundry.remove_all, stream_id)
            return f"已清空本会话的铸造提醒（共 {removed} 项）。"
        num_text = cleaned.lstrip("#")
        if not num_text.isdecimal():
            raise QueryError("编号必须为数字或“全部”，例如：/取消铸造 1。")
        if await asyncio.to_thread(foundry.remove, stream_id, int(num_text)):
            return f"已取消铸造提醒 #{num_text}。"
        return f"未找到本会话的铸造提醒 #{num_text}。"

    async def _subscribe_action(
        self, store: SubscriptionStore | None, stream_id: str, tail: str
    ) -> Card | str:
        if not tail:
            return build_subscription_help_card()
        if store is None:
            raise QueryError("订阅存储尚未初始化，请稍后重试。")
        event_type, filters = parse_subscribe_spec(tail)
        rule = await asyncio.to_thread(store.upsert, stream_id, event_type, filters)
        label = SUBSCRIPTION_LABELS.get(rule.event_type, rule.event_type)
        summary = format_filter_summary(rule.event_type, rule.filters)
        return f"已保存当前会话的【{label}】订阅（条件：{summary}）。"

    async def _unsubscribe_action(
        self, store: SubscriptionStore | None, stream_id: str, tail: str
    ) -> str:
        if store is None:
            raise QueryError("订阅存储尚未初始化，请稍后重试。")
        target = parse_unsubscribe_target(tail)
        if target == "all":
            removed = await asyncio.to_thread(store.remove_all, stream_id)
            return f"已退订当前会话的全部订阅（共 {removed} 项）。"
        label = SUBSCRIPTION_LABELS.get(target, target)
        removed_one = await asyncio.to_thread(store.remove, stream_id, target)
        if removed_one:
            return f"已退订当前会话的【{label}】推送。"
        return f"当前会话未订阅【{label}】。"

    @Tool(
        "warframe_world_query",
        description=(
            "查询 Warframe 国际服 PC 的世界状态、时效总览、开放世界平原周期、双衍王境轮换、突击、"
            "执刑官猎杀、裂隙、警报、入侵、虚空商人、瓦奇娅圣装重生、每周科研、官方新闻、"
            "钢铁之路、午夜电波、每日特惠、1999 日历、三大平原赏金、仲裁、虚空遗物与开核桃推荐、"
            "中英翻译、融合步数计算、Mod升级消耗、杜卡德金银铜垃圾、紫卡倾向分析及个人铸造提醒。"
        ),
        brief_description="查询 Warframe 国际服 PC 世界状态、实用工具计算、遗物开核桃与铸造提醒",
        detailed_description=(
            "只返回文本数据，不直接向群聊发送图片。"
            "支持常见中文主题词；遗物传 topic='遗物' 搭配 keyword；"
            "开核桃传 topic='开核桃' 搭配 keyword='速刷|全部 白金|奸商'；"
            "翻译/融合/升级消耗/紫卡分析/铸造提醒/取消铸造均传对应 topic 搭配 keyword。"
        ),
        parameters=[
            ToolParameterInfo(
                name="topic",
                param_type=ToolParamType.STRING,
                description=(
                    "要查询的主题，可选如：时效、平原、轮换、双衍王境、警报、裂缝、钢铁裂缝、九重天裂缝、"
                    "突击、猎杀、入侵、奸商、瓦奇娅、科研、新闻、钢铁、电波、每日特惠、1999、"
                    "地球赏金、金星赏金、火卫二赏金、仲裁、仲裁表、遗物、开核桃、翻译、融合、升级消耗、"
                    "金垃圾、银垃圾、铜垃圾、紫卡分析、铸造提醒、铸造列表、取消铸造、状态"
                ),
                required=True,
            ),
            ToolParameterInfo(
                name="keyword",
                param_type=ToolParamType.STRING,
                description=(
                    "可选参数/关键词；例如 裂缝筛选词、遗物编号、翻译词条、融合百分比、"
                    "开核桃参数、紫卡分析词条或铸造提醒“物品名 时长”"
                ),
                required=False,
            ),
        ],
    )
    async def handle_world_tool(
        self,
        topic: str = "",
        keyword: str = "",
        stream_id: str = "",
        **kwargs: Any,
    ) -> dict[str, str]:
        """Answer natural-language world state and tool calculator questions cleanly."""
        del kwargs
        try:
            service = self._get_service()
            flags = parse_command_flags(keyword)
            cleaned_kw = flags.cleaned
            key = "".join(topic.split()).casefold()
            if key in {"状态", "status"} and not cleaned_kw:
                return {
                    "name": "warframe_world_query",
                    "content": await self._status_text(service, stream_id),
                }
            if key in {"铸造提醒", "铸造列表", "取消铸造"}:
                reply = await self._tool_foundry(key, cleaned_kw, stream_id)
                return {"name": "warframe_world_query", "content": reply}
            card = await service.resolve_world_card(topic, keyword=cleaned_kw, page=flags.page)
            if card is None:
                return {
                    "name": "warframe_world_query",
                    "content": (
                        f"暂不支持主题“{topic}”。可用主题：时效、平原、轮换、警报、裂缝、钢铁裂缝、"
                        "九重天裂缝、突击、猎杀、入侵、奸商、瓦奇娅、科研、新闻、钢铁、电波、"
                        "每日特惠、1999、三大赏金、仲裁、仲裁表、遗物、开核桃、翻译、融合、"
                        "升级消耗、金/银/铜垃圾、紫卡分析、铸造提醒。"
                    ),
                }
            return {"name": "warframe_world_query", "content": card.text()}
        except QueryError as exc:
            return {"name": "warframe_world_query", "content": f"查询失败：{exc}"}
        except Exception:
            self.ctx.logger.exception("warframe_world_query 执行失败")
            return {
                "name": "warframe_world_query",
                "content": "世界状态查询失败，请稍后重试或查看插件日志。",
            }

    async def _tool_foundry(self, key: str, cleaned_kw: str, stream_id: str) -> str:
        sid = stream_id.strip() or "_tool_default"
        if key == "铸造列表":
            if self._foundry is None:
                raise QueryError("铸造提醒存储尚未初始化，请稍后重试。")
            items = await asyncio.to_thread(self._foundry.list_for_stream, sid)
            return build_foundry_list_card(items, time.time()).text()
        if key == "铸造提醒":
            return await self._foundry_add_action(sid, cleaned_kw)
        return await self._foundry_cancel_action(sid, cleaned_kw)

    @Tool(
        "warframe_market_query",
        description=(
            "查询 Warframe Market 国际服 PC 在线玩家报价、近 48h/90d 成交均价、"
            "杜卡德金银铜垃圾或返回候选物品列表。"
        ),
        brief_description="查询 Warframe Market 物品价格、成交统计与金银铜垃圾",
        detailed_description="仅返回结构化报价摘要或候选物品列表，不向会话发送图片。",
        parameters=[
            ToolParameterInfo(
                name="item_name",
                param_type=ToolParamType.STRING,
                description=(
                    "物品中文名、英文名、Market slug、别名（如 电男p、Volt Prime 一套）"
                    "或 金垃圾 / 银垃圾 / 铜垃圾"
                ),
                required=True,
            ),
            ToolParameterInfo(
                name="order_type",
                param_type=ToolParamType.STRING,
                description="订单类型：sell（卖家，默认）或 buy（买家）",
                required=False,
                enum_values=["sell", "buy"],
                default="sell",
            ),
            ToolParameterInfo(
                name="max_rank",
                param_type=ToolParamType.BOOLEAN,
                description="是否仅筛选满级 Mod/赋能订单，默认 false",
                required=False,
                default=False,
            ),
        ],
    )
    async def handle_market_tool(
        self,
        item_name: str = "",
        order_type: str = "sell",
        max_rank: bool | str = False,
        stream_id: str = "",
        **kwargs: Any,
    ) -> dict[str, str]:
        """Answer natural-language Warframe Market price questions without sending images."""
        del stream_id
        resolved_name = _pick_tool_item_name(item_name, kwargs)
        flags = parse_command_flags(resolved_name)
        try:
            service = self._get_service()
            card = await service.market_for_tool(
                flags.cleaned,
                order_type=order_type,
                max_rank=_coerce_bool(max_rank),
                english=flags.english,
                page=flags.page,
            )
            if card.candidates:
                lines = [f"- {item.name}（{item.english_name}）" for item in card.candidates]
                content = (
                    f"找到 {len(card.candidates)} 个匹配物品，请使用完整名称重新查询：\n"
                    + "\n".join(lines)
                )
                return {"name": "warframe_market_query", "content": content}
            return {"name": "warframe_market_query", "content": card.text()}
        except QueryError as exc:
            return {"name": "warframe_market_query", "content": f"市场查询失败：{exc}"}
        except Exception:
            self.ctx.logger.exception("warframe_market_query 执行失败")
            return {
                "name": "warframe_market_query",
                "content": "市场查询失败，请稍后重试或查看插件日志。",
            }

    @Command("wf_market", pattern=r"(?i)^\s*(?:@\S+\s+)*/?wm(?:\s+(?P<query>.*))?$")
    async def handle_market(
        self,
        stream_id: str = "",
        matched_groups: dict[str, str | None] | None = None,
        **kwargs: Any,
    ) -> tuple[bool, str, int]:
        """Query online PC orders or ducat rankings without crossing candidate lists."""
        query = ((matched_groups or {}).get("query") or "").strip()

        async def _exec(service: WarframeService, user_id: str) -> tuple[bool, str, int]:
            flags = parse_command_flags(query)
            compact = "".join(flags.cleaned.split()).casefold()
            ducat_routes: tuple[tuple[str, Literal["gold", "silver", "copper"]], ...] = (
                ("金垃圾", "gold"),
                ("杜卡德金垃圾", "gold"),
                ("银垃圾", "silver"),
                ("杜卡德银垃圾", "silver"),
                ("铜垃圾", "copper"),
                ("杜卡德铜垃圾", "copper"),
            )
            for alias, kind in ducat_routes:
                if compact == alias:
                    self._pending.pop((stream_id, "wm"), None)
                    return await self._send_card(
                        await service.ducats(kind),
                        stream_id,
                        force_text=flags.text_only,
                    )
            parsed, selected = self._select_item(flags.cleaned, stream_id)
            card = await service.market(parsed, selected, english=flags.english, page=flags.page)
            return await self._finalize_card(
                "wm", parsed, card, stream_id, user_id, force_text=flags.text_only
            )

        return await self._run_command(stream_id, "市场查询", kwargs, _exec)

    @Command("wf_riven", pattern=r"(?i)^\s*(?:@\S+\s+)*/?wr(?:\s+(?P<query>.*))?$")
    async def handle_riven(
        self,
        stream_id: str = "",
        matched_groups: dict[str, str | None] | None = None,
        **kwargs: Any,
    ) -> tuple[bool, str, int]:
        """Search online PC/crossplay Riven auctions with isolated per-command candidates."""
        query = ((matched_groups or {}).get("query") or "").strip()

        async def _exec(service: WarframeService, user_id: str) -> tuple[bool, str, int]:
            flags = parse_command_flags(query)
            riven_query, selected = self._select_riven(flags.cleaned, stream_id)
            card = await service.riven_market(
                flags.cleaned,
                selected,
                parsed=riven_query if selected is not None else None,
                page=flags.page,
            )
            return await self._finalize_card(
                "wr", riven_query, card, stream_id, user_id, force_text=flags.text_only
            )

        return await self._run_command(stream_id, "紫卡拍卖查询", kwargs, _exec)

    @Command("wf_lich", pattern=r"(?i)^\s*(?:@\S+\s+)*/?cd(?:\s+(?P<query>.*))?$")
    async def handle_lich(
        self,
        stream_id: str = "",
        matched_groups: dict[str, str | None] | None = None,
        **kwargs: Any,
    ) -> tuple[bool, str, int]:
        """Search online PC/crossplay Kuva Lich auctions."""
        return await self._handle_lich_sister("lich", "cd", stream_id, matched_groups, kwargs)

    @Command("wf_sister", pattern=r"(?i)^\s*(?:@\S+\s+)*/?xt(?:\s+(?P<query>.*))?$")
    async def handle_sister(
        self,
        stream_id: str = "",
        matched_groups: dict[str, str | None] | None = None,
        **kwargs: Any,
    ) -> tuple[bool, str, int]:
        """Search online PC/crossplay Tenet Sister auctions."""
        return await self._handle_lich_sister("sister", "xt", stream_id, matched_groups, kwargs)

    @Command(
        "wf_whisper",
        pattern=r"(?i)^\s*(?:@\S+\s+)*(?:/w(?:\s+(?P<arg>.*))?|w\s+(?P<num>\d+)\s*)$",
    )
    async def handle_whisper(
        self,
        stream_id: str = "",
        matched_groups: dict[str, str | None] | None = None,
        **kwargs: Any,
    ) -> tuple[bool, str, int]:
        """Return ready-to-paste `/w` whisper copy text for the caller's latest query."""
        if not stream_id:
            return False, "缺少当前会话 ID", 2
        user_id = _extract_user_id(kwargs)
        groups = matched_groups or {}
        arg = (groups.get("arg") or groups.get("num") or "").strip()
        try:
            reply = self._whispers.reply_for(stream_id, user_id, arg)
            return await self._send_text(reply, stream_id)
        except QueryError as exc:
            return await self._send_text(str(exc), stream_id, success=False)

    async def _run_command(
        self,
        stream_id: str,
        action_label: str,
        kwargs: dict[str, Any],
        runner: Callable[[WarframeService, str], Awaitable[tuple[bool, str, int]]],
    ) -> tuple[bool, str, int]:
        if not stream_id:
            return False, "缺少当前会话 ID", 2
        user_id = _extract_user_id(kwargs)
        try:
            service = self._get_service()
            return await runner(service, user_id)
        except QueryError as exc:
            return await self._send_text(str(exc), stream_id, success=False)
        except Exception:
            self.ctx.logger.exception("Warframe %s失败", action_label)
            return await self._send_text(
                f"{action_label}失败，请稍后重试并检查插件日志。", stream_id, success=False
            )

    async def _handle_lich_sister(
        self,
        kind: Literal["lich", "sister"],
        cmd: str,
        stream_id: str,
        matched_groups: dict[str, str | None] | None,
        kwargs: dict[str, Any],
    ) -> tuple[bool, str, int]:
        label = "赤毒" if kind == "lich" else "信条"
        query = ((matched_groups or {}).get("query") or "").strip()

        async def _exec(service: WarframeService, user_id: str) -> tuple[bool, str, int]:
            flags = parse_command_flags(query)
            keyword, selected = self._select_lich_sister(flags.cleaned, stream_id, cmd)
            card = await service.lich_sister_market(kind, keyword, selected, page=flags.page)
            return await self._finalize_card(
                cmd, keyword, card, stream_id, user_id, force_text=flags.text_only
            )

        return await self._run_command(stream_id, f"{label}拍卖查询", kwargs, _exec)

    async def _finalize_card(
        self,
        cmd: str,
        query: Any,
        card: Card,
        stream_id: str,
        user_id: str,
        *,
        force_text: bool = False,
    ) -> tuple[bool, str, int]:
        self._pending.pop((stream_id, cmd), None)
        if card.candidates:
            self._remember_candidates(stream_id, cmd, query, card.candidates)
        if card.whispers:
            self._whispers.remember(stream_id, user_id, cmd, card.whispers)
        return await self._send_card(card, stream_id, force_text=force_text)

    def _get_pending_item(
        self, stream_id: str, cmd: str, number: int
    ) -> tuple[PendingSelection, Item]:
        pending = self._pending.get((stream_id, cmd))
        if pending is None or pending.expires_at <= time.monotonic():
            self._pending.pop((stream_id, cmd), None)
            raise QueryError(f"当前会话没有有效候选，请先用 /{cmd} 重新查询。")
        if not 1 <= number <= len(pending.items):
            raise QueryError(f"候选编号应为 1～{len(pending.items)}。")
        return pending, pending.items[number - 1]

    def _select_item(self, raw: str, stream_id: str) -> tuple[MarketQuery, Item | None]:
        if not raw.isdecimal():
            return parse_query(raw), None
        pending, item = self._get_pending_item(stream_id, "wm", int(raw))
        return cast(MarketQuery, pending.query), item

    def _select_riven(self, raw: str, stream_id: str) -> tuple[RivenQuery, Item | None]:
        choice = extract_candidate_choice(raw)
        if choice is None:
            return parse_riven_query(raw), None
        number, tail = choice
        pending, item = self._get_pending_item(stream_id, "wr", number)
        base = cast(RivenQuery, pending.query)
        if not tail:
            return base, item
        return _merge_riven_tail(base, tail), item

    def _select_lich_sister(self, raw: str, stream_id: str, cmd: str) -> tuple[str, Item | None]:
        if not raw.isdecimal():
            return raw, None
        pending, item = self._get_pending_item(stream_id, cmd, int(raw))
        return str(pending.query), item

    def _remember_candidates(self, stream_id: str, cmd: str, query: Any, items: list[Item]) -> None:
        now = time.monotonic()
        self._pending = {
            key: value for key, value in self._pending.items() if value.expires_at > now
        }
        if len(self._pending) >= 128:
            self._pending.pop(next(iter(self._pending)))
        self._pending[(stream_id, cmd)] = PendingSelection(query, items, now + 60)

    async def _send_text(
        self, text: str, stream_id: str, *, success: bool = True
    ) -> tuple[bool, str, int]:
        sent = await self.ctx.send.text(text, stream_id)
        ok = sent is True or isinstance(sent, dict) and bool(sent.get("sent"))
        return success and ok, "已回复" if ok else "消息发送失败", 2

    async def _send_card(
        self, card: Card, stream_id: str, *, force_text: bool = False
    ) -> tuple[bool, str, int]:
        if force_text or self.settings.output_mode == "text":
            return await self._send_text(card.text(), stream_id)
        try:
            image = await asyncio.to_thread(
                render_card,
                card,
                font_path=self.settings.font_path,
            )
            sent = await self.ctx.send.image(base64.b64encode(image).decode("ascii"), stream_id)
            if sent is True or isinstance(sent, dict) and bool(sent.get("sent")):
                return True, "已发送查询卡片", 2
            self.ctx.logger.warning("图片发送未成功，尝试文字回复")
        except (ValueError, OSError):
            self.ctx.logger.warning("卡片生成失败，尝试文字回复", exc_info=True)
        return await self._send_text(card.text(), stream_id)


def _merge_riven_tail(base: RivenQuery, tail: str) -> RivenQuery:
    cleaned = tail.strip()
    if cleaned.startswith("-"):
        parsed = parse_riven_query(f"__sel__-{cleaned.lstrip('-')}")
        return RivenQuery(
            base.weapon, parsed.positive or base.positive, parsed.negative or base.negative
        )
    parsed = parse_riven_query(f"__sel__ {cleaned}")
    if not parsed.positive and not parsed.negative:
        return RivenQuery(base.weapon, cleaned, base.negative)
    return RivenQuery(
        base.weapon,
        parsed.positive or base.positive,
        parsed.negative or base.negative,
        parsed.reroll or base.reroll,
        parsed.polarity or base.polarity,
        parsed.stat_count or base.stat_count,
        parsed.max_price if parsed.max_price is not None else base.max_price,
    )


def _extract_user_id(kwargs: dict[str, Any]) -> str:
    for key in ("user_id", "sender_id"):
        val = kwargs.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    msg = kwargs.get("message")
    msg_info = (
        msg.get("message_info") if isinstance(msg, dict) else getattr(msg, "message_info", None)
    )
    user_info = (
        msg_info.get("user_info")
        if isinstance(msg_info, dict)
        else getattr(msg_info, "user_info", None)
    )
    uid = (
        user_info.get("user_id")
        if isinstance(user_info, dict)
        else getattr(user_info, "user_id", None)
    )
    if uid is not None and str(uid).strip():
        return str(uid).strip()
    return "_anonymous"


def _pick_tool_item_name(item_name: str, kwargs: dict[str, Any]) -> str:
    if item_name.strip():
        return item_name.strip()
    for alias in ("query", "item", "keyword", "name"):
        value = kwargs.get(alias)
        if isinstance(value, str):
            text = value.strip()
            if text:
                return str(text)
    return ""


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().casefold() in {"1", "true", "yes", "on", "是", "满级"}
    return bool(value)
