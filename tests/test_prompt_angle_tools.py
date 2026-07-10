"""Phase 2 MCP prompt-angle tools: payload contracts and parseable IDs."""

import importlib

import pytest

from aeko_mcp.tools import contexts, research, reviews


def test_track_prompt_forwards_only_settable_angles(monkeypatch):
    calls = []

    def fake_post(path, json=None, headers=None):
        calls.append({"path": path, "json": json, "headers": headers})
        return {
            "results": [
                {
                    "status": "tracked",
                    "tracked_prompt_id": "tp-1",
                    "ai_platform": "openai",
                    "country": "US",
                }
            ],
            "summary": {"tracked": 1},
        }

    monkeypatch.setattr(research.client, "post", fake_post)

    out = research.aeko_track_prompt(
        raw_prompt="best regenerative cream for a friend gift",
        prompt_en="best regenerative cream for a friend gift",
        ai_platforms=["openai", "google"],
        countries=["US", "KR"],
        view_id="view-1",
        context_ids=["ctx-1", "ctx-2"],
    )

    assert "tp-1" in out
    assert calls == [
        {
            "path": "/api/tracked-prompts",
            "json": {
                "raw_prompt": "best regenerative cream for a friend gift",
                "prompt_en": "best regenerative cream for a friend gift",
                "ai_platforms": ["openai", "google"],
                "countries": ["US", "KR"],
                "view_id": "view-1",
                "context_ids": ["ctx-1", "ctx-2"],
            },
            "headers": None,
        }
    ]
    assert "prompt_ko" not in calls[0]["json"]
    assert "persona" not in calls[0]["json"]
    assert "tags" not in calls[0]["json"]
    assert "priority" not in calls[0]["json"]
    assert "source_type" not in calls[0]["json"]
    assert "source_ref" not in calls[0]["json"]


def test_track_prompt_rejects_non_backend_metadata_kwargs():
    with pytest.raises(TypeError):
        research.aeko_track_prompt(raw_prompt="friend gift cream", priority=1)


def test_tracked_prompt_list_renders_angle_fields():
    rendered = research._format_tracked_prompts(
        [
            {
                "id": "tp-1",
                "raw_prompt": "friend gift cream",
                "ai_platform": "openai",
                "country": "US",
                "status": "tracked",
                "context_id": "ctx-1",
                "context_title": "Friend gift situation",
                "funnel_stage": "consideration",
                "query_type": "recommendation",
                "tags": ["gift", "cream"],
            }
        ]
    )

    assert "Friend gift situation" in rendered
    assert "consideration" in rendered
    assert "recommendation" in rendered
    assert "gift, cream" in rendered


def test_tracked_prompt_detail_renders_context_not_legacy_persona():
    rendered = research._format_tracked_prompt_detail(
        {
            "window": "latest",
            "prompt": {
                "id": "tp-1",
                "raw_prompt": "friend gift cream",
                "country": "US",
                "persona": "legacy shopper profile",
                "context_id": "ctx-1",
                "context_title": "Friend gift situation",
                "context_snapshot": "Customer needs a practical gift.\nBudget is under $50.",
            },
            "responses": [],
        }
    )

    assert "Friend gift situation" in rendered
    assert "Customer needs a practical gift." in rendered
    assert "Budget is under $50." in rendered
    assert "legacy shopper profile" not in rendered


def test_quota_tool_reads_tracked_prompt_quota(monkeypatch):
    calls = []

    def fake_get(path, params=None):
        calls.append({"path": path, "params": params})
        if path == "/api/users/limit-status":
            return {"tracked_prompts": {"current": 8, "limit": 20}}
        return {
            "tracked_count": 8,
            "max_tracked_prompts": 20,
            "remaining": 12,
            "package_type": "pro",
        }

    monkeypatch.setattr(research.client, "get", fake_get)
    out = research.aeko_get_quota()

    assert calls == [
        {"path": "/api/tracked-prompts/quota", "params": None},
        {"path": "/api/users/limit-status", "params": None},
    ]
    assert "tracked_count" in out
    assert "20" in out


def test_context_write_tools_call_expected_routes(monkeypatch):
    calls = []

    def fake_post(path, json=None):
        calls.append({"method": "POST", "path": path, "json": json})
        if path == "/api/contexts/from-reviews":
            return {"requested": 1, "created": 1, "promoted": 0, "skipped": 0, "context_ids": ["ctx-2"]}
        return {"id": "ctx-1", **(json or {})}

    def fake_patch(path, json=None):
        calls.append({"method": "PATCH", "path": path, "json": json})
        return {"id": path.rsplit("/", 1)[-1], **(json or {})}

    def fake_delete(path):
        calls.append({"method": "DELETE", "path": path})
        return {"archived": True, "references_retained": 0}

    monkeypatch.setattr(contexts.client, "post", fake_post)
    monkeypatch.setattr(contexts.client, "patch", fake_patch)
    monkeypatch.setattr(contexts.client, "delete", fake_delete)

    create_out = contexts.aeko_create_context(
        domain_id="domain-1",
        title="Friend gift situation",
        summary="A shopper needs a giftable cream for a friend.",
        occasion="gift",
        recipient="friend",
        scope="product",
        product_external_ref="sku-1",
    )
    update_out = contexts.aeko_update_context(
        "ctx-1",
        title="Updated gift situation",
        context_for_prompt="Customer needs a practical gift for a friend.",
        status="active",
    )
    archive_out = contexts.aeko_archive_context("ctx-1")
    batch_out = contexts.aeko_create_contexts_from_reviews(
        domain_id="domain-1",
        integration_id="int-1",
        min_context_score=80,
        review_ids=["rev-1"],
    )

    assert "ctx-1" in create_out
    assert "Updated gift situation" in update_out
    assert "archived" in archive_out
    assert "ctx-2" in batch_out
    assert calls == [
        {
            "method": "POST",
            "path": "/api/contexts",
            "json": {
                "domain_id": "domain-1",
                "title": "Friend gift situation",
                "summary": "A shopper needs a giftable cream for a friend.",
                "occasion": "gift",
                "recipient": "friend",
                "scope": "product",
                "product_external_ref": "sku-1",
                "source": "manual",
                "curated": True,
            },
        },
        {
            "method": "PATCH",
            "path": "/api/contexts/ctx-1",
            "json": {
                "title": "Updated gift situation",
                "context_for_prompt": "Customer needs a practical gift for a friend.",
                "status": "active",
            },
        },
        {"method": "DELETE", "path": "/api/contexts/ctx-1"},
        {
            "method": "POST",
            "path": "/api/contexts/from-reviews",
            "json": {
                "domain_id": "domain-1",
                "integration_id": "int-1",
                "min_context_score": 80,
                "review_ids": ["rev-1"],
            },
        },
    ]


