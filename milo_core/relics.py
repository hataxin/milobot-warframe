"""Void Relic lookup by relic name, reward name or alias."""

from __future__ import annotations

from .card_model import Card
from .dictionary import RelicEntry
from .errors import QueryError
from .market import normalize
from .worldstate import QueryMeta, subtitle

RELIC_RENDER_LIMIT = 30

_TIER_ONLY_KEYS = frozenset(
    {
        "古纪",
        "前纪",
        "中纪",
        "后纪",
        "安魂",
        "lith",
        "meso",
        "neo",
        "axi",
        "requiem",
        "guji",
        "qianji",
        "zhongji",
        "houji",
        "anhun",
    }
)


def is_tier_only(keyword: str) -> bool:
    """Reject tier-only queries like '中纪' or 'zhongji' that match hundreds of relics."""
    cleaned = "".join(keyword.split()).casefold()
    for suffix in ("遗物", "核桃", "relic"):
        cleaned = cleaned.removesuffix(suffix)
    return cleaned in _TIER_ONLY_KEYS


def _token_variants(token: str, aliases: dict[str, str]) -> list[str]:
    base = normalize(token).removesuffix("遗物")
    if not base:
        return []
    variants = [base]
    alias_base = base.removesuffix("prime")
    alias = aliases.get(alias_base) or aliases.get(base)
    if alias is not None and alias:
        aliased = normalize(alias)
        if base.endswith("prime") and "prime" not in aliased:
            aliased += "prime"
        if aliased and aliased not in variants:
            variants.append(aliased)
    return variants


def _relic_name_key(relic: RelicEntry) -> str:
    return normalize(relic.name).removesuffix("遗物")


def _matches_all_tokens(relic: RelicEntry, token_groups: list[list[str]]) -> bool:
    relic_key = _relic_name_key(relic)
    reward_keys = [normalize(r.name) for r in relic.rewards]
    if all(any(v in relic_key for v in group) for group in token_groups):
        return True
    return any(
        all(any(v in r_key for v in group) for group in token_groups) for r_key in reward_keys
    )


def search_relics(
    keyword: str, relics: list[RelicEntry], aliases: dict[str, str]
) -> list[RelicEntry]:
    """Resolve relics by exact relic name, exact reward name, or token match."""
    whole_keys = _token_variants(keyword, aliases)
    if not whole_keys:
        return []
    exact_name = [relic for relic in relics if _relic_name_key(relic) in whole_keys]
    if exact_name:
        return sorted(exact_name, key=lambda r: r.name)
    exact_reward = [
        relic
        for relic in relics
        if any(normalize(reward.name) in whole_keys for reward in relic.rewards)
    ]
    if exact_reward:
        return sorted(exact_reward, key=lambda r: r.name)
    token_groups = [group for part in keyword.split() if (group := _token_variants(part, aliases))]
    if not token_groups:
        return []
    partial = [relic for relic in relics if _matches_all_tokens(relic, token_groups)]
    return sorted(partial, key=lambda r: r.name)


def build_relic_help_card() -> Card:
    """Build a usage guide Card when `/遗物` is invoked without a keyword."""
    return Card(
        "遗物查询帮助",
        [
            ("按遗物名", "/遗物 中纪 A1", "精确查询指定遗物及其掉落奖励"),
            ("按奖励名", "/遗物 Volt Prime", "列出包含该奖励的所有遗物"),
            ("按别名", "/遗物 电男", "支持作者词典别名与 Prime 简写"),
            ("别名指令", "/核桃 后纪 S5", "/核桃 与 /遗物 用法相同"),
        ],
        "请补充遗物编号或奖励物品名称，避免仅输入档位（古纪/前纪/中纪/后纪/安魂）",
        columns=("方式", "示例指令", "说明"),
        kind="relic_help",
        footer_note="单次最多展示 30 个匹配遗物",
    )


def build_relics_card(keyword: str, matches: list[RelicEntry], meta: QueryMeta) -> Card:
    """Build the Void Relic results Card, capped at 30 rows."""
    if not matches:
        raise QueryError(f"未找到与“{keyword}”相关的遗物，请尝试完整遗物编号或奖励名称。")
    shown = matches[:RELIC_RENDER_LIMIT]
    rows: list[tuple[str, ...]] = []
    for relic in shown:
        common = "\n".join(r.display_name for r in relic.rewards if r.rarity == "COMMON") or "—"
        uncommon = "\n".join(r.display_name for r in relic.rewards if r.rarity == "UNCOMMON") or "—"
        rare = (
            "\n".join(r.display_name for r in relic.rewards if r.rarity in {"RARE", "LEGENDARY"})
            or "—"
        )
        rows.append((relic.name, common, uncommon, rare))
    extra = (
        f"共 {len(matches)} 个遗物（仅显示前 {len(shown)} 个）"
        if len(matches) > len(shown)
        else f"共 {len(matches)} 个遗物"
    )
    return Card(
        "遗物查询",
        rows,
        subtitle(meta, extra),
        columns=("遗物名称", "常见 (铜)", "罕见 (银)", "稀有 (金)"),
        kind="relics",
        highlight=f"关键词：{keyword}",
    )
