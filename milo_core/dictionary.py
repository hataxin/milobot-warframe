"""On-demand static dictionaries and translations cached in plugin SQLite."""

from __future__ import annotations

import asyncio
import lzma
import re
from dataclasses import dataclass
from typing import Any

from .client import MARKET_URL, PUBLIC_EXPORT_INDEX_URL, PUBLIC_EXPORT_MANIFEST_URL, DataClient
from .errors import QueryError
from .market import Item, parse_items

INDEX_TTL = 86_400
DICT_TTL = 604_800
_MARKUP_RE = re.compile(r"<[^<>]*>")
_EN_NAME_RE = re.compile(r"（英文：(.+?)）")

_EXPORT_SOURCES: tuple[tuple[str, str], ...] = (
    ("ExportCustoms", "ExportCustoms"),
    ("ExportDrones", "ExportDrones"),
    ("ExportFlavour", "ExportFlavour"),
    ("ExportGear", "ExportGear"),
    ("ExportKeys", "ExportKeys"),
    ("ExportRelicArcane", "ExportRelicArcane"),
    ("ExportResources", "ExportResources"),
    ("ExportSentinels", "ExportSentinels"),
    ("ExportSortieRewards", "ExportOther"),
    ("ExportUpgrades", "ExportUpgrades"),
    ("ExportWarframes", "ExportWarframes"),
    ("ExportWeapons", "ExportWeapons"),
)

_PART_FALLBACKS: dict[str, str] = {
    "Blueprint": "蓝图",
    "Systems": "系统",
    "Chassis": "机体",
    "Helmet": "头部神经光元",
    "Neuroptics": "头部神经光元",
}


@dataclass(frozen=True)
class NodeInfo:
    """Star-chart node metadata."""

    name: str
    system: str = ""
    mission_index: int | None = None
    faction_index: int | None = None

    @property
    def display_name(self) -> str:
        """Return localized 'Node(System)' display text."""
        return f"{self.name}({self.system})" if self.system else self.name


@dataclass(frozen=True)
class NightwaveChallenge:
    """Nightwave challenge definition from ExportSortieRewards."""

    name: str
    desc: str
    standing: int
    required: int

    @property
    def formatted_desc(self) -> str:
        """Replace the |COUNT| placeholder with the required count."""
        return self.desc.replace("|COUNT|", str(self.required))


@dataclass(frozen=True)
class PoolReward:
    """One reward entry inside a bounty reward pool."""

    item: str
    rarity: str
    count: int

    @property
    def display_name(self) -> str:
        """Render count placeholders inside reward text."""
        if "|COUNT|" in self.item:
            return self.item.replace("|COUNT|", str(self.count))
        return self.item


@dataclass(frozen=True)
class RelicReward:
    """One drop inside a Void Relic."""

    name: str
    rarity: str
    count: int

    @property
    def display_name(self) -> str:
        """Include drop count prefix when greater than 1."""
        return f"{self.count}x {self.name}" if self.count > 1 else self.name


@dataclass(frozen=True)
class RelicEntry:
    """A Void Relic and its translated drop table."""

    unique_name: str
    name: str
    rewards: tuple[RelicReward, ...]


@dataclass(frozen=True)
class RivenStatInfo:
    """Warframe Market riven stat definition from market_riven_tion.json."""

    url_name: str
    effect: str
    units: str = ""
    positive_is_negative: bool = False
    negative_only: bool = False


@dataclass(frozen=True)
class RivenTrendEntry:
    """Base riven stat ranges by weapon category from riven_analyse_trend.json."""

    name: str
    rifle: float = 0.0
    shotgun: float = 0.0
    pistol: float = 0.0
    melee: float = 0.0
    archwing: float = 0.0


@dataclass(frozen=True)
class WeaponMeta:
    """Weapon disposition and category metadata from ExportWeapons."""

    unique_name: str
    name: str
    english_name: str
    product_category: str
    omega_attenuation: float
    description: str = ""


def strip_markup(text: str) -> str:
    """Remove Warframe inline <...> markup tags."""
    return _MARKUP_RE.sub("", text).strip()


def split_camel_case(text: str) -> str:
    """Split CamelCase identifiers into title-cased words."""
    if not text:
        return text
    spaced = re.sub(r"(?<=\D)(?=[A-Z])", " ", text)
    return spaced.title()


