"""Phase 4 MCP tools: analytics reads, connects, lifecycle."""

import importlib

from aeko_mcp.tools import action_plan, content_variation, reviews, visibility


def test_domain_info_renders_brand_keywords(monkeypatch):
    monkeypatch.setattr(
        visibility.client,
        "get",
        lambda *args, **kwargs: {
            "name": "Grafen",
            "ko_name": "그라펜",
            "base_url": "https://grafen.co.kr",
            "scope": "beauty",
            "brand_keywords": ["Grafen", "그라펜"],
        },
    )

    rendered = visibility.aeko_get_domain_info("domain-1")

    assert "Brand Keywords**: Grafen, 그라펜" in rendered


def test_visibility_summary_passes_backend_filters(monkeypatch):
    calls = []

    def fake_get(path, params=None):
        calls.append({"path": path, "params": params})
        return {"metrics": {}, "trend": [], "brand_keyword": "Brand", "brand_mentions": []}

    monkeypatch.setattr(visibility.client, "get", fake_get)
    visibility.aeko_get_visibility_summary(
        "domain-1",
        view="overview",
        vertical_scope="beauty",
        country="US",
        ai_platform="openai",
        query_type="recommendation",
        funnel_stage="consideration",
        prompt_ids=["p1", "p2"],
    )

    assert calls == [
        {
            "path": "/api/visibility/summary",
            "params": {
                "domain_id": "domain-1",
                "scope": "beauty",
                "country": "US",
                "ai_platform": "openai",
                "query_type": "recommendation",
                "funnel_stage": "consideration",
                "prompt_ids": "p1,p2",
            },
        }
    ]


def test_citability_tool_calls_domain_or_page_route(monkeypatch):
    calls = []

    def fake_get(path, params=None):
        calls.append({"path": path, "params": params})
        return {"avg_score": 82, "page_count": 3}

    monkeypatch.setattr(visibility.client, "get", fake_get)
    domain = visibility.aeko_get_citability(domain_id="domain-1")
    page = visibility.aeko_get_citability(source_id="source-1")
    missing = visibility.aeko_get_citability()

    assert "Citability" in domain
    assert "Citability" in page
    assert "domain_id or source_id" in missing
    assert calls == [
        {"path": "/api/citability/domain", "params": {"domain_id": "domain-1"}},
        {"path": "/api/citability/page", "params": {"source_id": "source-1"}},
    ]


def test_analytics_tools_call_expected_routes(monkeypatch):
    analytics = importlib.import_module("aeko_mcp.tools.analytics")
    calls = []

    def fake_get(path, params=None):
        calls.append({"path": path, "params": params})
        return {"ok": True, "path": path}

    monkeypatch.setattr(analytics.client, "get", fake_get)

    sov = analytics.aeko_get_share_of_voice("domain-1", prompt_ids=["p1"], start_date="2026-01-01", end_date="2026-01-31")
    drift = analytics.aeko_get_answer_drift("domain-1", days=14, prompt_ids=["p1"])
    measure = analytics.aeko_get_measure("domain-1", view="readiness")

    assert "monitoring/sov" in sov
    assert "monitoring/drift" in drift
    assert "measure/readiness" in measure
    assert calls == [
        {
            "path": "/api/monitoring/sov",
            "params": {
                "domain_id": "domain-1",
                "prompt_ids": "p1",
                "start_date": "2026-01-01",
                "end_date": "2026-01-31",
            },
        },
        {"path": "/api/monitoring/drift", "params": {"domain_id": "domain-1", "days": 14, "prompt_ids": "p1"}},
        {"path": "/api/measure/readiness", "params": {"domain_id": "domain-1"}},
    ]


# aeko_connect_review_source / aeko_sync_review_source were removed: connecting or syncing a
# real review platform (Crema / Judge.me / Cafe24) is dashboard-only so third-party credentials
# never traverse the MCP channel. The only agent-side review intake is aeko_inject_reviews (manual).


