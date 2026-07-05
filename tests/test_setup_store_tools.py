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


def test_quota_reads_prompt_quota_and_limit_status(monkeypatch):
    calls = []

    def fake_get(path, params=None):
        calls.append({"path": path, "params": params})
        if path == "/api/tracked-prompts/quota":
            return {"tracked_count": 8, "max_tracked_prompts": 20, "remaining": 12}
        return {"domains": {"current": 1, "limit": 5}, "tracked_prompts": {"current": 8, "limit": 20}}

    monkeypatch.setattr(research.client, "get", fake_get)
    out = research.aeko_get_quota()

    assert calls == [
        {"path": "/api/tracked-prompts/quota", "params": None},
        {"path": "/api/users/limit-status", "params": None},
    ]
    assert "tracked_prompt_quota" in out
    assert "limit_status" in out


def test_setup_tools_call_expected_routes(monkeypatch):
    setup = importlib.import_module("aeko_mcp.tools.setup")
    calls = []

    def fake_post(path, json=None):
        calls.append({"method": "POST", "path": path, "json": json})
        return {"ok": True, "prompts": [{"prompt_text": "best gift cream"}], "results": []}

    def fake_put(path, json=None):
        calls.append({"method": "PUT", "path": path, "json": json})
        return {"selected_markets": json["markets"]}

    monkeypatch.setattr(setup.client, "post", fake_post)
    monkeypatch.setattr(setup.client, "put", fake_put)

    gen_out = setup.aeko_generate_starter_prompts("domain-1")
    accept_out = setup.aeko_accept_starter_prompts(
        "domain-1",
        [{"raw_prompt": "best gift cream", "prompt_kind": "discovery", "target_market": "US"}],
    )
    markets_out = setup.aeko_update_markets(["US", "KR"])

    assert "best gift cream" in gen_out
    assert "results" in accept_out
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
        {"method": "PUT", "path": "/api/user/markets", "json": {"markets": ["US", "KR"]}},
    ]