def decompress_lzma(raw: bytes) -> bytes:
    """Decode standard LZMA or DE's explicit-size + EOS LZMA1 streams."""
    try:
        return lzma.decompress(raw)
    except lzma.LZMAError:
        if len(raw) < 13:
            raise QueryError("导出索引压缩格式无效，请稍后重试。") from None
        patched = raw[:5] + b"\xff" * 8 + raw[13:]
        try:
            return lzma.decompress(patched, format=lzma.FORMAT_ALONE)
        except lzma.LZMAError as exc:
            raise QueryError("导出索引解压失败，请稍后重试。") from exc


def parse_export_index(raw: bytes) -> dict[str, str]:
    """Parse index_zh.txt.lzma into {base_prefix: 'filename!hash'}."""
    text = decompress_lzma(raw).decode("utf-8")
    mapping: dict[str, str] = {}
    for line in text.splitlines():
        entry = line.strip()
        if "!" not in entry:
            continue
        filename, _, _ = entry.partition("!")
        prefix = filename.split("_", 1)[0].removesuffix(".json")
        if prefix:
            mapping[prefix] = entry
    if not mapping:
        raise QueryError("官方导出索引为空，请稍后重试。")
    return mapping


def extract_weapon_english_name(item: dict[str, Any]) -> str:
    """Extract normalized English weapon name from localized description."""
    desc = item.get("description")
    if not isinstance(desc, str):
        return ""
    match = _EN_NAME_RE.search(desc)
    if not match:
        return ""
    english = re.sub(r"\s+", " ", match.group(1)).strip().casefold()
    name = str(item.get("name") or "")
    if name.upper().startswith("MK1-") and not english.startswith("mk1-"):
        english = "mk1-" + english
    return english


class TranslationIndex:
    """In-memory exact + last-3-segment suffix lookup index."""

    def __init__(self, names: dict[str, str], descs: dict[str, str]) -> None:
        self.names = names
        self.descs = descs
        self._suffix3: dict[str, str] = {}
        self._suffix2: dict[str, str] = {}
        self._suffix1: dict[str, str] = {}
        for unique_name, name in names.items():
            parts = [part for part in unique_name.split("/") if part]
            if len(parts) >= 3:
                self._suffix3.setdefault("/".join(parts[-3:]), name)
            if len(parts) >= 2:
                self._suffix2.setdefault("/".join(parts[-2:]), name)
            if parts:
                self._suffix1.setdefault(parts[-1], name)

    def translate(self, path: str) -> str:
        """Translate a Lotus path by exact key or trailing path segments."""
        if not path:
            return path
        if (hit := self.names.get(path)) is not None and hit:
            return hit
        parts = [part for part in path.split("/") if part]
        for size, table in ((3, self._suffix3), (2, self._suffix2), (1, self._suffix1)):
            if (
                len(parts) >= size
                and (hit := table.get("/".join(parts[-size:]))) is not None
                and hit
            ):
                return hit
        return path

    def describe(self, path: str) -> str:
        """Return supplemental Chinese description if available."""
        return self.descs.get(path, "")


def _fallback_reward_name(path: str) -> str:
    segment = path.rsplit("/", 1)[-1] if "/" in path else path
    readable = split_camel_case(segment)
    for english, chinese in _PART_FALLBACKS.items():
        readable = readable.replace(english, chinese)
    return readable


def _int_or_none(value: Any) -> int | None:
    return value if type(value) is int else None


def _clean_desc(value: Any) -> str:
    if isinstance(value, list):
        return str(value[0]) if value else ""
    return str(value) if value is not None else ""


