"""Bounded pages for list tools whose full result can outgrow MCP clients.

Some lists grow with the account (thousands of tracked prompts or Contexts).
Returned whole they exceed client output limits and the call fails, so these
tools return one page at a time. A page holds at most ``limit`` rows and also
shrinks until its text fits ``MAX_PAGE_CHARS``; the header names the next
offset, so nothing is skipped when a page shrinks.
"""

from typing import Callable

# Claude Code rejects MCP results over about 25k tokens by default. Korean text
# and UUIDs tokenize densely, so stay near 30k characters.
MAX_PAGE_CHARS = 30_000


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
