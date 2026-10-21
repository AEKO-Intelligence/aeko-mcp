"""Pages shrink to fit client output limits without skipping rows."""

from aeko_mcp.tools import contexts, research
from aeko_mcp.tools._paging import MAX_PAGE_CHARS, fit_page, page_line


def test_fit_page_drops_trailing_rows_until_the_text_fits():
    rows = ["x" * 100] * 50

    def render(count):
        return page_line(0, count, len(rows), "rows") + "\n" + "\n".join(rows[:count])

    text = fit_page(render, len(rows), budget=1_000)

    assert len(text) <= 1_000
    shown = text.count("x" * 100)
    assert 1 <= shown < 50
    assert f"Showing rows 1–{shown} of 50. Next page: offset={shown}." in text


def test_fit_page_keeps_one_row_even_when_it_is_over_budget():
    text = fit_page(lambda count: "y" * 5_000 * count, 3, budget=1_000)

    assert text == "y" * 5_000


def test_tracked_prompt_page_with_long_rows_stays_under_the_budget(monkeypatch):
    long_text = "세탁기 비교 질문 " * 60
    rows = [{"id": f"tp-{i}", "raw_prompt": long_text, "prompt_ko": long_text} for i in range(200)]
    monkeypatch.setattr(research.client, "get", lambda path, params=None: rows)

    first = research.aeko_get_tracked_prompts(limit=200)

    assert len(first) <= MAX_PAGE_CHARS
    next_offset = int(first.split("Next page: offset=", 1)[1].split(".", 1)[0])
    second = research.aeko_get_tracked_prompts(limit=200, offset=next_offset)
    assert f"`tp-{next_offset - 1}`" in first and f"`tp-{next_offset}`" not in first
    assert f"`tp-{next_offset}`" in second


def test_context_and_opportunity_pages_stay_under_the_budget(monkeypatch):
    memory = "맞벌이 4인 가족의 대용량 세탁 고민 " * 40
    rows = [{"id": f"ctx-{i}", "title": f"Memory {i}", "context_for_prompt": memory} for i in range(100)]
    ranked = [
        {"context_id": f"ctx-{i}", "title": memory[:200], "state": "saved", "rollup": {"opportunity_score": 1}}
        for i in range(200)
    ]

    def fake_get(path, params=None):
        return {"focused": [], "recommended": [], "contexts": ranked} if path.endswith("/opportunities") else rows

    monkeypatch.setattr(contexts.client, "get", fake_get)

    assert len(contexts.aeko_list_contexts("domain-1", limit=100)) <= MAX_PAGE_CHARS
    assert len(contexts.aeko_list_context_opportunities("domain-1", limit=200)) <= MAX_PAGE_CHARS