class DictionaryService:
    """Lazy, SQLite-backed static Warframe dictionaries."""

    def __init__(self, client: DataClient) -> None:
        self.client = client
        self._translation_index: TranslationIndex | None = None
        self._translation_stamp: float = 0.0

    async def export_index(self) -> dict[str, str]:
        """Fetch and cache the PublicExport file manifest mapping."""

        async def _build() -> dict[str, str]:
            raw = await self.client.fetch_bytes(PUBLIC_EXPORT_INDEX_URL)
            return parse_export_index(raw)

        cached = await self.client.get_or_build("export:index:zh", INDEX_TTL, _build)
        return dict(cached.body)

    async def _fetch_export_json(self, index: dict[str, str], prefix: str) -> dict[str, Any]:
        entry = index.get(prefix)
        if entry is None or not entry:
            raise QueryError(f"官方导出索引缺少 {prefix}。")
        data = await self.client.fetch_json(PUBLIC_EXPORT_MANIFEST_URL + entry)
        if not isinstance(data, dict):
            raise QueryError(f"{prefix} 导出格式无效。")
        return data

    async def nodes(self) -> dict[str, NodeInfo]:
        """Load star-chart nodes from ExportRegions plus supplemental CDN nodes."""

        async def _build() -> dict[str, dict[str, Any]]:
            index = await self.export_index()
            raw = await self._fetch_export_json(index, "ExportRegions")
            merged: dict[str, dict[str, Any]] = {}
            for item in raw.get("ExportRegions", []):
                _add_node_record(merged, item, overwrite=True)
            try:
                cdn_nodes = await self.client.fetch_cdn_json("nodes.json")
            except QueryError:
                cdn_nodes = []
            if isinstance(cdn_nodes, list):
                for item in cdn_nodes:
                    _add_node_record(merged, item, overwrite=False)
            if not merged:
                raise QueryError("星图节点词典为空，请稍后重试。")
            return merged

        cached = await self.client.get_or_build("dict:nodes:v1", DICT_TTL, _build)
        return {
            key: NodeInfo(
                str(row.get("name") or key),
                str(row.get("system") or ""),
                _int_or_none(row.get("mission")),
                _int_or_none(row.get("faction")),
            )
            for key, row in cached.body.items()
            if isinstance(row, dict)
        }

    async def nightwave(self) -> dict[str, NightwaveChallenge]:
        """Load Nightwave challenge metadata from ExportSortieRewards."""

        async def _build() -> dict[str, dict[str, Any]]:
            index = await self.export_index()
            raw = await self._fetch_export_json(index, "ExportSortieRewards")
            challenges = (raw.get("ExportNightwave") or {}).get("challenges", [])
            result: dict[str, dict[str, Any]] = {}
            for item in challenges:
                if not isinstance(item, dict) or not item.get("uniqueName"):
                    continue
                result[str(item["uniqueName"])] = {
                    "name": str(item.get("name") or ""),
                    "desc": str(item.get("description") or ""),
                    "standing": int(item.get("standing") or 0),
                    "required": int(item.get("required") or 1),
                }
            if not result:
                raise QueryError("午夜电波词典为空，请稍后重试。")
            return result

        cached = await self.client.get_or_build("dict:nightwave:v1", DICT_TTL, _build)
        return {
            key: NightwaveChallenge(
                str(row.get("name") or key),
                str(row.get("desc") or ""),
                int(row.get("standing") or 0),
                int(row.get("required") or 1),
            )
            for key, row in cached.body.items()
            if isinstance(row, dict)
        }

    async def weapons_en(self) -> dict[str, str]:
        """Load casefolded English -> Chinese weapon name mapping."""

        async def _build() -> dict[str, str]:
            index = await self.export_index()
            raw = await self._fetch_export_json(index, "ExportWeapons")
            result: dict[str, str] = {}
            for section in ("ExportWeapons", "ExportRailjackWeapons"):
                for item in raw.get(section, []):
                    if not isinstance(item, dict) or not item.get("name"):
                        continue
                    english = extract_weapon_english_name(item)
                    if english:
                        result.setdefault(english, str(item["name"]))
            return result

        cached = await self.client.get_or_build("dict:weapons_en:v1", DICT_TTL, _build)
        return {str(k): str(v) for k, v in cached.body.items()}

    async def translations(self) -> TranslationIndex:
        """Load merged PublicExport + CDN state translations."""

        async def _build() -> dict[str, dict[str, str]]:
            names: dict[str, str] = {}
            descs: dict[str, str] = {}
            try:
                index = await self.export_index()
                results = await asyncio.gather(
                    *(self._fetch_export_json(index, prefix) for prefix, _ in _EXPORT_SOURCES),
                    return_exceptions=True,
                )
                for (_, json_key), payload in zip(_EXPORT_SOURCES, results, strict=True):
                    if isinstance(payload, dict):
                        _collect_export_names(names, payload.get(json_key, []))
            except QueryError:
                pass
            try:
                cdn_rows = await self.client.fetch_cdn_json("state_translation.json")
            except QueryError:
                cdn_rows = []
            if isinstance(cdn_rows, list):
                _collect_cdn_translations(names, descs, cdn_rows)
            if not names:
                raise QueryError("状态翻译词典暂不可用，请稍后重试。")
            return {"names": names, "descs": descs}

        cached = await self.client.get_or_build("dict:translations:v1", DICT_TTL, _build)
        if self._translation_index is None or self._translation_stamp != cached.fetched_at:
            body = cached.body
            self._translation_index = TranslationIndex(
                {str(k): str(v) for k, v in body.get("names", {}).items()},
                {str(k): str(v) for k, v in body.get("descs", {}).items()},
            )
            self._translation_stamp = cached.fetched_at
        return self._translation_index

    async def reward_pool(self) -> dict[str, list[PoolReward]]:
        """Load CDN bounty reward pools with translated item names."""

        async def _build() -> dict[str, list[dict[str, Any]]]:
            raw = await self.client.fetch_cdn_json("reward_pool.json")
            if not isinstance(raw, list):
                raise QueryError("赏金奖励池格式无效。")
            try:
                trans = await self.translations()
            except QueryError:
                trans = TranslationIndex({}, {})
            pools: dict[str, list[dict[str, Any]]] = {}
            for entry in raw:
                if not isinstance(entry, dict) or not entry.get("uniqueName"):
                    continue
                items: list[dict[str, Any]] = []
                for reward in entry.get("rewards", []):
                    if not isinstance(reward, dict) or not reward.get("item"):
                        continue
                    item_text = str(reward["item"])
                    if item_text.startswith("/"):
                        item_text = trans.translate(item_text)
                    items.append(
                        {
                            "item": strip_markup(item_text),
                            "rarity": str(reward.get("rarity") or "COMMON"),
                            "count": int(reward.get("itemCount") or 1),
                        }
                    )
                pools[str(entry["uniqueName"])] = items
            return pools

        cached = await self.client.get_or_build("dict:reward_pool:v1", DICT_TTL, _build)
        return {
            key: [
                PoolReward(str(r["item"]), str(r["rarity"]), int(r["count"]))
                for r in rows
                if isinstance(r, dict)
            ]
            for key, rows in cached.body.items()
        }

    async def arbitration_tiers(self) -> dict[str, str]:
        """Load S/A/B/C/D/F arbitration node tiers from CDN."""

        async def _build() -> dict[str, str]:
            raw = await self.client.fetch_cdn_json("arbitration_tiers.json")
            if not isinstance(raw, list) or not raw:
                raise QueryError("仲裁分级数据不可用，请稍后重试。")
            tiers: dict[str, str] = {}
            for row in raw:
                if not isinstance(row, dict):
                    continue
                key = str(row.get("key") or "").strip()
                if key:
                    tiers[key] = str(row.get("tier") or "F").strip().upper()
            if not tiers:
                raise QueryError("仲裁分级数据为空，请稍后重试。")
            return tiers

        cached = await self.client.get_or_build("dict:arbitration_tiers:v1", DICT_TTL, _build)
        return {str(k): str(v) for k, v in cached.body.items()}

    async def relics(self) -> list[RelicEntry]:
        """Load non-secret Void Relics with translated rewards."""

        async def _build() -> list[dict[str, Any]]:
            index = await self.export_index()
            raw = await self._fetch_export_json(index, "ExportRelicArcane")
            try:
                trans = await self.translations()
            except QueryError:
                trans = TranslationIndex({}, {})
            entries: list[dict[str, Any]] = []
            seen_names: set[str] = set()
            for item in raw.get("ExportRelicArcane", []):
                if not isinstance(item, dict) or item.get("codexSecret"):
                    continue
                name = str(item.get("name") or "").strip()
                raw_rewards = item.get("relicRewards")
                if not name or name in seen_names or not isinstance(raw_rewards, list):
                    continue
                if not raw_rewards:
                    continue
                seen_names.add(name)
                rewards = [_decode_relic_reward(rr, trans) for rr in raw_rewards]
                entries.append(
                    {
                        "id": str(item.get("uniqueName") or name),
                        "name": name,
                        "rewards": [r for r in rewards if r is not None],
                    }
                )
            if not entries:
                raise QueryError("遗物数据为空，请稍后重试。")
            return entries

        cached = await self.client.get_or_build("dict:relics:v1", DICT_TTL, _build)
        return [
            RelicEntry(
                str(row["id"]),
                str(row["name"]),
                tuple(RelicReward(str(r[0]), str(r[1]), int(r[2])) for r in row.get("rewards", [])),
            )
            for row in cached.body
            if isinstance(row, dict)
        ]

    async def _market_weapon_catalog(self, cache_key: str, path: str) -> list[Item]:
        async def _build() -> list[dict[str, Any]]:
            body = await self.client.fetch_market_json(MARKET_URL + path)
            parsed = parse_items(body)
            return [
                {
                    "id": item.item_id,
                    "slug": item.slug,
                    "name": item.name,
                    "en": item.english_name,
                }
                for item in parsed
            ]

        cached = await self.client.get_or_build(cache_key, DICT_TTL, _build)
        return [
            Item(str(row["id"]), str(row["slug"]), str(row["name"]), str(row["en"]))
            for row in cached.body
            if isinstance(row, dict)
        ]

    async def riven_weapons(self) -> list[Item]:
        """Load Warframe Market v2 riven-eligible weapons."""
        return await self._market_weapon_catalog("dict:riven_weapons:v1", "/riven/weapons")

    async def lich_weapons(self) -> list[Item]:
        """Load Warframe Market v2 Kuva Lich weapons."""
        return await self._market_weapon_catalog("dict:lich_weapons:v1", "/lich/weapons")

    async def sister_weapons(self) -> list[Item]:
        """Load Warframe Market v2 Tenet Sister weapons."""
        return await self._market_weapon_catalog("dict:sister_weapons:v1", "/sister/weapons")

    async def riven_tions(self) -> tuple[list[RivenStatInfo], dict[str, str]]:
        """Load riven stat translation metadata and CN aliases from CDN."""

        async def _build() -> dict[str, Any]:
            raw_stats = await self.client.fetch_cdn_json("market_riven_tion.json")
            if not isinstance(raw_stats, list) or not raw_stats:
                raise QueryError("紫卡词条词典不可用，请稍后重试。")
            try:
                raw_aliases = await self.client.fetch_cdn_json("market_riven_tion_alias.json")
            except QueryError:
                raw_aliases = []
            stats = [
                {
                    "url": str(row.get("url_name") or "").strip(),
                    "effect": str(row.get("effect") or "").strip(),
                    "units": str(row.get("units") or row.get("unit") or "").strip(),
                    "pin": str(row.get("positive_is_negative") or "0") in {"1", "true", "True"},
                    "neg_only": str(row.get("negative_only") or "0") in {"1", "true", "True"},
                }
                for row in raw_stats
                if isinstance(row, dict) and row.get("url_name") and row.get("effect")
            ]
            aliases: dict[str, str] = {}
            if isinstance(raw_aliases, list):
                for row in raw_aliases:
                    if isinstance(row, dict) and row.get("cn") and row.get("en"):
                        aliases[str(row["cn"]).strip().casefold()] = str(row["en"]).strip()
            return {"stats": stats, "aliases": aliases}

        cached = await self.client.get_or_build("dict:riven_tions:v1", DICT_TTL, _build)
        stats = [
            RivenStatInfo(
                str(r["url"]),
                str(r["effect"]),
                str(r.get("units") or ""),
                bool(r.get("pin")),
                bool(r.get("neg_only")),
            )
            for r in cached.body.get("stats", [])
            if isinstance(r, dict)
        ]
        aliases = {str(k): str(v) for k, v in cached.body.get("aliases", {}).items()}
        return stats, aliases

    async def riven_analyse_trends(self) -> dict[str, RivenTrendEntry]:
        """Load riven stat numeric trend baselines from CDN."""

        async def _build() -> dict[str, dict[str, float]]:
            raw = await self.client.fetch_cdn_json("riven_analyse_trend.json")
            if not isinstance(raw, list) or not raw:
                raise QueryError("紫卡倾向基准数据不可用，请稍后重试。")
            trends: dict[str, dict[str, float]] = {}
            for row in raw:
                if not isinstance(row, dict) or not row.get("name"):
                    continue
                trends[str(row["name"]).strip()] = {
                    "rifle": float(row.get("rifle") or 0.0),
                    "shotgun": float(row.get("shotgun") or 0.0),
                    "pistol": float(row.get("pistol") or 0.0),
                    "melee": float(row.get("melle") or row.get("melee") or 0.0),
                    "archwing": float(row.get("archwing") or 0.0),
                }
            if not trends:
                raise QueryError("紫卡倾向基准数据为空，请稍后重试。")
            return trends

        cached = await self.client.get_or_build("dict:riven_analyse_trend:v1", DICT_TTL, _build)
        return {
            name: RivenTrendEntry(
                name,
                float(row.get("rifle") or 0.0),
                float(row.get("shotgun") or 0.0),
                float(row.get("pistol") or 0.0),
                float(row.get("melee") or 0.0),
                float(row.get("archwing") or 0.0),
            )
            for name, row in cached.body.items()
            if isinstance(row, dict)
        }

    async def weapons_meta(self) -> list[WeaponMeta]:
        """Load weapon disposition and product category metadata from ExportWeapons."""

        async def _build() -> list[dict[str, Any]]:
            index = await self.export_index()
            raw = await self._fetch_export_json(index, "ExportWeapons")
            items: list[dict[str, Any]] = []
            for entry in raw.get("ExportWeapons", []):
                if not isinstance(entry, dict) or not entry.get("name"):
                    continue
                omega = entry.get("omegaAttenuation")
                items.append(
                    {
                        "id": str(entry.get("uniqueName") or entry["name"]),
                        "name": strip_markup(str(entry["name"])),
                        "en": extract_weapon_english_name(entry),
                        "cat": str(entry.get("productCategory") or ""),
                        "omega": float(omega) if isinstance(omega, (int, float)) else 0.0,
                        "desc": str(entry.get("description") or ""),
                    }
                )
            if not items:
                raise QueryError("武器倾向元数据为空，请稍后重试。")
            return items

        cached = await self.client.get_or_build("dict:weapons_meta:v1", DICT_TTL, _build)
        return [
            WeaponMeta(
                str(r["id"]),
                str(r["name"]),
                str(r.get("en") or ""),
                str(r.get("cat") or ""),
                float(r.get("omega") or 0.0),
                str(r.get("desc") or ""),
            )
            for r in cached.body
            if isinstance(r, dict)
        ]

    async def cached_counts(self) -> dict[str, int]:
        """Read local cached dictionary sizes without hitting the network."""
        counts: dict[str, int] = {}
        nodes_cached = await asyncio.to_thread(self.client.cache.get, "dict:nodes:v1")
        if nodes_cached and isinstance(nodes_cached.body, dict):
            counts["nodes"] = len(nodes_cached.body)
        trans_cached = await asyncio.to_thread(self.client.cache.get, "dict:translations:v1")
        if trans_cached and isinstance(trans_cached.body, dict):
            counts["translations"] = len(trans_cached.body.get("names", {}))
        relics_cached = await asyncio.to_thread(self.client.cache.get, "dict:relics:v1")
        if relics_cached and isinstance(relics_cached.body, list):
            counts["relics"] = len(relics_cached.body)
        return counts