def test_list_contexts_renders_authoritative_prompt_text(monkeypatch):
    calls = []

    def fake_get(path, params=None):
        calls.append({"path": path, "params": params})
        return [
            {
                "id": "ctx-converted",
                "title": "Converted ICP",
                "context_for_prompt": "Age range: 20-29\nInterests: sensitive-skin care",
                "kind": "persona",
                "scope": "brand",
            }
        ]

    monkeypatch.setattr(contexts.client, "get", fake_get)
    out = contexts.aeko_list_contexts("domain-1")

    assert "Age range: 20-29" in out
    assert "Interests: sensitive-skin care" in out
    assert calls == [
        {
            "path": "/api/contexts",
            "params": {"domain_id": "domain-1", "status": "active", "curated": "true"},
        }
    ]


def test_view_tools_call_expected_routes(monkeypatch):
    views = importlib.import_module("aeko_mcp.tools.views")
    calls = []

    def fake_get(path, params=None):
        calls.append({"method": "GET", "path": path, "params": params})
        return {"views": [{"id": "view-1", "name": "Gift view", "prompt_count": 2}]}

    def fake_post(path, json=None):
        calls.append({"method": "POST", "path": path, "json": json})
        return {"id": "view-2", "name": json.get("name", "Gift view"), "added_count": 1, "skipped_count": 0}

    monkeypatch.setattr(views.client, "get", fake_get)
    monkeypatch.setattr(views.client, "post", fake_post)

    list_out = views.aeko_list_views("domain-1", status="active")
    create_out = views.aeko_create_view(
        domain_id="domain-1",
        name="Gift view",
        description="Gift-focused prompts",
        prompt_ids=["prompt-1"],
    )
    add_out = views.aeko_add_prompts_to_view("view-2", ["prompt-2"])

    assert "view-1" in list_out
    assert "view-2" in create_out
    assert "added_count" in add_out
    assert calls == [
        {"method": "GET", "path": "/api/views", "params": {"domain_id": "domain-1", "status": "active"}},
        {
            "method": "POST",
            "path": "/api/views",
            "json": {
                "domain_id": "domain-1",
                "name": "Gift view",
                "description": "Gift-focused prompts",
                "prompt_ids": ["prompt-1"],
            },
        },
        {"method": "POST", "path": "/api/views/view-2/prompts", "json": {"prompt_ids": ["prompt-2"]}},
    ]


def test_suggested_prompt_tools_call_expected_routes(monkeypatch):
    calls = []

    def fake_get(path, params=None):
        calls.append({"method": "GET", "path": path, "params": params})
        return [{"suggestion_id": "sug-1", "suggestion_hash": "hash-1", "prompt": "친구 선물 크림 추천"}]

    def fake_post(path, json=None):
        calls.append({"method": "POST", "path": path, "json": json})
        return {"status": "tracked", "context_id": "ctx-1", "tracked_prompt_ids": ["tp-1"]}

    monkeypatch.setattr(reviews.client, "get", fake_get)
    monkeypatch.setattr(reviews.client, "post", fake_post)

    list_out = reviews.aeko_get_suggested_prompts("int-1", "sku-1", limit=5)
    track_out = reviews.aeko_track_suggested_prompt(
        integration_id="int-1",
        suggestion_id="sug-1",
        ai_platforms=["openai"],
        countries=["US"],
        view_id="view-1",
    )
    batch_out = reviews.aeko_track_suggested_prompts(
        integration_id="int-1",
        min_context_score=80,
        review_ids=["rev-1"],
        ai_platforms=["google"],
        countries=["KR"],
        view_id="view-1",
    )
    dismiss_out = reviews.aeko_dismiss_suggested_prompt("int-1", "hash-1")

    assert "sug-1" in list_out
    assert "tp-1" in track_out
    assert "tracked" in batch_out
    assert "hash-1" in dismiss_out
    assert calls == [
        {
            "method": "GET",
            "path": "/api/review-integrations/int-1/products/sku-1/suggested-prompts",
            "params": {"limit": 5},
        },
        {
            "method": "POST",
            "path": "/api/review-integrations/int-1/suggested-prompts/sug-1/track",
            "json": {
                "ai_platforms": ["openai"],
                "countries": ["US"],
                "view_id": "view-1",
            },
        },
        {
            "method": "POST",
            "path": "/api/review-integrations/int-1/suggested-prompts/track-batch",
            "json": {
                "min_context_score": 80,
                "review_ids": ["rev-1"],
                "ai_platforms": ["google"],
                "countries": ["KR"],
                "view_id": "view-1",
            },
        },
        {
            "method": "POST",
            "path": "/api/review-integrations/int-1/suggested-prompts/hash-1/dismiss",
            "json": None,
        },
    ]
