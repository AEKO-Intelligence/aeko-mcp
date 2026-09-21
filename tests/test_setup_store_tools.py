"""Phase 3 MCP setup/store tools."""

import importlib

from aeko_mcp.tools import research, store_write, visibility


def test_add_domain_posts_domain_create(monkeypatch):
    calls = []

    def fake_post(path, json=None):
        calls.append({"path": path, "json": json})
        return {"id": "domain-1", "base_url": "https://brand.example", "name": "Brand"}

    monkeypatch.setattr(visibility.client, "post", fake_post)
    out = visibility.aeko_add_domain(
        base_url="https://brand.example",
        display_name="Brand",
        scope="beauty",
        ko_name="브랜드",
    )

    assert "domain-1" in out
    assert calls == [
        {
            "path": "/api/domains",
            "json": {
                "base_url": "https://brand.example",
                "display_name": "Brand",
                "scope": "beauty",
                "ko_name": "브랜드",
            },
        }
    ]


def test_store_tools_call_expected_routes(monkeypatch):
    calls = []

    def fake_get(path, params=None):
        calls.append({"method": "GET", "path": path, "params": params})
        return [{"id": "prod-1", "external_product_id": "sku-1", "title": "Gift cream"}]

    def fake_post(path, json=None, headers=None):
        calls.append({"method": "POST", "path": path, "json": json, "headers": headers})
        if path.endswith("/sync"):
            return [{"id": "prod-1", "external_product_id": "sku-1"}]
        return {"id": "store-1", "platform": json.get("platform", "manual"), "synced": len(json.get("products", []))}

    monkeypatch.setattr(store_write.client, "get", fake_get)
    monkeypatch.setattr(store_write.client, "post", fake_post)

    connect_out = store_write.aeko_connect_store(
        domain_id="domain-1",
        platform="shopify",
        store_identifier="brand.myshopify.com",
        access_token="token-1",
    )
    sync_out = store_write.aeko_sync_store("store-1")
    list_out = store_write.aeko_list_store_products(domain_id="domain-1", include_citability=True, limit=25)

    assert "store-1" in connect_out
    assert "prod-1" in sync_out
    assert "sku-1" in list_out
    assert calls == [
        {
            "method": "POST",
            "path": "/api/store-integrations",
            "json": {
                "domain_id": "domain-1",
                "platform": "shopify",
                "store_identifier": "brand.myshopify.com",
                "access_token": "token-1",
            },
            "headers": None,
        },
        {"method": "POST", "path": "/api/store-integrations/store-1/sync", "json": None, "headers": None},
        {
            "method": "GET",
            "path": "/api/store-products",
            "params": {"domain_id": "domain-1", "include_citability": True, "limit": 25, "offset": 0, "sort": "synced_desc"},
        },
    ]


def test_connect_store_rejects_manual_platform_without_call(monkeypatch):
    called = {"post": False}
    monkeypatch.setattr(store_write.client, "post", lambda *a, **k: called.__setitem__("post", True) or {})

    out = store_write.aeko_connect_store(
        domain_id="domain-1",
        platform="manual",
        store_identifier="manual",
        access_token="not-used",
    )

    assert "aeko_inject_products" in out
    assert called["post"] is False


def test_inject_products_chunks_over_200(monkeypatch):
    calls = []

    def fake_post(path, json=None, headers=None):
        calls.append({"path": path, "size": len(json["products"])})
        return {"domain_id": json["domain_id"], "integration_id": "store-1", "requested": len(json["products"]), "synced": len(json["products"]), "skipped": 0}

    monkeypatch.setattr(store_write.client, "post", fake_post)
    products = [
        {
            "external_product_id": f"sku-{i}",
            "title": f"Product {i}",
            "product_url": f"https://brand.example/admin/{i}",
            "public_url": f"https://brand.example/products/{i}",
        }
        for i in range(450)
    ]

    out = store_write.aeko_inject_products("domain-1", products)

    assert calls == [
        {"path": "/api/store-integrations/products/inject", "size": 200},
        {"path": "/api/store-integrations/products/inject", "size": 200},
        {"path": "/api/store-integrations/products/inject", "size": 50},
    ]
    assert '"synced": 450' in out


