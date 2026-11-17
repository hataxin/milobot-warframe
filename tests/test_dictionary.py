import lzma
import struct
from pathlib import Path

import httpx
import pytest

from milo_core.cache import ResponseCache
from milo_core.client import DataClient
from milo_core.dictionary import (
    DictionaryService,
    TranslationIndex,
    decompress_lzma,
    extract_weapon_english_name,
    parse_export_index,
)
from milo_core.errors import QueryError


def _make_de_style_lzma(payload: bytes) -> bytes:
    """Create a stream mimicking DE's explicit-size header + EOS marker."""
    standard = lzma.compress(payload, format=lzma.FORMAT_ALONE)
    return standard[:5] + struct.pack("<Q", len(payload)) + standard[13:]


def test_decompress_lzma_handles_standard_and_de_explicit_size() -> None:
    sample = b"ExportRegions_zh.json!00_abc\nExportWeapons_zh.json!00_def\n"
    assert decompress_lzma(lzma.compress(sample, format=lzma.FORMAT_ALONE)) == sample
    assert decompress_lzma(_make_de_style_lzma(sample)) == sample
    parsed = parse_export_index(_make_de_style_lzma(sample))
    assert parsed == {
        "ExportRegions": "ExportRegions_zh.json!00_abc",
        "ExportWeapons": "ExportWeapons_zh.json!00_def",
    }


def test_extract_weapon_english_name_handles_mk1_prefix() -> None:
    mk1 = {"name": "MK1-斯特朗", "description": "（英文：STRUN）训练用霰弹枪。"}
    base = {"name": "斯特朗", "description": "（英文：STRUN）标准霰弹枪。"}
    assert extract_weapon_english_name(mk1) == "mk1-strun"
    assert extract_weapon_english_name(base) == "strun"


def test_translation_index_matches_exact_and_suffix_segments() -> None:
    index = TranslationIndex(
        {"/Lotus/Types/Items/MiscItems/Forma": "Forma"},
        {"/Lotus/Upgrades/Calendar/AbilityStrength": "增加25%技能强度。"},
    )
    assert index.translate("/Lotus/Types/Items/MiscItems/Forma") == "Forma"
    assert index.translate("/Lotus/StoreItems/Types/Items/MiscItems/Forma") == "Forma"
    assert index.translate("/Lotus/Unknown/Path") == "/Lotus/Unknown/Path"
    assert index.describe("/Lotus/Upgrades/Calendar/AbilityStrength") == "增加25%技能强度。"


async def test_dictionary_caches_in_sqlite_and_falls_back_across_mirrors(
    tmp_path: Path,
) -> None:
    cache = ResponseCache(tmp_path)
    cache.initialize()
    calls: list[str] = []
    index_bytes = lzma.compress(b"ExportRegions_zh.json!00_r1\n", format=lzma.FORMAT_ALONE)

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        calls.append(url)
        if "index_zh.txt.lzma" in url:
            return httpx.Response(200, content=index_bytes)
        if "ExportRegions_zh.json!00_r1" in url:
            return httpx.Response(
                200,
                json={
                    "ExportRegions": [
                        {
                            "uniqueName": "SolNode1",
                            "name": "节点甲",
                            "systemName": "地球",
                            "missionIndex": 2,
                            "factionIndex": 0,
                        }
                    ]
                },
            )
        if "testingcf.jsdelivr.net" in url:
            return httpx.Response(500)
        if "nodes.json" in url:
            return httpx.Response(
                200,
                json=[
                    {
                        "uniqueName": "SolNode1",
                        "name": "被覆盖错误名",
                        "systemName": "错误",
                    },
                    {
                        "uniqueName": "EarthHUB",
                        "name": "Strata 中继站",
                        "systemName": "地球",
                    },
                ],
            )
        return httpx.Response(404)

    client = DataClient(cache, httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    try:
        dicts = DictionaryService(client)
        nodes = await dicts.nodes()
        assert nodes["SolNode1"].display_name == "节点甲(地球)"
        assert nodes["EarthHUB"].display_name == "Strata 中继站(地球)"
        assert any("cdn.jsdelivr.net" in url for url in calls)

        calls.clear()
        dicts_reloaded = DictionaryService(client)
        nodes_cached = await dicts_reloaded.nodes()
        assert nodes_cached["SolNode1"].name == "节点甲"
        assert calls == []

        counts = await dicts_reloaded.cached_counts()
        assert counts["nodes"] == 2
    finally:
        await client.close()


async def test_dictionary_raises_query_error_when_all_sources_fail(tmp_path: Path) -> None:
    cache = ResponseCache(tmp_path)
    cache.initialize()
    transport = httpx.MockTransport(lambda _: httpx.Response(500))
    client = DataClient(cache, httpx.AsyncClient(transport=transport))
    try:
        dicts = DictionaryService(client)
        with pytest.raises(QueryError):
            await dicts.arbitration_tiers()
    finally:
        await client.close()
