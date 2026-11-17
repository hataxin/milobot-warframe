"""Structured query results shared by service, text and image outputs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from .market import Item
    from .whisper import WhisperEntry

CardKind = Literal[
    "cycles",
    "market",
    "candidates",
    "summary",
    "alerts",
    "fissures",
    "sortie",
    "archon",
    "invasions",
    "void_trader",
    "steel_path",
    "nightwave",
    "daily_deals",
    "calendar",
    "syndicate",
    "duviri",
    "arbitration",
    "arbitration_list",
    "relics",
    "relic_help",
    "help",
    "subscriptions",
    "subscription_help",
    "ducats",
    "riven",
    "lich_sister",
    "relic_value",
    "translate",
    "fusion",
    "varzia",
    "conquest",
    "news",
    "timings",
]


@dataclass
class Card:
    """One query result that can be sent as text or rendered as a PNG."""

    title: str
    rows: list[tuple[str, ...]]
    subtitle: str = ""
    candidates: list[Item] = field(default_factory=list)
    columns: tuple[str, ...] = ()
    kind: CardKind = "summary"
    empty_message: str = "暂无数据"
    highlight: str = ""
    footer_note: str = ""
    stats_line: str = ""
    whispers: list[WhisperEntry] = field(default_factory=list, repr=False, compare=False)

    def text(self) -> str:
        """Build a readable chat response without depending on an image renderer."""
        lines = [self.title]
        if self.highlight:
            lines.append(self.highlight)
        if self.subtitle:
            lines.append(self.subtitle)
        if self.columns:
            lines.append(" · ".join(self.columns))
        if not self.rows:
            lines.append(self.empty_message)
        else:
            for row in self.rows:
                if row and row[0].startswith("§"):
                    lines.append(f"[{row[0].removeprefix('§')}]")
                else:
                    lines.append(" · ".join(row))
        if self.stats_line:
            lines.append(self.stats_line)
        return "\n".join(lines)