def test_atomic_product_page_update_sends_one_fenced_patch(monkeypatch):
    calls = []
    integration_id = "6f9b2c4e-2a1d-4d8e-9b7a-1c2d3e4f5a6b"
    claim_id = "0c7e1a52-8d6f-4b1e-a3c9-5e2d7f8a9b10"
    audit_id = "9a8b7c6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d"

    def fake_post(path, json=None, headers=None):
        calls.append({"path": path, "json": json, "headers": headers})
        return {
            "audit_id": audit_id,
            "platform": "shopify",
            "external_product_id": "sku-1",
            "status": "success",
        }

    monkeypatch.setattr(store_write.client, "post", fake_post)

    receipt = store_write.aeko_update_product_page(
        integration_id=integration_id,
        external_product_id="sku-1",
        action_item_id="itm_1",
        execution_claim_id=claim_id,
        description_html="<section>Evidence</section>",
        json_ld={"@context": "https://schema.org", "@type": "Product"},
        tags=["gift"],
        meta_title="Gift cream",
        meta_description="Evidence-backed gift cream",
        skip_aeko_shop=True,
    )

    assert receipt.audit_id == audit_id
    assert receipt.store_integration_id == integration_id
    assert receipt.external_product_id == "sku-1"
    assert (receipt.status, receipt.store_updated, receipt.admin_url) == ("success", True, None)
    assert calls == [
        {
            "path": f"/api/store-integrations/{integration_id}/products/sku-1",
            "json": {
                "skip_aeko_shop": True,
                "description": "<section>Evidence</section>",
                "json_ld": {"@context": "https://schema.org", "@type": "Product"},
                "tags": ["gift"],
                "meta": {
                    "title": "Gift cream",
                    "description": "Evidence-backed gift cream",
                },
                "action_item_id": "itm_1",
                "execution_claim_id": claim_id,
            },
            "headers": None,
        }
    ]


def test_legacy_product_update_forwards_claim_fence(monkeypatch):
    calls = []

    def fake_post(path, json=None, headers=None):
        calls.append(json)
        return {
            "audit_id": "audit-1",
            "platform": "cafe24",
            "external_product_id": "7",
            "status": "success",
        }

    monkeypatch.setattr(store_write.client, "post", fake_post)
    store_write.aeko_update_product_meta(
        "store-1",
        "7",
        title="SEO",
        action_item_id="itm_jsonld",
        execution_claim_id="claim-jsonld",
    )

    assert calls == [
        {
            "meta": {"title": "SEO"},
            "action_item_id": "itm_jsonld",
            "execution_claim_id": "claim-jsonld",
        }
    ]


def test_quota_reads_prompt_quota_and_limit_status(monkeypatch):
    calls = []

    def fake_get(path, params=None):
        calls.append({"path": path, "params": params})
        if path == "/api/tracked-prompts/quota":
            return {"tracked_count": 8, "max_tracked_prompts": 20, "remaining": 12}
        if path == "/api/user":
            return {"package_type": "pro", "selected_markets": ["US"]}
        return {"domains": {"current": 1, "limit": 5}, "tracked_prompts": {"current": 8, "limit": 20}}

    monkeypatch.setattr(research.client, "get", fake_get)
    out = research.aeko_get_quota()

    assert calls == [
        {"path": "/api/tracked-prompts/quota", "params": None},
        {"path": "/api/users/limit-status", "params": None},
        {"path": "/api/user", "params": None},
    ]
    assert "tracked_prompt_quota" in out
    assert "limit_status" in out
    assert '"package_type": "pro"' in out


