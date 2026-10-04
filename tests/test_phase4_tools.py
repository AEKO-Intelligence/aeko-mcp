"""Phase 4 MCP tools: analytics reads, connects, lifecycle."""

import importlib

from aeko_mcp.tools import action_plan, content_variation, reviews, store_write, visibility


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

    # SOV is shaped (Task 2); drift and measure are asserted on their own routes below.
    assert sov.startswith("# Share of Voice")
    assert "monitoring/drift" in drift
    assert "measure/readiness" in measure
    assert calls == [
        {
            "path": "/api/monitoring/sov",
            "params": {
                "domain_id": "domain-1",
                "prompt_ids": "p1",
                "from": "2026-01-01",
                "to": "2026-01-31",
                "limit": 25,
                "per_prompt_limit": 1,
            },
        },
        {"path": "/api/monitoring/drift", "params": {"domain_id": "domain-1", "days": 14, "prompt_ids": "p1"}},
        {"path": "/api/measure/readiness", "params": {"domain_id": "domain-1"}},
    ]


def _capture_get(monkeypatch, module, response):
    calls = []

    def fake_get(path, params=None):
        calls.append({"path": path, "params": params})
        return response

    monkeypatch.setattr(module.client, "get", fake_get)
    return calls


def _sov_brand(name, mentions, *, own=False, position=2.5):
    return {
        "name": name,
        "total_mentions": mentions,
        "avg_visibility": 41.237,
        "avg_position": position,
        "cited_response_count": 4,
        "response_count": 9,
        "mention_share_pct": 12.345,
        "is_own_brand": own,
    }


def test_share_of_voice_defaults_send_no_range_and_render_all_time(monkeypatch):
    analytics = importlib.import_module("aeko_mcp.tools.analytics")
    calls = _capture_get(
        monkeypatch,
        analytics,
        {"brands": [_sov_brand("Acme", 10)], "brands_total": 1, "per_prompt": [], "per_prompt_total": 0, "range": None},
    )

    rendered = analytics.aeko_get_share_of_voice("domain-1")

    assert calls == [
        {"path": "/api/monitoring/sov", "params": {"domain_id": "domain-1", "limit": 25, "per_prompt_limit": 1}}
    ]
    assert "Range: all time" in rendered
    assert "| 1 | Acme | 12.3 | 10 | 41.24 | 2.50 | 4 / 9 |" in rendered
    assert "showing 1 of 1 brands" in rendered


def test_share_of_voice_maps_date_aliases_and_clamps_limit(monkeypatch):
    analytics = importlib.import_module("aeko_mcp.tools.analytics")
    calls = _capture_get(
        monkeypatch, analytics, {"brands": [], "brands_total": 0, "range": {"from": "2026-09-01", "to": "2026-09-30"}}
    )

    rendered = analytics.aeko_get_share_of_voice(
        "domain-1", start_date="2026-09-01", end_date="2026-09-30", limit=500
    )
    analytics.aeko_get_share_of_voice("domain-1", from_date="2026-08-01", to_date="2026-08-31", limit=0)

    assert calls[0]["params"] == {
        "domain_id": "domain-1",
        "from": "2026-09-01",
        "to": "2026-09-30",
        "limit": 50,
        "per_prompt_limit": 1,
    }
    assert calls[1]["params"] == {
        "domain_id": "domain-1",
        "from": "2026-08-01",
        "to": "2026-08-31",
        "limit": 1,
        "per_prompt_limit": 1,
    }
    assert "Range: 2026-09-01 ~ 2026-09-30" in rendered
    assert "showing 0 of 0 brands" in rendered