def _add_node_record(target: dict[str, dict[str, Any]], item: Any, *, overwrite: bool) -> None:
    if not isinstance(item, dict):
        return
    key = str(item.get("uniqueName") or "").strip()
    name = str(item.get("name") or "").strip()
    if not key or not name:
        return
    if not overwrite and key in target:
        return
    target[key] = {
        "name": name,
        "system": str(item.get("systemName") or "").strip(),
        "mission": _int_or_none(item.get("missionIndex")),
        "faction": _int_or_none(item.get("factionIndex")),
    }


def _collect_export_names(names: dict[str, str], items: Any) -> None:
    if not isinstance(items, list):
        return
    for item in items:
        if not isinstance(item, dict):
            continue
        key = str(item.get("uniqueName") or "").strip()
        name = str(item.get("name") or "").strip()
        if key and name:
            names[key] = name


def _collect_cdn_translations(
    names: dict[str, str], descs: dict[str, str], rows: list[Any]
) -> None:
    for item in rows:
        if not isinstance(item, dict):
            continue
        key = str(item.get("uniqueName") or "").strip()
        name = str(item.get("name") or "").strip()
        if not key or not name:
            continue
        names[key] = name
        desc = _clean_desc(item.get("description"))
        if desc:
            descs[key] = desc


def _decode_relic_reward(raw: Any, trans: TranslationIndex) -> list[Any] | None:
    if not isinstance(raw, dict) or not raw.get("rewardName"):
        return None
    path = str(raw["rewardName"])
    translated = trans.translate(path)
    if translated == path:
        translated = _fallback_reward_name(path)
    return [
        strip_markup(translated),
        str(raw.get("rarity") or "COMMON").upper(),
        int(raw.get("itemCount") or 1),
    ]
