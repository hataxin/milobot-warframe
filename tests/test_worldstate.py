from milo_core.dictionary import NightwaveChallenge, NodeInfo, PoolReward, TranslationIndex
from milo_core.worldstate import (
    QueryMeta,
    build_alerts_card,
    build_archon_card,
    build_calendar_card,
    build_daily_deals_card,
    build_duviri_card,
    build_fissures_card,
    build_invasions_card,
    build_nightwave_card,
    build_sortie_card,
    build_steel_path_card,
    build_syndicate_card,
    build_void_trader_card,
)


def _mongo_ts(seconds: float) -> dict[str, dict[str, str]]:
    return {"$date": {"$numberLong": str(int(seconds * 1000))}}


NODES = {
    "SolNode122": NodeInfo("Stephano", "天王星", 8, 0),
    "SolNode310": NodeInfo("Mot", "虚空", 2, 4),
    "CrewBattleNode509": NodeInfo("比邻星节点", "土星比邻星域", 60, 0),
    "EarthHUB": NodeInfo("Strata 中继站", "地球", 100, 0),
}
TRANS = TranslationIndex(
    {
        "/Lotus/Types/Items/MiscItems/Forma": "Forma",
        "/Lotus/Types/Recipes/Weapons/DeraVandalBlueprint": "德拉·破坏者 蓝图",
        "/Lotus/StoreItems/Types/Items/Research/ChemComponent": "爆燃喷射器",
        "/Lotus/Types/Challenges/Calendar1999/Cal1": "惩罚炽蛇军",
        "/Lotus/Upgrades/Calendar/Up1": "力量飙升",
        "/Lotus/StoreItems/Types/Items/MiscItems/ArcaneUnlocker": "<ARCHWING> 赋能槽连接器",
        "/Lotus/Types/Gameplay/Eidolon/Jobs/JobA": "取回物资",
    },
    {
        "/Lotus/Types/Challenges/Calendar1999/Cal1": "击杀 150 名敌人",
        "/Lotus/Upgrades/Calendar/Up1": "增加 25% 技能强度",
    },
)
NOW = 1_800_000_000.0
META = QueryMeta(NOW, NOW - 5, [])


def test_alerts_and_fissures_filter_expired_and_sort_by_tier() -> None:
    ws = {
        "Alerts": [
            {
                "Expiry": _mongo_ts(NOW + 3600),
                "MissionInfo": {
                    "location": "SolNode122",
                    "missionType": "MT_DEFENSE",
                    "faction": "FC_GRINEER",
                    "missionReward": {
                        "credits": 10000,
                        "countedItems": [
                            {"ItemType": "/Lotus/Types/Items/MiscItems/Forma", "ItemCount": 3}
                        ],
                    },
                },
            },
            {
                "Expiry": _mongo_ts(NOW - 10),
                "MissionInfo": {"location": "SolNode122"},
            },
        ],
        "ActiveMissions": [
            {
                "Node": "SolNode310",
                "MissionType": "MT_SURVIVAL",
                "Modifier": "VoidT4",
                "Hard": False,
                "Expiry": _mongo_ts(NOW + 900),
            },
            {
                "Node": "SolNode122",
                "MissionType": "MT_DEFENSE",
                "Modifier": "VoidT1",
                "Hard": False,
                "Expiry": _mongo_ts(NOW + 600),
            },
            {
                "Node": "SolNode310",
                "MissionType": "MT_SURVIVAL",
                "Modifier": "VoidT6",
                "Hard": True,
                "Expiry": _mongo_ts(NOW + 1200),
            },
        ],
        "VoidStorms": [
            {
                "Node": "CrewBattleNode509",
                "ActiveMissionTier": "VoidT2",
                "Expiry": _mongo_ts(NOW + 1800),
            }
        ],
    }
    alerts = build_alerts_card(ws, NODES, TRANS, META)
    assert len(alerts.rows) == 1
    assert alerts.rows[0][0] == "Stephano(天王星)"
    assert "10,000 星币，Forma ×3" in alerts.rows[0][2]

    normal = build_fissures_card(ws, NODES, "normal", META)
    assert [row[0] for row in normal.rows] == [
        "§古纪 (T1)",
        "G系 · 防御",
        "§后纪 (T4)",
        "O系 · 生存",
    ]

    steel = build_fissures_card(ws, NODES, "steel", META)
    assert len(steel.rows) == 2 and steel.rows[0][0] == "§全能 (T6)"
    assert steel.rows[1][0] == "O系 · 生存"

    storm = build_fissures_card(ws, NODES, "storm", META)
    assert storm.rows[0][0] == "§前纪 (T2)"
    assert storm.rows[1][0] == "G系 · 前哨战"
    assert storm.rows[1][1] == "比邻星节点(土星比邻星域)"


