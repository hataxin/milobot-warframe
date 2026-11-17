"""Shared command flag parsing (`-1`, `-w`, `-en`, `-<page>`) and pagination helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass

_PAGE_FLAG_RE = re.compile(r"^-(\d+)$")


@dataclass(frozen=True)
class CommandFlags:
    """Parsed per-invocation display/pagination options preserving hyphenated names."""

    cleaned: str
    text_only: bool = False
    english: bool = False
    page: int = 1


def parse_command_flags(raw: str, *, allow_page: bool = True) -> CommandFlags:
    """Extract trailing or whitespace-separated `-1`, `-w`, `-en`, `-<page>` flags."""
    text = raw.strip()
    if not text:
        return CommandFlags("")
    # Support attached trailing shorthand like `托里德-2` or `Volt-1` while keeping `MK1-Braton`.
    suffix = r"w|en|\d+" if allow_page else r"w|en|1"
    text = re.sub(rf"(?<!\s)-({suffix})\s*$", r" -\1", text, flags=re.IGNORECASE)
    text_only = False
    english = False
    page = 1
    kept: list[str] = []
    for token in text.split():
        lowered = token.casefold()
        if lowered in {"-1", "-w", "--text"}:
            text_only = True
        elif lowered in {"-en", "--en"}:
            english = True
        elif allow_page and (match := _PAGE_FLAG_RE.match(lowered)):
            page = max(1, int(match.group(1)))
        else:
            kept.append(token)
    return CommandFlags(" ".join(kept).strip(), text_only=text_only, english=english, page=page)


def paginate[T](items: list[T], page: int, page_size: int) -> tuple[list[T], int, int]:
    """Slice one page cleanly, clamping page to `[1, total_pages]`."""
    if not items:
        return [], 1, 1
    total_pages = max(1, (len(items) + page_size - 1) // page_size)
    current = min(max(1, page), total_pages)
    start = (current - 1) * page_size
    return items[start : start + page_size], current, total_pages


def page_caption(page: int, total_pages: int) -> str:
    """Format concise page indicator when a result spans multiple pages."""
    if total_pages <= 1:
        return ""
    return f"第 {page}/{total_pages} 页（加 -{min(page + 1, total_pages)} 翻页）"
