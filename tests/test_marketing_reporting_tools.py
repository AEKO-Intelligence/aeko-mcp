"""Read-only OpenAI Ads reporting tools, exercised through FastMCP registration (no network)."""
import asyncio
import inspect
import json
import re

import httpx
import pytest

from aeko_mcp.server import client, mcp
from aeko_mcp.tools import marketing_reporting

DOMAIN = "11111111-1111-4111-8111-111111111111"
ACCOUNT = "22222222-2222-4222-8222-222222222222"
CAMPAIGN = "33333333-3333-4333-8333-333333333333"
DUMMY_TOKEN = "aeko_ot1_dummy-test-token"
REPORTING_TOOLS = {"aeko_list_ad_accounts", "aeko_get_product_insights", "aeko_get_conversion_insights"}


@pytest.fixture
def backend(monkeypatch):
    """Route the shared AEKO client through a mock transport and record every request."""
    state = {"requests": [], "response": httpx.Response(200, json={})}

    def handler(request: httpx.Request) -> httpx.Response:
        state["requests"].append(request)
        response = state["response"]
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(
        client, "_client", httpx.Client(base_url="http://aeko.test", transport=httpx.MockTransport(handler))
    )
    ctx = client.set_request_auth_token(DUMMY_TOKEN)
    yield state
    client.reset_request_auth_token(ctx)


def _call(name: str, **arguments) -> str:
    return asyncio.run(mcp._tool_manager.call_tool(name, arguments))


def _payload(output: str):
    match = re.search(r"```json\n(.*)\n```", output, re.S)
    assert match, output
    return json.loads(match.group(1))


def _product_response(**page):
    return {
        "ad_account_id": ACCOUNT,
        "account_currency": "KRW",
        "account_timezone": "Asia/Seoul",
        "scope": "campaign",
        "scope_remote_id": "cmp_remote",
        "date_from": "2026-09-01",
        "date_to": "2026-09-07",
        "sort": "product_impressions_desc",
        "page": {
            "limit": 10,
            "after": "cursor-1",
            "has_more": True,
            "next_cursor": "cursor-2",
            "paging_blocked": False,
            "blocked_reason": None,
            **page,
        },
        "carousel": {"status": "not_requested", "reason": None},
        "rows": [
            {
                "identity": {"feed_id": "feed_1", "item_id": "sku-1", "status": "complete"},
                "key": '["feed_1","sku-1"]',
                "title": "Serum",
                "impressions": 0,
                "clicks": None,
                "spend_micros": 0,
                "carousel_card_impressions": None,
                "carousel_card_clicks": None,
                "issues": ["clicks_missing"],
            },
            {
                "identity": {"feed_id": "feed_2", "item_id": None, "status": "missing_item_id"},
                "key": None,
                "title": None,
                "impressions": None,
                "clicks": 0,
                "spend_micros": None,
                "carousel_card_impressions": 7,
                "carousel_card_clicks": 0,
                "issues": [],
            },
        ],
    }


def _conversion_response():
    return {
        "scope": "campaign",
        "ad_account_id": ACCOUNT,
        "date_from": "2026-09-01",
        "date_to": "2026-09-02",
        "account_timezone": "Asia/Seoul",
        "account_currency": "KRW",
        "latest_completed_date": "2026-09-01",
        "state": "stale",
        "state_reasons": ["INCLUDES_INCOMPLETE_DATES", "ROWS_NOT_RETURNED", "STALE_DATES"],
        "blocked_reason": None,
        "freshness_threshold_hours": 36,
        "restatement_days": 30,
        "last_refreshed_at": "2026-09-01T00:00:00Z",
        "oldest_refreshed_at": "2026-09-01T00:00:00Z",
        "coverage": {
            "requested_days": 2,
            "completed_days": 1,
            "covered_days": 1,
            "stale_days": 1,
            "pending_days": 1,
            "uncovered_days": 0,
        },
        "latest_attempt": {"run_id": "44444444-4444-4444-8444-444444444444", "status": "failed",
                           "failure_code": "PROVIDER_RATE_LIMITED", "failure_message": "Rate limited."},
        "latest_success": None,
        "attribution": {
            "conversion_event_setting_id": None,
            "click_through_window_days": None,
            "view_through_window_days": 1,
        },
        "campaigns": [
            {
                "remote_campaign_id": "cmp_remote",
                "campaign_id": CAMPAIGN,
                "coverage": "unavailable",
                "requested_days": 1,
                "reported_days": 0,
                "stale_days": 1,
                "conversions": {"value": None, "reported_days": 0},
                "click_through_conversions": {"value": 0, "reported_days": 1},
                "view_through_conversions": {"value": None, "reported_days": 0},
                "days": [
                    {"date": "2026-09-01", "status": "omitted", "conversions": None, "stale": True},
                    {"date": "2026-09-02", "status": "pending", "conversions": None, "stale": False},
                ],
            }
        ],
    }