def test_sortie_archon_and_invasions() -> None:
    ws = {
        "Sorties": [
            {
                "Boss": "SORTIE_BOSS_HEK",
                "Expiry": _mongo_ts(NOW + 5000),
                "Variants": [
                    {
                        "missionType": "MT_INTEL",
                        "modifierType": "SORTIE_MODIFIER_ARMOR",
                        "node": "SolNode122",
                    }
                ],
            }
        ],
        "LiteSorties": [
            {
                "Boss": "SORTIE_BOSS_NIRA",
                "Expiry": _mongo_ts(NOW + 100_000),
                "Missions": [{"missionType": "MT_ASSASSINATION", "node": "SolNode122"}],
            }
        ],
        "Invasions": [
            {"Node": "SolNode310", "Completed": True, "Goal": 99999},
            {
                "Node": "SolNode122",
                "Faction": "FC_CORPUS",
                "DefenderFaction": "FC_GRINEER",
                "Count": -10000,
                "Goal": 40000,
                "Completed": False,
                "AttackerReward": {
                    "countedItems": [
                        {
                            "ItemType": "/Lotus/Types/Recipes/Weapons/DeraVandalBlueprint",
                            "ItemCount": 1,
                        }
                    ]
                },
                "DefenderReward": None,
            },
        ],
    }
    sortie = build_sortie_card(ws, NODES, META)
    assert "Vay Hek 委员" in sortie.highlight
    assert sortie.rows[0][3] == "敌人护甲强化"

    archon = build_archon_card(ws, NODES, META)
    assert "混沌蛇主" in archon.highlight

    invasions = build_invasions_card(ws, NODES, TRANS, META)
    assert len(invasions.rows) == 1
    assert "德拉·破坏者 蓝图" in invasions.rows[0][2]
    assert invasions.rows[0][3] == "25.0%"


def test_void_trader_steel_path_nightwave_deals_calendar_syndicate_duviri() -> None:
    ws = {
        "VoidTraders": [
            {
                "Character": "Baro Ki'Teer",
                "Node": "EarthHUB",
                "Activation": _mongo_ts(NOW + 7200),
                "Expiry": _mongo_ts(NOW + 172_800),
            }
        ],
        "SeasonInfo": {
            "Season": 18,
            "Expiry": _mongo_ts(NOW + 864_000),
            "ActiveChallenges": [
                {"Challenge": "/Lotus/Daily1", "Daily": True},
                {"Challenge": "/Lotus/Elite1"},
            ],
        },
        "DailyDeals": [
            {
                "StoreItem": "/Lotus/StoreItems/Types/Items/Research/ChemComponent",
                "Discount": 25,
                "OriginalPrice": 20,
                "SalePrice": 15,
                "AmountTotal": 100,
                "AmountSold": 120,
                "Expiry": _mongo_ts(NOW + 3600),
            }
        ],
        "KnownCalendarSeasons": [
            {
                "Season": "CST_WINTER",
                "YearIteration": 2,
                "Expiry": _mongo_ts(NOW + 5000),
                "Days": [
                    {
                        "day": 40,
                        "events": [
                            {
                                "type": "CET_CHALLENGE",
                                "challenge": "/Lotus/Types/Challenges/Calendar1999/Cal1",
                            },
                            {
                                "type": "CET_REWARD",
                                "reward": "/Lotus/StoreItems/Types/Items/MiscItems/ArcaneUnlocker",
                            },
                        ],
                    }
                ],
            }
        ],
        "SyndicateMissions": [
            {
                "Tag": "CetusSyndicate",
                "Expiry": _mongo_ts(NOW + 3600),
                "Jobs": [
                    {
                        "jobType": "/Lotus/Types/Gameplay/Eidolon/Jobs/JobA",
                        "rewards": "PoolA",
                        "minEnemyLevel": 5,
                        "maxEnemyLevel": 15,
                        "masteryReq": 2,
                        "xpAmounts": [400, 400],
                    }
                ],
            }
        ],
        "EndlessXpSchedule": [
            {
                "CategoryChoices": [
                    {"Category": "EXC_NORMAL", "Choices": ["Gara", "Khora"]},
                    {"Category": "EXC_HARD", "Choices": ["DualIchor", "Strun"]},
                ]
            }
        ],
    }
    vt = build_void_trader_card(ws, NODES, TRANS, META)
    assert vt.rows[0][1] == "尚未到达"

    sp = build_steel_path_card(1_605_484_800.0)
    assert sp.rows[0][0] == "本周" and sp.rows[0][1] == "Umbra Forma 蓝图"

    nw = build_nightwave_card(
        ws,
        {
            "/Lotus/Daily1": NightwaveChallenge("每日挑战", "击杀 |COUNT| 名", 1000, 15),
            "/Lotus/Elite1": NightwaveChallenge("精英挑战", "完成突击", 7000, 1),
        },
        META,
    )
    assert [row[0] for row in nw.rows] == ["每日", "精英"]
    assert nw.rows[0][2] == "击杀 15 名"

    deals = build_daily_deals_card(ws, TRANS, META)
    assert deals.rows[0][0] == "爆燃喷射器"
    assert deals.rows[0][3] == "0 / 100"

    cal = build_calendar_card(ws, TRANS, META)
    assert cal.rows[0][0] == "2月9日"
    assert "惩罚炽蛇军：击杀 150 名敌人" in cal.rows[0][2]
    assert cal.rows[1][2] == "赋能槽连接器"

    syn = build_syndicate_card(
        ws,
        "CetusSyndicate",
        {"PoolA": [PoolReward("伊莱体 ×|COUNT|", "COMMON", 15)]},
        TRANS,
        META,
    )
    assert syn.rows[0][0] == "取回物资"
    assert "MR 2" in syn.rows[0][1]
    assert syn.rows[0][2] == "伊莱体 ×15"

    duv = build_duviri_card(ws, {"dual ichor": "恶脓双斧", "strun": "斯特朗"}, META)
    assert duv.rows[0] == ("普通", "Gara / Khora")
    assert duv.rows[1] == ("钢铁之路", "恶脓双斧 / 斯特朗")
