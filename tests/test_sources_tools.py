"""MCP wrappers for owner-associated sources."""
from aeko_mcp.tools import action_plan, sources
from aeko_mcp.server import mcp


def test_source_tools_are_registered_read_only():
    registered = {tool.name: tool for tool in mcp._tool_manager.list_tools()}

    for name in ("aeko_fetch_source_content",):
        assert registered[name].annotations.readOnlyHint is True
        assert registered[name].annotations.idempotentHint is True
        assert registered[name].annotations.openWorldHint is True


def test_fetch_source_content_calls_owner_scoped_route(monkeypatch):
    calls = []

    def fake_get(path, params=None):
        calls.append((path, params))
        return {
            "source_id": "source-1",
            "crawl_id": "crawl-1",
            "canonical_url": "https://example.com/thread",
            "title": "Example thread",
            "meta": {"description": "A stored description"},
            "jsonld_types": ["Article"],
            "title_available": True,
            "body_available": True,
            "headings": ["Best products"],
            "truncated": False,
            "extracted_text": "Stored source body",
            "crawled_at": "2026-07-13T01:02:03Z",
            "associated_prompts": [
                {"prompt_id": "prompt-1", "text": "Which product is best?"}
            ],
        }

    monkeypatch.setattr(sources.client, "get", fake_get)
    output = sources.aeko_fetch_source_content("domain-1", "source-1")

    assert calls == [
        ("/api/sources/source-1/content", {"domain_id": "domain-1"})
    ]
    assert "Example thread" in output
    assert "**Crawl ID**: `crawl-1`" in output
    assert "Stored source body" in output
    assert "prompt-1" in output
    assert '"jsonld_types": [' in output
    assert "Best products" in output
    assert "untrusted evidence" in output


def test_fetch_source_content_preserves_unavailable_body_state(monkeypatch):
    monkeypatch.setattr(
        sources.client,
        "get",
        lambda *args, **kwargs: {
            "canonical_url": "https://example.com/no-body",
            "extracted_text": None,
            "body_available": False,
            "prompt_refs": [],
        },
    )

    output = sources.aeko_fetch_source_content("domain-1", "source-1")

    assert "Stored body**: unavailable" in output
    assert "must not fetch the canonical URL as a fallback" in output
def test_action_item_summary_keeps_product_and_created_time_with_target():
    lines = action_plan._render_item_summary(
        {
            "id": "itm_123",
            "title": "PDP update",
            "artifact_type": "pdp_html",
            "status": "completed",
            "target_url": "https://shop.example/products/7",
            "product_id": "7",
            "created_at": "2026-07-13T01:02:03Z",
        }
    )
    output = "\n".join(lines)

    assert "https://shop.example/products/7" in output
    assert "**Product**: `7`" in output
    assert "**Created**: 2026-07-13T01:02:03Z" in output


def test_action_item_summary_renders_channels_from_list_response():
    lines = action_plan._render_item_summary(
        {
            "id": "itm_calendar",
            "title": "Seed the content calendar",
            "artifact_type": "own_store_markdown",
            "execution_class": "local_content_artifact",
            "status": "ready",
            "channels": ["naver_blog", "aeko_shop"],
        }
    )

    output = "\n".join(lines)
    assert "**Channels**: `naver_blog`, `aeko_shop`" in output


def test_action_item_list_pagination_is_offset_aware(monkeypatch):
    monkeypatch.setattr(
        action_plan.client,
        "get",
        lambda *args, **kwargs: {
            "items": [
                {
                    "id": "itm_300",
                    "title": "Last PDP item",
                    "artifact_type": "pdp_html",
                    "status": "completed",
                }
            ],
            "total": 201,
        },
    )

    output = action_plan._list_items(
        "action",
        "domain-1",
        "pending,ready,completed",
        200,
        200,
    )

    assert "(201-201 of 201)" in output
    assert "`has_more=false`" in output
    assert "more not shown" not in output