# --- Registration -----------------------------------------------------------------


def test_reporting_tools_register_read_only_with_explicit_account():
    registered = {tool.name: tool for tool in mcp._tool_manager.list_tools()}
    assert REPORTING_TOOLS <= registered.keys()
    for name in REPORTING_TOOLS:
        tool = registered[name]
        assert tool.annotations.readOnlyHint is True
        assert tool.annotations.idempotentHint is True
        assert tool.annotations.destructiveHint is not True
        for parameter in inspect.signature(tool.fn).parameters.values():
            assert not isinstance(parameter.annotation, str)
    for name in ("aeko_get_product_insights", "aeko_get_conversion_insights"):
        required = set(registered[name].parameters["required"])
        assert {"domain_id", "ad_account_id", "date_from", "date_to"} <= required
    assert "scope" not in registered["aeko_get_conversion_insights"].parameters["properties"]
    assert set(registered["aeko_list_ad_accounts"].parameters["required"]) == {"domain_id"}


def test_legacy_ad_insights_signature_is_unchanged_and_points_to_stored_conversions():
    registered = {tool.name: tool for tool in mcp._tool_manager.list_tools()}
    tool = registered["aeko_get_ad_insights"]
    assert list(inspect.signature(tool.fn).parameters) == [
        "domain_id", "date_from", "date_to", "scope", "scope_id", "segment", "limit", "ad_account_id",
    ]
    assert "not yet ingested" not in tool.description
    assert "aeko_get_conversion_insights" in tool.description


# --- Account listing --------------------------------------------------------------


def test_list_ad_accounts_projects_selection_fields_without_configuration(backend):
    backend["response"] = httpx.Response(200, json=[
        {"id": ACCOUNT, "domain_id": DOMAIN, "connected": True, "status": "connected",
         "account_name": "Main", "currency_code": "KRW", "timezone": "Asia/Seoul",
         "has_openai_api_key": True, "sftp_host": "sftp.example", "sftp_user": "feed",
         "pixel_id": "px_1", "conversions_api_token_configured": True},
        {"id": CAMPAIGN, "domain_id": DOMAIN, "connected": False, "status": "disconnected",
         "timezone": None},
    ])
    output = _call("aeko_list_ad_accounts", domain_id=DOMAIN)

    [request] = backend["requests"]
    assert request.method == "GET"
    assert request.url.path == "/api/marketing/ad-accounts"
    assert dict(request.url.params) == {"domain_id": DOMAIN}
    assert request.headers["Authorization"] == f"Bearer {DUMMY_TOKEN}"
    payload = _payload(output)
    assert payload["count"] == 2 and payload["connected_count"] == 1
    first = payload["accounts"][0]
    assert first["timezone"] == "Asia/Seoul" and first["currency_code"] == "KRW"
    for hidden in ("has_openai_api_key", "sftp_host", "sftp_user", "pixel_id", "conversions_api_token_configured"):
        assert hidden not in first
    assert "sftp.example" not in output


# --- Product insights -------------------------------------------------------------


def test_product_insights_forwards_one_page_with_account_scope_and_cursor(backend):
    backend["response"] = httpx.Response(200, json=_product_response())
    output = _call(
        "aeko_get_product_insights",
        domain_id=DOMAIN, ad_account_id=ACCOUNT, date_from="2026-09-01", date_to="2026-09-07",
        scope="campaign", scope_id=CAMPAIGN, limit=10, after="cursor-1",
    )

    [request] = backend["requests"]  # has_more=True still means exactly one request
    assert request.method == "GET"
    assert request.url.path == "/api/marketing/product-insights"
    assert dict(request.url.params) == {
        "domain_id": DOMAIN, "ad_account_id": ACCOUNT, "scope": "campaign", "scope_id": CAMPAIGN,
        "date_from": "2026-09-01", "date_to": "2026-09-07", "limit": "10", "after": "cursor-1",
    }
    assert _payload(output) == _product_response()
    assert "next_cursor" in output and "not a complete" in output


def test_product_insights_preserves_null_versus_zero_and_carousel_separation(backend):
    backend["response"] = httpx.Response(200, json=_product_response())
    rows = _payload(_call(
        "aeko_get_product_insights",
        domain_id=DOMAIN, ad_account_id=ACCOUNT, date_from="2026-09-01", date_to="2026-09-07",
    ))["rows"]
    assert rows[0]["impressions"] == 0 and rows[0]["clicks"] is None
    assert rows[1]["impressions"] is None and rows[1]["clicks"] == 0
    assert rows[1]["carousel_card_impressions"] == 7  # never folded into impressions
    assert rows[1]["identity"] == {"feed_id": "feed_2", "item_id": None, "status": "missing_item_id"}


