"""Bounded pages for list tools whose full result can outgrow MCP clients.

Some lists grow with the account (thousands of tracked prompts or Contexts).
Returned whole they exceed client output limits and the call fails, so these
tools return one page at a time. A page holds at most ``limit`` rows and also
shrinks until its text fits ``MAX_PAGE_CHARS``; the header names the next
offset, so nothing is skipped when a page shrinks.
"""

from typing import Callable, Iterable, Optional

# Claude Code rejects MCP results over about 25k tokens by default. Korean text
# and UUIDs can approach a token per character, so stay at 20k characters.
MAX_PAGE_CHARS = 20_000
# How many unmatched exact IDs a header names before summarizing the rest.
MISSING_IDS_SHOWN = 50


def exact_ids(values: Optional[Iterable]) -> Optional[dict[str, str]]:
    """Map each requested ID's comparison key (trimmed, lower-case) to the ID as given.

    None, an empty list or only blank entries mean no ID filter: some clients
    send ``[]`` for every optional array.
    """
    if not values:
        return None
    keyed: dict[str, str] = {}
    for value in values:
        text = str(value).strip()
        if text:
            keyed.setdefault(text.lower(), text)
    return keyed or None


def id_key(value) -> str:
    return str(value or "").strip().lower()


def missing_ids_line(label: str, wanted: dict[str, str], found: set[str]) -> Optional[str]:
    """Name the requested IDs (by ``exact_ids`` key) that matched no row."""
    missing = [given for key, given in wanted.items() if key not in found]
    if not missing:
        return None
    shown = ", ".join(f"`{i}`" for i in missing[:MISSING_IDS_SHOWN])
    more = f" and {len(missing) - MISSING_IDS_SHOWN} more" if len(missing) > MISSING_IDS_SHOWN else ""
    return f"{label}: {shown}{more}"


def page_line(offset: int, shown: int, total: int, noun: str) -> str:
    end = offset + shown
    line = f"Showing {noun} {offset + 1}–{end} of {total}."
    return line + (f" Next page: offset={end}." if end < total else " Last page.")


def fit_page(render: Callable[[int], str], count: int, budget: int = MAX_PAGE_CHARS) -> str:
    """Render the first ``count`` rows, dropping trailing rows until the text fits.

    ``render(n)`` must render the page with its first ``n`` rows, including the
    header that names the next offset. One row is always kept so paging moves on.
    """
    text = render(count)
    while len(text) > budget and count > 1:
        count = max(1, min(count - 1, count * budget // len(text)))
        text = render(count)
    return text
