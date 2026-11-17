import pytest

from milo_core.arbitration import (
    build_arbitration_card,
    build_arbitration_list_card,
    parse_arbys,
)
from milo_core.dictionary import NodeInfo, RelicEntry, RelicReward
from milo_core.errors import QueryError
from milo_core.relics import build_relic_help_card, build_relics_card, is_tier_only, search_relics
from milo_core.worldstate import QueryMeta

NOW = 1_800_000_000.0
META = QueryMeta(NOW, NOW, [])
NODES = {
    "SolNode64": NodeInfo("Seimeni", "谷神星", 8, 2),
    "SolNode106": NodeInfo("Hydron", "塞德娜", 8, 0),
    "SolNode10": NodeInfo("Lua", "月球", 2, 1),
}
TIERS = {"SolNode64": "S", "SolNode106": "A", "SolNode10": "C"}


def test_parse_arbys_filters_malformed_and_builds_current_and_lookahead() -> None:
    raw = "\n".join(
        [
            "bad-line",
            f"{int(NOW) - 7200},SolNode64",
            f"{int(NOW) - 600},SolNode64",
            f"{int(NOW) + 3600},SolNode10",
            f"{int(NOW) + 7200},SolNode106",
            f"{int(NOW) + 40 * 86_400},SolNode64",
        ]
    )
    entries = parse_arbys(raw, NOW)
    assert len(entries) == 3

    current = build_arbitration_card(entries, NODES, TIERS, META)
    assert current.rows[0][0] == "Seimeni(谷神星)"
    assert current.rows[0][2] == "S"

    lookahead = build_arbitration_list_card(entries, NODES, TIERS, META)
    assert len(lookahead.rows) == 1
    assert lookahead.rows[0][1] == "Hydron(塞德娜)"
    assert lookahead.rows[0][3] == "A"


def test_parse_arbys_empty_raises_query_error() -> None:
    with pytest.raises(QueryError):
        parse_arbys("invalid\n100,SolNode1", NOW)


@pytest.mark.parametrize("text", ["中纪", "中纪 遗物", "zhongji", "Axi", "古纪核桃"])
def test_relic_tier_only_is_rejected(text: str) -> None:
    assert is_tier_only(text)


def test_relic_search_supports_exact_name_alias_and_cap() -> None:
    relics = [
        RelicEntry(
            f"/Lotus/Relics/R{i}",
            f"中纪 A{i} 遗物",
            (
                RelicReward("Forma 蓝图", "COMMON", 1),
                RelicReward("Volt Prime 机体 蓝图", "UNCOMMON", 1),
                RelicReward("Volt Prime 头部神经光元 蓝图", "RARE", 1),
            ),
        )
        for i in range(1, 35)
    ]
    exact = search_relics("中纪 A1", relics, {})
    assert len(exact) == 1 and exact[0].name == "中纪 A1 遗物"

    by_alias = search_relics("电男 机体", relics, {"电男": "Volt"})
    assert len(by_alias) == 34

    card = build_relics_card("电男 机体", by_alias, META)
    assert len(card.rows) == 30
    assert "仅显示前 30 个" in card.subtitle
    assert "Volt Prime 机体 蓝图" in card.rows[0][2]

    help_card = build_relic_help_card()
    assert help_card.kind == "relic_help" and len(help_card.rows) >= 3

    with pytest.raises(QueryError, match="未找到"):
        build_relics_card("不存在", [], META)