def test_ga4_tools_call_expected_routes(monkeypatch):
    ga4 = importlib.import_module("aeko_mcp.tools.ga4")
    calls = []

    def fake_get(path, params=None):
        calls.append({"method": "GET", "path": path, "params": params})
        return {"connected": True, "properties": []}

    def fake_post(path, json=None):
        calls.append({"method": "POST", "path": path, "json": json})
        return {"synced": True}

    monkeypatch.setattr(ga4.client, "get", fake_get)
    monkeypatch.setattr(ga4.client, "post", fake_post)

    ga4.aeko_get_ga4_status("domain-1")
    ga4.aeko_list_ga4_properties("domain-1")
    ga4.aeko_select_ga4_property("domain-1", "properties/123", property_name="GA4 Main", account_id="accounts/1", account_name="Account")
    ga4.aeko_sync_ga4("domain-1")

    assert calls == [
        {"method": "GET", "path": "/api/ga4/status", "params": {"domain_id": "domain-1"}},
        {"method": "GET", "path": "/api/ga4/properties", "params": {"domain_id": "domain-1"}},
        {
            "method": "POST",
            "path": "/api/ga4/select-property",
            "json": {
                "domain_id": "domain-1",
                "property_id": "properties/123",
                "property_name": "GA4 Main",
                "account_id": "accounts/1",
                "account_name": "Account",
            },
        },
        {"method": "POST", "path": "/api/ga4/sync-mine", "json": {"domain_id": "domain-1"}},
    ]


def test_action_lifecycle_tools_call_expected_routes(monkeypatch):
    calls = []

    def fake_post(path, json=None, headers=None):
        calls.append({"method": "POST", "path": path, "json": json, "headers": headers})
        if path.endswith("/claim"):
            return {"id": "itm_1", "status": "ready", "title": "Plan"}
        if path.endswith("/release"):
            return {"id": "itm_1", "status": "ready", "title": "Plan"}
        return {"id": "itm_1", "status": "ready", "title": "Plan"}

    def fake_delete(path, params=None):
        calls.append({"method": "DELETE", "path": path, "params": params})
        return {}

    monkeypatch.setattr(action_plan.client, "post", fake_post)
    monkeypatch.setattr(action_plan.client, "delete", fake_delete)

    create = action_plan.aeko_create_action_item(
        domain_id="domain-1",
        artifact_type="pdp_html",
        idempotency_key="domain-1:pdp:sku-1",
        product_id="sku-1",
    )
    claim = action_plan.aeko_claim_action_item("itm_1")
    release = action_plan.aeko_release_action_item("itm_1", claim_id="claim-1")
    complete = action_plan.aeko_complete_action_item(
        "itm_1",
        artifact_summary="Preview saved",
        execution_claim_id="claim-1",
    )
    dismiss = action_plan.aeko_dismiss_action_item("itm_1")

    assert "itm_1" in create
    assert "Action item claimed" in claim
    assert "ready" in release
    assert "marked ready" in complete
    assert "dismissed" in dismiss
    assert calls == [
        {
            "method": "POST",
            "path": "/api/action-items",
            "json": {"domain_id": "domain-1", "artifact_type": "pdp_html", "product_id": "sku-1"},
            "headers": {"Idempotency-Key": "domain-1:pdp:sku-1"},
        },
        {
            "method": "POST",
            "path": "/api/action-items/itm_1/claim",
            "json": None,
            "headers": None,
        },
        {
            "method": "POST",
            "path": "/api/action-items/itm_1/release",
            "json": {
                "force": False,
                "confirm_no_active_execution": False,
                "claim_id": "claim-1",
            },
            "headers": None,
        },
        {
            "method": "POST",
            "path": "/api/items/itm_1/complete",
            "json": {
                "artifact_summary": "Preview saved",
                "execution_claim_id": "claim-1",
            },
            "headers": None,
        },
        {"method": "DELETE", "path": "/api/action-items/itm_1", "params": None},
    ]


def test_action_claim_annotations_expose_permanent_claim_semantics():
    registered = {tool.name: tool for tool in action_plan.mcp._tool_manager.list_tools()}

    claim = registered["aeko_claim_action_item"].annotations
    assert claim.readOnlyHint is False
    assert claim.idempotentHint is False
    assert claim.destructiveHint is False

    release = registered["aeko_release_action_item"].annotations
    assert release.readOnlyHint is False
    assert release.idempotentHint is True
    assert release.destructiveHint is False


def test_unpublish_content_calls_aeko_shop_route(monkeypatch):
    calls = []

    def fake_post(path, json=None):
        calls.append({"path": path, "json": json})
        return {"id": "post-1", "status": "unpublished", "slug": "hello"}

    monkeypatch.setattr(content_variation.client, "post", fake_post)
    out = content_variation.aeko_unpublish_content("content-1", item_id="itm_1")

    assert "unpublished" in out
    assert calls == [
        {
            "path": "/api/aeko-shop/posts/content-1/unpublish",
            "json": {"item_id": "itm_1"},
        }
    ]