def test_product_insights_defaults_to_account_scope_limit_25_without_cursor(backend):
    backend["response"] = httpx.Response(200, json=_product_response(has_more=False, next_cursor=None))
    output = _call(
        "aeko_get_product_insights",
        domain_id=DOMAIN, ad_account_id=ACCOUNT, date_from="2026-06-07", date_to="2026-09-07",
    )  # 93 inclusive days is the backend maximum
    params = dict(backend["requests"][0].url.params)
    assert params["scope"] == "account" and params["limit"] == "25"
    assert "scope_id" not in params and "after" not in params
    assert "no further rows" in output


def test_product_insights_reports_blocked_paging_as_unknown_completeness(backend):
    response = _product_response(has_more=None, next_cursor=None, paging_blocked=True,
                                 blocked_reason="has_more_missing")
    response["carousel"] = {"status": "rejected", "reason": "PROVIDER_REJECTED_FIELDS"}
    backend["response"] = httpx.Response(200, json=response)
    output = _call(
        "aeko_get_product_insights",
        domain_id=DOMAIN, ad_account_id=ACCOUNT, date_from="2026-09-01", date_to="2026-09-07",
    )
    payload = _payload(output)
    assert payload["page"]["paging_blocked"] is True and payload["page"]["has_more"] is None
    assert payload["carousel"] == {"status": "rejected", "reason": "PROVIDER_REJECTED_FIELDS"}
    assert "has_more_missing" in output and "`rejected`" in output


BASE_PRODUCT = {"domain_id": DOMAIN, "ad_account_id": ACCOUNT, "date_from": "2026-09-01", "date_to": "2026-09-07"}


@pytest.mark.parametrize(
    "overrides",
    [
        {"ad_account_id": ""},
        {"ad_account_id": "act_remote_123"},
        {"domain_id": "not-a-uuid"},
        {"scope": "ad_group", "scope_id": CAMPAIGN},
        {"scope": "campaign"},
        {"scope_id": CAMPAIGN},
        {"limit": 0},
        {"limit": 51},
        {"after": ""},
        {"after": "x" * 513},
        {"date_from": "2026-9-01"},
        {"date_to": "2026-02-30"},
        {"date_from": "2026-09-08"},
        {"date_from": "2026-06-06"},  # 94 inclusive days
    ],
)
def test_product_insights_rejects_invalid_input_without_a_request(backend, overrides):
    output = _call("aeko_get_product_insights", **{**BASE_PRODUCT, **overrides})
    assert output.startswith("# Failed to get product insights")
    assert "No request was sent." in output
    assert backend["requests"] == []


# --- Stored conversion insights ---------------------------------------------------


def test_conversion_insights_reads_stored_campaign_report_verbatim(backend):
    backend["response"] = httpx.Response(200, json=_conversion_response())
    output = _call(
        "aeko_get_conversion_insights",
        domain_id=DOMAIN, ad_account_id=ACCOUNT, date_from="2026-09-01", date_to="2026-09-02",
    )

    [request] = backend["requests"]
    assert request.method == "GET"
    assert request.url.path == "/api/marketing/conversion-insights"
    assert dict(request.url.params) == {
        "domain_id": DOMAIN, "ad_account_id": ACCOUNT, "scope": "campaign",
        "date_from": "2026-09-01", "date_to": "2026-09-02",
    }
    payload = _payload(output)
    assert payload == _conversion_response()
    campaign = payload["campaigns"][0]
    assert campaign["conversions"]["value"] is None
    assert campaign["click_through_conversions"] == {"value": 0, "reported_days": 1}
    assert [day["status"] for day in campaign["days"]] == ["omitted", "pending"]
    assert payload["latest_success"] is None and payload["latest_attempt"]["status"] == "failed"
    assert payload["attribution"]["click_through_window_days"] is None
    assert "`stale`" in output and "STALE_DATES" in output and "No refresh was requested." in output


def test_conversion_insights_surfaces_blocked_not_synced_state(backend):
    response = {**_conversion_response(), "state": "not_synced", "state_reasons": ["ACCOUNT_TIMEZONE_MISSING"],
                "blocked_reason": "ACCOUNT_TIMEZONE_MISSING", "campaigns": []}
    backend["response"] = httpx.Response(200, json=response)
    output = _call(
        "aeko_get_conversion_insights",
        domain_id=DOMAIN, ad_account_id=ACCOUNT, date_from="2026-09-01", date_to="2026-09-02",
    )
    assert "`not_synced`" in output and "blocked: `ACCOUNT_TIMEZONE_MISSING`" in output
    assert _payload(output)["campaigns"] == []


