from typing import Any

import pytest

from milo_core.errors import QueryError
from milo_core.market import Item, MarketQuery, filter_orders, parse_query, resolve_item

ITEM = Item("mod1", "pressure_point", "压迫点", "Pressure Point", 10)


def order(price: int, **overrides: Any) -> dict[str, Any]:
    raw = {
        "itemId": "mod1",
        "type": "sell",
        "platinum": price,
        "quantity": 2,
        "rank": 10,
        "visible": True,
        "user": {"status": "ingame", "ingameName": "Player"},
    }
    raw.update(overrides)
    return raw


def test_multiword_names_and_maxim_do_not_get_destroyed_by_flags() -> None:
    assert parse_query("Maxim Prime Set 买家 MAX PC") == MarketQuery("Maxim Prime Set", True, True)
    assert parse_query("Frost Prime Set").keyword == "Frost Prime Set"


@pytest.mark.parametrize("query", ["PC", "Volt PS4", "Volt 国服", "Volt 买家 卖家"])
def test_invalid_flags_are_explicit_errors(query: str) -> None:
    with pytest.raises(QueryError):
        parse_query(query)


def test_chinese_alias_and_prime_shorthand_choose_the_set() -> None:
    items = [
        Item("1", "volt_prime_set", "伏特Prime一套", "Volt Prime Set"),
        Item("2", "volt_prime_blueprint", "伏特Prime蓝图", "Volt Prime Blueprint"),
    ]
    for name in ["伏特p", "电男", "电男p", "Volt", "volt_prime_set"]:
        assert resolve_item(name, items, {"电男": "Volt"}) == [items[0]]


def test_market_filters_hidden_offline_wrong_items_and_missing_rank() -> None:
    body = {
        "data": [
            order(8),
            order(1, visible=False),
            order(2, user={"status": "offline", "ingameName": "Away"}),
            order(3, itemId="other"),
            order(4, rank=None),
            order(5, rank=0),
            order(6, user={"ingameName": "Unknown"}),
            order(7, type="buy"),
        ]
    }
    result = filter_orders(body, ITEM, MarketQuery("压迫点", max_rank=True))
    assert [entry.price for entry in result] == [8]


def test_orders_are_sorted_by_direction_and_limited_to_eight() -> None:
    sells = {"data": [order(price) for price in range(12, 0, -1)]}
    assert [entry.price for entry in filter_orders(sells, ITEM, MarketQuery("x"))] == list(
        range(1, 9)
    )
    buys = {"data": [order(price, type="buy") for price in range(12)]}
    assert [
        entry.price for entry in filter_orders(buys, ITEM, MarketQuery("x", buyer=True))
    ] == list(range(11, 3, -1))


def test_empty_orders_are_valid_but_unknown_max_rank_is_not() -> None:
    assert filter_orders({"data": []}, ITEM, MarketQuery("x")) == []
    with pytest.raises(QueryError, match="满级信息"):
        filter_orders({"data": []}, Item("x", "x", "x", "x"), MarketQuery("x", max_rank=True))