def test_share_of_voice_renders_per_prompt_block_for_small_views(monkeypatch):
    analytics = importlib.import_module("aeko_mcp.tools.analytics")
    calls = _capture_get(
        monkeypatch,
        analytics,
        {
            "brands": [_sov_brand("Acme", 10)],
            "brands_total": 1,
            "per_prompt": [
                {
                    "prompt_id": "p1",
                    "prompt_text": "best sunscreen | for oily skin that does not leave a white cast on darker skin tones",
                    "country": "US",
                    "ai_platform": "openai",
                    "top_brands": [
                        {"name": "A", "visibility_score": 80.0, "mention_count": 12},
                        {"name": "B", "visibility_score": 60.0, "mention_count": 7},
                        {"name": "C", "visibility_score": 20.0, "mention_count": 3},
                    ],
                    "brands_total": 5,
                },
                {
                    "prompt_id": "p2",
                    "prompt_text": "quiet prompt",
                    "country": "KR",
                    "ai_platform": "google",
                    "top_brands": [],
                    "brands_total": 0,
                },
            ],
            "per_prompt_total": 2,
            "range": None,
        },
    )

    rendered = analytics.aeko_get_share_of_voice("domain-1", prompt_ids=["p1", "p2", "p3"])

    assert calls[0]["params"] == {
        "domain_id": "domain-1",
        "prompt_ids": "p1,p2,p3",
        "limit": 25,
        "per_prompt_limit": 3,
    }
    assert (
        "- best sunscreen / for oily skin that does not leave a whit... · openai · US"
        " → A (12), B (7), C (3) (+2 more)"
    ) in rendered
    assert "- quiet prompt · google · KR → no brands" in rendered


def test_share_of_voice_omits_per_prompt_block_above_ten_prompts(monkeypatch):
    analytics = importlib.import_module("aeko_mcp.tools.analytics")
    ids = [f"p{i}" for i in range(1, 12)]
    calls = _capture_get(
        monkeypatch,
        analytics,
        {
            "brands": [_sov_brand("Acme", 10)],
            "brands_total": 1,
            "per_prompt": [
                {"prompt_id": "p1", "prompt_text": "should not render", "top_brands": [], "brands_total": 0}
            ],
            "per_prompt_total": 11,
            "range": None,
        },
    )

    rendered = analytics.aeko_get_share_of_voice("domain-1", prompt_ids=ids)

    assert calls[0]["params"]["prompt_ids"] == ",".join(ids)
    assert calls[0]["params"]["per_prompt_limit"] == 1
    assert "per-prompt detail is shown for views of 10 prompts or fewer" in rendered.lower()
    assert "should not render" not in rendered


def test_share_of_voice_marks_own_brand_and_reports_totals(monkeypatch):
    analytics = importlib.import_module("aeko_mcp.tools.analytics")
    brands = [_sov_brand(f"Brand {i}", 100 - i) for i in range(1, 25)]
    brands.insert(4, _sov_brand("Mine|Co", 96, own=True, position=None))
    _capture_get(
        monkeypatch,
        analytics,
        {"brands": brands, "brands_total": 61, "brands_cursor": "abc", "per_prompt": [], "range": None},
    )

    rendered = analytics.aeko_get_share_of_voice("domain-1")

    assert "| 5 | ★ Mine/Co | 12.3 | 96 | 41.24 | - | 4 / 9 |" in rendered
    assert rendered.count("| ★ ") == 1
    assert "showing 25 of 61 brands" in rendered


def test_share_of_voice_leaves_appended_brands_unranked(monkeypatch):
    analytics = importlib.import_module("aeko_mcp.tools.analytics")
    # The backend's first page is the top `limit` brands plus the own brand and configured
    # competitors that rank below it, appended in rank order: their position is not their rank.
    brands = [_sov_brand("Top", 50), _sov_brand("Mine", 2, own=True)]
    _capture_get(monkeypatch, analytics, {"brands": brands, "brands_total": 40, "range": None})

    rendered = analytics.aeko_get_share_of_voice("domain-1", limit=1)

    assert "| 1 | Top |" in rendered
    assert "| - | ★ Mine |" in rendered
    assert "showing 2 of 40 brands" in rendered


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


def test_public_state_removal_tools_are_annotated_destructive():
    registered = {tool.name: tool for tool in content_variation.mcp._tool_manager.list_tools()}

    unpublish = registered["aeko_unpublish_content"].annotations
    assert unpublish.readOnlyHint is False
    assert unpublish.destructiveHint is True

    sync = registered["aeko_sync_store"].annotations
    assert sync.readOnlyHint is False
    assert sync.destructiveHint is True