BASE_CONVERSION = {"domain_id": DOMAIN, "ad_account_id": ACCOUNT, "date_from": "2026-09-01", "date_to": "2026-09-02"}


@pytest.mark.parametrize(
    "overrides",
    [
        {"ad_account_id": ""},
        {"domain_id": "example.com"},
        {"date_to": "2026-08-31"},
        {"date_from": "20260901"},
        {"date_from": "2026-06-01", "date_to": "2026-09-01"},  # 93 inclusive days
    ],
)
def test_conversion_insights_rejects_invalid_input_without_a_request(backend, overrides):
    output = _call("aeko_get_conversion_insights", **{**BASE_CONVERSION, **overrides})
    assert output.startswith("# Failed to get conversion insights")
    assert "No request was sent." in output
    assert backend["requests"] == []


def test_conversion_insights_accepts_92_day_window(backend):
    backend["response"] = httpx.Response(200, json=_conversion_response())
    _call("aeko_get_conversion_insights", **{**BASE_CONVERSION, "date_from": "2026-06-01", "date_to": "2026-08-31"})
    assert len(backend["requests"]) == 1


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("aeko_get_conversion_insights", {k: v for k, v in BASE_CONVERSION.items() if k != "ad_account_id"}),
        ("aeko_get_product_insights", {k: v for k, v in BASE_PRODUCT.items() if k != "ad_account_id"}),
        ("aeko_get_product_insights", {**BASE_PRODUCT, "limit": "ten"}),
    ],
)
def test_schema_rejects_missing_account_or_non_integer_limit_before_a_request(backend, tool, arguments):
    with pytest.raises(Exception, match="ad_account_id|limit"):
        _call(tool, **arguments)
    assert backend["requests"] == []


# --- Errors -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("tool", "response", "expected"),
    [
        ("aeko_get_product_insights", httpx.Response(401, json={"detail": "Invalid token"}), "Authentication failed"),
        ("aeko_get_product_insights",
         httpx.Response(502, json={"detail": {"code": "PROVIDER_RESPONSE_MALFORMED", "message": "Bad rows."}}),
         "[PROVIDER_RESPONSE_MALFORMED] Bad rows."),
        ("aeko_get_product_insights",
         httpx.Response(409, json={"detail": {"code": "ACCOUNT_TIMEZONE_MISSING", "message": "No timezone."}}),
         "[ACCOUNT_TIMEZONE_MISSING]"),
        ("aeko_get_product_insights",
         httpx.Response(422, json={"detail": {"code": "MARKETING_PRODUCT_INSIGHTS_DATE_INCOMPLETE",
                                              "message": "Completed dates through 2026-09-06."}}),
         "MARKETING_PRODUCT_INSIGHTS_DATE_INCOMPLETE"),
        ("aeko_get_conversion_insights",
         httpx.Response(404, json={"detail": {"code": "OPENAI_ADS_ACCOUNT_NOT_FOUND", "message": "Connect first."}}),
         "[OPENAI_ADS_ACCOUNT_NOT_FOUND]"),
        ("aeko_get_conversion_insights", httpx.Response(403, json={"detail": "Pro+ required"}), "Pro+ required"),
        ("aeko_list_ad_accounts", httpx.Response(404, json={"detail": "Domain not found"}), "Domain not found"),
        ("aeko_list_ad_accounts", httpx.ConnectError("boom"), "Cannot connect to AEKO API"),
    ],
)
def test_backend_errors_surface_without_leaking_the_bearer_token(backend, tool, response, expected):
    backend["response"] = response
    arguments = {"domain_id": DOMAIN}
    if tool != "aeko_list_ad_accounts":
        arguments.update(ad_account_id=ACCOUNT, date_from="2026-09-01", date_to="2026-09-02")
    output = _call(tool, **arguments)
    assert output.startswith("# Failed to")
    assert expected in output
    assert DUMMY_TOKEN not in output and "Bearer" not in output
    assert len(backend["requests"]) == 1  # no retry loop
    assert "```json" not in output


def test_reporting_module_never_writes(monkeypatch):
    for method in ("post", "patch", "put", "delete"):
        monkeypatch.setattr(client, method, lambda *a, **k: pytest.fail(f"unexpected {method}"))
    source = inspect.getsource(marketing_reporting)
    assert not re.search(r"client\.(post|patch|put|delete)\b", source)
