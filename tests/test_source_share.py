"""aeko_get_source_share: citation shares by platform and domain, top URLs of one domain."""
import re
from datetime import date, datetime, timezone

from aeko_mcp.server import mcp
from aeko_mcp.tools import source_share


def _domain_rows(count, *, absent=None, base_share=4.0):
    rows = []
    for index in range(count):
        name = f"site{index + 1}.com"
        if name == absent:
            continue
        rows.append(
            {
                "domain": name,
                "citations": 40 - index,
                "url_count": 3 + index,
                "share_pct": round(base_share - index * 0.1, 1),
                "platforms": [
                    {"platform": "chatgpt", "citations": 30 - index},
                    {"platform": "gemini", "citations": 10},
                ],
            }
        )
    return rows


def _current_page():
    rows = _domain_rows(25)
    rows[1]["domain"] = "news.naver.com"
    rows[1]["share_pct"] = 3.9
    return {
        "domains": rows,
        "totals": {"citations": 1000, "domains": 310},
        "available_platforms": ["chatgpt", "gemini"],
        "range": {"from": "2026-07-07", "to": "2026-10-04"},
        "cursor": "next-page",
    }


def _previous_page():
    # site1.com moved from 3.5% to 4.0%; news.naver.com is new this period.
    rows = _domain_rows(25, base_share=3.5)
    rows = [row for row in rows if row["domain"] != "site2.com"]
    return {
        "domains": rows,
        "totals": {"citations": 900, "domains": 280},
        "available_platforms": ["chatgpt", "gemini"],
        "range": {"from": "2026-04-08", "to": "2026-07-06"},
        "cursor": "older-page",
    }


def test_default_call_reads_current_and_previous_window(monkeypatch):
    calls = []

    def fake_get(path, params=None):
        calls.append((path, dict(params or {})))
        return _current_page() if len(calls) == 1 else _previous_page()

    monkeypatch.setattr(source_share, "_utc_today", lambda: date(2026, 10, 4))
    monkeypatch.setattr(source_share.client, "get", fake_get)

    output = source_share.aeko_get_source_share("domain-1")

    assert calls == [
        (
            "/api/monitoring/sources/domains",
            {"domain_id": "domain-1", "from": "2026-07-07", "to": "2026-10-04", "limit": 25},
        ),
        (
            "/api/monitoring/sources/domains",
            {"domain_id": "domain-1", "from": "2026-04-08", "to": "2026-07-06", "limit": 25},
        ),
    ]
    assert (date(2026, 10, 4) - date(2026, 7, 7)).days == 89

    assert "Range: 2026-07-07 ~ 2026-10-04" in output
    assert "Previous period: 2026-04-08 ~ 2026-07-06" in output
    assert "Total citations: 1,000 across 310 domains" in output
    assert "over the top 25 domains" in output

    platform_shares = [
        float(m) for m in re.findall(r"^\| (?:chatgpt|gemini) \| ([0-9.]+) \|", output, re.MULTILINE)
    ]
    assert len(platform_shares) == 2
    assert abs(sum(platform_shares) - 100.0) <= 0.1

    assert "| rank | domain | share % | citations | urls | Δ vs previous period (pp) |" in output
    assert "| 1 | site1.com | 4.0 | 40 | 3 | +0.5 |" in output
    assert "| 2 | news.naver.com | 3.9 | 39 | 4 | — |" in output
    assert "showing 25 of 310 domains" in output


def test_platform_shares_without_more_pages_have_no_top_note(monkeypatch):
    page = _current_page()
    page["cursor"] = None
    monkeypatch.setattr(source_share.client, "get", lambda path, params=None: page)

    output = source_share.aeko_get_source_share("domain-1", from_date="2026-09-01", to_date="2026-09-30")

    assert "over the top" not in output


def test_explicit_range_and_filters_are_passed_and_previous_window_matches_length(monkeypatch):
    calls = []

    def fake_get(path, params=None):
        calls.append(dict(params or {}))
        return _current_page()

    monkeypatch.setattr(source_share.client, "get", fake_get)

    source_share.aeko_get_source_share(
        "domain-1",
        from_date="2026-09-01",
        to_date="2026-09-30",
        prompt_ids=["p1", "p2"],
        ai_platform="gemini",
    )

    assert calls[0] == {
        "domain_id": "domain-1",
        "prompt_ids": "p1,p2",
        "ai_platform": "gemini",
        "from": "2026-09-01",
        "to": "2026-09-30",
        "limit": 25,
    }
    assert calls[1]["from"] == "2026-08-02"
    assert calls[1]["to"] == "2026-08-31"


def test_domain_lists_top_urls(monkeypatch):
    calls = []

    def fake_get(path, params=None):
        calls.append((path, dict(params or {})))
        return {
            "domain": "news.naver.com",
            "urls": [
                {
                    "source_id": f"s{index}",
                    "url": f"https://news.naver.com/article/{index}",
                    "title": ("Very long headline | with a pipe " * 5) if index == 0 else f"Article {index}",
                    "has_json_ld": index % 2 == 0,
                    "citations": 20 - index,
                    "first_cited_at": "2026-08-01T00:00:00Z",
                    "last_cited_at": "2026-10-01T09:30:00Z",
                    "ai_readiness": None,
                }
                for index in range(20)
            ],
            "total": 48,
            "cursor": "more",
        }

    monkeypatch.setattr(source_share.client, "get", fake_get)

    output = source_share.aeko_get_source_share("domain-1", domain="news.naver.com")

    assert calls == [
        (
            "/api/monitoring/sources/domains/news.naver.com/urls",
            {"domain_id": "domain-1", "limit": 20},
        )
    ]
    assert "| url | title | citations | last cited |" in output
    assert "| https://news.naver.com/article/1 | Article 1 | 19 | 2026-10-01 |" in output
    long_row = next(line for line in output.splitlines() if "/article/0 |" in line)
    title_cell = long_row.split(" | ")[1]
    assert len(title_cell) <= 80
    assert "showing 20 of 48 URLs" in output


def test_domain_key_is_url_encoded_in_the_path(monkeypatch):
    calls = []

    def fake_get(path, params=None):
        calls.append(path)
        return {"domain": "x", "urls": [], "total": 0, "cursor": None}

    monkeypatch.setattr(source_share.client, "get", fake_get)

    source_share.aeko_get_source_share("domain-1", domain="a b/c")

    assert calls == ["/api/monitoring/sources/domains/a%20b%2Fc/urls"]


def test_domain_with_no_urls_says_no_citations(monkeypatch):
    monkeypatch.setattr(
        source_share.client,
        "get",
        lambda path, params=None: {"domain": "news.naver.com", "urls": [], "total": 0, "cursor": None},
    )

    output = source_share.aeko_get_source_share("domain-1", domain="news.naver.com")

    assert "No citations of news.naver.com" in output
    assert "| url |" not in output


def test_utc_today_is_the_utc_date():
    assert source_share._utc_today() == datetime.now(timezone.utc).date()


def test_source_share_is_registered_read_only():
    registered = {tool.name: tool for tool in mcp._tool_manager.list_tools()}

    tool = registered["aeko_get_source_share"]
    assert tool.annotations.readOnlyHint is True
    assert set(tool.parameters["properties"]) == {
        "domain_id",
        "from_date",
        "to_date",
        "prompt_ids",
        "ai_platform",
        "domain",
    }