def test_setup_tools_call_expected_routes(monkeypatch):
    setup = importlib.import_module("aeko_mcp.tools.setup")
    calls = []

    def fake_post(path, json=None):
        calls.append({"method": "POST", "path": path, "json": json})
        return {"ok": True, "prompts": [{"prompt_text": "best gift cream"}], "results": []}

    def fake_put(path, json=None):
        calls.append({"method": "PUT", "path": path, "json": json})
        return {"selected_markets": json["markets"]}

    def fake_get(path, params=None):
        calls.append({"method": "GET", "path": path, "params": params})
        return {"selected_markets": ["KR"]}

    monkeypatch.setattr(setup.client, "post", fake_post)
    monkeypatch.setattr(setup.client, "put", fake_put)
    monkeypatch.setattr(setup.client, "get", fake_get)

    gen_out = setup.aeko_generate_starter_prompts("domain-1")
    accept_out = setup.aeko_accept_starter_prompts(
        "domain-1",
        [{"raw_prompt": "best gift cream", "prompt_kind": "discovery", "target_market": "US"}],
    )
    current_markets_out = setup.aeko_get_current_markets()
    markets_out = setup.aeko_update_markets(["US", "KR"])

    assert "best gift cream" in gen_out
    assert "results" in accept_out
    assert "KR" in current_markets_out
    assert "US" in markets_out
    assert calls == [
        {"method": "POST", "path": "/api/tracked-prompts/starter/generate", "json": {"domain_id": "domain-1"}},
        {
            "method": "POST",
            "path": "/api/tracked-prompts/starter/accept",
            "json": {
                "domain_id": "domain-1",
                "selections": [{"raw_prompt": "best gift cream", "prompt_kind": "discovery", "target_market": "US"}],
            },
        },
        {"method": "GET", "path": "/api/user", "params": None},
        {"method": "PUT", "path": "/api/user/markets", "json": {"markets": ["US", "KR"]}},
    ]


def test_starter_prompt_generate_output_can_pass_wholesale_to_accept(monkeypatch):
    setup = importlib.import_module("aeko_mcp.tools.setup")
    generated_prompt = {
        "prompt_text": "best gift cream",
        "prompt_kind": "discovery",
        "target_market": "US",
        "target_language": "en",
        "intent": "recommendation",
        "attributes_products": ["sku-1"],
    }
    calls = []

    def fake_post(path, json=None):
        calls.append({"path": path, "json": json})
        if path.endswith("/generate"):
            return {"prompts": [generated_prompt]}
        return {"results": [], "summary": {"requested": 1, "tracked": 1}}

    monkeypatch.setattr(setup.client, "post", fake_post)

    generated = setup.aeko_generate_starter_prompts("domain-1")
    accepted = setup.aeko_accept_starter_prompts("domain-1", [generated_prompt])

    assert '"prompt_text": "best gift cream"' in generated
    assert '"tracked": 1' in accepted
    assert calls == [
        {
            "path": "/api/tracked-prompts/starter/generate",
            "json": {"domain_id": "domain-1"},
        },
        {
            "path": "/api/tracked-prompts/starter/accept",
            "json": {
                "domain_id": "domain-1",
                "selections": [
                    {
                        "raw_prompt": "best gift cream",
                        "prompt_kind": "discovery",
                        "target_market": "US",
                        "attributes_products": ["sku-1"],
                    }
                ],
            },
        },
    ]


def test_accept_starter_prompts_rejects_missing_prompt_text_locally(monkeypatch):
    setup = importlib.import_module("aeko_mcp.tools.setup")
    called = {"post": False}

    def unexpected_post(*args, **kwargs):
        called["post"] = True
        return {}

    monkeypatch.setattr(setup.client, "post", unexpected_post)
    output = setup.aeko_accept_starter_prompts(
        "domain-1",
        [{"prompt_kind": "discovery", "target_market": "US"}],
    )

    assert "must include `raw_prompt` or generated `prompt_text`" in output
    assert called["post"] is False


def test_store_integrations_surface_partial_sync_status(monkeypatch):
    monkeypatch.setattr(
        store_write.client,
        "get",
        lambda *args, **kwargs: [
            {
                "id": "store-1",
                "domain_id": "domain-1",
                "platform": "cafe24",
                "store_identifier": "shop",
                "scopes": "mall.write_product",
                "last_sync_status": "partial_failure",
                "last_sync_error_message": "17 products could not be fetched",
            }
        ],
    )

    out = store_write.aeko_list_store_integrations()

    assert "Last sync status**: partial_failure" in out
    assert "17 products could not be fetched" in out
