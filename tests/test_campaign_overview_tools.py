import json
from uuid import uuid4

import httpx
import pytest

from aeko_mcp.client import AekoAPIError
from aeko_mcp.server import mcp
from aeko_mcp.tools import campaign_overview as tools
from aeko_mcp.tools._structured import AekoToolError, AekoToolInputError

DOMAIN = str(uuid4())
ACCOUNT = str(uuid4())
CAMPAIGN = str(uuid4())
PRODUCT = str(uuid4())
AD = str(uuid4())
GROUP = str(uuid4())
ITEM = str(uuid4())


def code(exc):
    return json.loads(str(exc.value))


def ad(ad_id=AD, **extra):
    return {"id": ad_id, "name": "Ad", "status": "active", "review_status": "approved",
            "creative": {"title": "Title", "body": "Body"}, "auto_added": True, **extra}


def overview_payload(campaigns=None):
    return {
        "account": {"id": ACCOUNT, "name": "Acct", "currency_code": "USD", "timezone": "Asia/Seoul"},
        "capacity": {"used": None, "limit": 100, "warn_at": 80, "observed_at": None},
        "archived_campaigns": 2,
        "campaigns": campaigns if campaigns is not None else [{
            "id": CAMPAIGN, "name": "Camp", "status": "active", "kind": "always_on",
            "display_state": "running", "bidding_type": "impressions", "countries": ["US"],
            "ad_group_count": 1, "ad_count": 1, "product_count": 1,
            "products": [{
                "store_product_id": PRODUCT, "title": "Cream", "ad_count": 1, "added_today": 1,
                "ad_groups": [{"id": GROUP, "name": "Group", "status": "active"}], "ads": [ad()],
            }],
        }],
    }


NUMBERS = {
    "as_of": "2026-10-28T01:00:00Z", "collecting": False, "window": {"from": "2026-09-29", "to": "2026-10-28"},
    "account": {"impressions": 10, "clicks": None, "spend_micros": 5},
    "campaigns": {CAMPAIGN: {"impressions": 10, "clicks": 1, "spend_micros": 5}},
    "products": {f"{CAMPAIGN}:{PRODUCT}": {"impressions": 4, "clicks": None, "spend_micros": None}},
    "ads": {AD: {"impressions": 0, "clicks": 0, "spend_micros": 0}},
    "mention": {AD: {"rate": 0.5, "responses": 8}},
}
ATTENTION = {
    "total": 3, "rejected_total": 1, "saved_drafts": {"count": 4},
    "rejected_ads": [{"ad": {"id": AD, "name": "Bad"}, "campaign_id": CAMPAIGN, "campaign_name": "Camp",
                      "product_title": "Cream", "reason": "policy"}],
    "pending_placements": [{"ad_set_item_id": ITEM}],
}


def serve(monkeypatch, overview=None, numbers=None, attention=None, calls=None):
    def get(path, params=None):
        if calls is not None:
            calls.append((path, params))
        if path.endswith("/numbers"):
            return NUMBERS if numbers is None else numbers
        if path.endswith("/attention"):
            return ATTENTION if attention is None else attention
        return overview_payload() if overview is None else overview
    monkeypatch.setattr(tools.client, "get", get)


def test_registered_with_right_annotations():
    registered = {tool.name: tool for tool in mcp._tool_manager.list_tools()}
    for name in ("aeko_get_campaign_overview", "aeko_list_product_ads", "aeko_list_open_placements"):
        assert registered[name].annotations.readOnlyHint is True
    write = registered["aeko_answer_open_placement"].annotations
    assert write.readOnlyHint is False and write.destructiveHint is True and write.openWorldHint is True
    doc = registered["aeko_answer_open_placement"].description
    assert "PAUSED" in doc and "explicit yes" in doc
    flat = " ".join(doc.split())
    assert "identical answer returns the first result" in flat and "Not repeatable" not in flat


def test_overview_merges_three_reads_and_keeps_absent_numbers_null(monkeypatch):
    calls = []
    serve(monkeypatch, calls=calls)
    result = tools.aeko_get_campaign_overview(DOMAIN, ACCOUNT, days=7, ads_per_product=2)
    assert calls == [
        (tools.BASE, {"domain_id": DOMAIN, "ad_account_id": ACCOUNT, "ads_per_product": 2}),
        (f"{tools.BASE}/numbers", {"domain_id": DOMAIN, "ad_account_id": ACCOUNT, "days": 7}),
        (f"{tools.BASE}/attention", {"domain_id": DOMAIN, "ad_account_id": ACCOUNT}),
    ]
    campaign = result.campaigns[0]
    assert campaign.numbers.clicks == 1
    product = campaign.products[0]
    assert product.numbers.impressions == 4 and product.numbers.clicks is None and product.numbers.spend_micros is None
    assert product.ads[0].numbers.impressions == 0  # a reported zero stays 0
    assert product.ads[0].mention_rate == 0.5 and product.ads[0].title == "Title" and product.ads[0].auto_added
    assert result.account_numbers.clicks is None
    assert result.attention.open_placements == 1 and result.attention.saved_drafts == 4
    assert result.attention.rejected_ads[0].reason == "policy"
    assert "not live" in result.numbers_note and result.numbers_window == NUMBERS["window"]
    assert result.output_limited is False


def test_overview_absent_entries_are_null_not_zero(monkeypatch):
    serve(monkeypatch, numbers={"window": {"from": "a", "to": "b"}, "account": None, "campaigns": {}, "products": {}, "ads": {}})
    result = tools.aeko_get_campaign_overview(DOMAIN)
    assert result.account_numbers is None
    assert result.campaigns[0].numbers is None
    assert result.campaigns[0].products[0].numbers is None
    assert result.campaigns[0].products[0].ads[0].numbers is None
    assert result.campaigns[0].products[0].ads[0].mention_rate is None
    assert result.numbers_as_of is None


def test_overview_without_account_params_omits_ad_account_id(monkeypatch):
    calls = []
    serve(monkeypatch, overview={"account": None, "campaigns": []}, calls=calls)
    result = tools.aeko_get_campaign_overview(DOMAIN)
    assert all("ad_account_id" not in params for _, params in calls)
    assert result.campaigns == [] and result.account is None


def _big_campaigns(campaigns, products, ads, text="x"):
    return [{
        "id": str(uuid4()), "name": f"Campaign {i} " + text * 20, "status": "active", "countries": [],
        "products": [{
            "store_product_id": str(uuid4()), "title": text * 20, "ad_count": ads, "ad_groups": [],
            "ads": [ad(str(uuid4()), name=text * 30, creative={"title": text * 25, "body": text * 50})
                    for _ in range(ads)],
        } for _ in range(products)],
    } for i in range(campaigns)]


def test_overview_truncates_large_accounts_with_flags(monkeypatch):
    serve(monkeypatch, overview=overview_payload(_big_campaigns(40, 8, 5)))
    result = tools.aeko_get_campaign_overview(DOMAIN, ads_per_product=5)
    assert result.output_limited is True
    assert tools.text_bytes(result) <= tools.MAX_PAGE_CHARS
    assert len(result.campaigns) + result.campaigns_omitted == 40
    for campaign in result.campaigns:
        assert len(campaign.products) + campaign.products_omitted == 8
        for product in campaign.products:
            assert len(product.ads) + product.ads_omitted == 5


def test_overview_korean_text_keeps_ads_before_dropping_them(monkeypatch):
    # 3 campaigns x 5 products x 3 Korean ads: shrinks ad by ad, not straight to zero ads.
    serve(monkeypatch, overview=overview_payload(_big_campaigns(3, 5, 3, text="가")))
    result = tools.aeko_get_campaign_overview(DOMAIN, ads_per_product=3)
    assert tools.text_bytes(result) <= tools.MAX_PAGE_CHARS
    shown = [len(p.ads) for c in result.campaigns for p in c.products]
    assert len(result.campaigns) == 3 and len(shown) == 15
    assert min(shown) >= 1
    assert result.output_limited is (max(shown) < 3)


def test_overview_many_long_rejected_ads_still_fit(monkeypatch):
    rejected = [{"ad": {"id": str(uuid4()), "name": "가" * 400}, "campaign_name": "나" * 400,
                 "product_title": "다" * 400, "reason": "라" * 2000} for _ in range(200)]
    serve(monkeypatch, attention={"total": 200, "rejected_total": 200, "rejected_ads": rejected, "pending_placements": []})
    result = tools.aeko_get_campaign_overview(DOMAIN)
    assert tools.text_bytes(result) <= tools.MAX_PAGE_CHARS
    assert all(len(r.reason) <= tools.MAX_REJECTED_TEXT for r in result.attention.rejected_ads)
    assert result.attention.rejected_ads_omitted == 200 - len(result.attention.rejected_ads)


def test_overview_rejected_list_drops_before_campaigns(monkeypatch):
    rejected = [{"ad": {"id": str(uuid4()), "name": "가" * 100}, "campaign_name": "나" * 100,
                 "product_title": "다" * 100, "reason": "라" * 100} for _ in range(20)]
    serve(monkeypatch, overview=overview_payload(_big_campaigns(5, 5, 3, text="가")),
          attention={"total": 20, "rejected_total": 20, "rejected_ads": rejected, "pending_placements": []})
    result = tools.aeko_get_campaign_overview(DOMAIN)
    assert tools.text_bytes(result) <= tools.MAX_PAGE_CHARS
    assert result.attention.rejected_ads_omitted == 20 - len(result.attention.rejected_ads)


def test_overview_caps_rejected_list(monkeypatch):
    rejected = [{"ad": {"id": str(uuid4()), "name": "r"}, "reason": "x"} for _ in range(30)]
    serve(monkeypatch, attention={"total": 30, "rejected_total": 30, "rejected_ads": rejected, "pending_placements": []})
    result = tools.aeko_get_campaign_overview(DOMAIN)
    assert len(result.attention.rejected_ads) == tools.MAX_REJECTED_SHOWN
    assert result.attention.rejected_ads_omitted == 10


@pytest.mark.parametrize("kwargs", [
    {"domain_id": "bad"}, {"domain_id": DOMAIN, "ad_account_id": "bad"},
    {"domain_id": DOMAIN, "days": 0}, {"domain_id": DOMAIN, "days": 91}, {"domain_id": DOMAIN, "days": True},
    {"domain_id": DOMAIN, "ads_per_product": 0}, {"domain_id": DOMAIN, "ads_per_product": 21},
])
def test_overview_rejects_bad_input_before_request(monkeypatch, kwargs):
    monkeypatch.setattr(tools.client, "get", lambda *a, **k: pytest.fail("backend called"))
    with pytest.raises(AekoToolInputError) as exc:
        tools.aeko_get_campaign_overview(**kwargs)
    assert code(exc)["code"] == "INVALID_ARGUMENT"


def test_overview_rejects_malformed_backend_response(monkeypatch):
    monkeypatch.setattr(tools.client, "get", lambda *a, **k: ["not", "a", "dict"])
    with pytest.raises(AekoToolError) as exc:
        tools.aeko_get_campaign_overview(DOMAIN)
    assert code(exc)["code"] == "INVALID_BACKEND_RESPONSE"


def test_overview_backend_error_is_a_bounded_tool_error(monkeypatch):
    def get(*a, **k):
        raise AekoAPIError("secret backend body", http_status=403, request_sent=True)
    monkeypatch.setattr(tools.client, "get", get)
    with pytest.raises(AekoToolError) as exc:
        tools.aeko_get_campaign_overview(DOMAIN)
    payload = code(exc)
    assert payload["code"] == "ACCESS_DENIED" and payload["mutation_state"] == "not_attempted"
    assert "secret" not in str(exc.value)


def test_list_product_ads_passes_bucket_and_pages(monkeypatch):
    calls = []
    def get(path, params=None):
        calls.append((path, params))
        return {"ads": [ad(str(uuid4())) for _ in range(2)], "total": 7}
    monkeypatch.setattr(tools.client, "get", get)
    result = tools.aeko_list_product_ads(DOMAIN, CAMPAIGN, PRODUCT, offset=3, limit=2)
    assert calls == [(f"{tools.BASE}/ads", {
        "domain_id": DOMAIN, "campaign_id": CAMPAIGN, "store_product_id": PRODUCT, "offset": 3, "limit": 2})]
    assert result.returned_count == 2 and result.next_offset == 5 and result.has_more
    assert result.ads[0].title == "Title" and result.ads[0].numbers is None


def test_list_product_ads_last_page_and_none_bucket(monkeypatch):
    monkeypatch.setattr(tools.client, "get", lambda path, params=None: {"ads": [ad()], "total": 1})
    result = tools.aeko_list_product_ads(DOMAIN, CAMPAIGN, "none")
    assert result.next_offset is None and result.has_more is False


def test_list_product_ads_shrinks_big_page_without_skipping(monkeypatch):
    big = [ad(str(uuid4()), name="n" * 250, creative={"title": "t" * 250, "body": "b" * 250}) for _ in range(100)]
    monkeypatch.setattr(tools.client, "get", lambda path, params=None: {"ads": big, "total": 150})
    result = tools.aeko_list_product_ads(DOMAIN, CAMPAIGN, PRODUCT, limit=100)
    assert result.output_limited is True and result.returned_count < 100
    assert result.next_offset == result.returned_count and tools.text_bytes(result) <= tools.MAX_PAGE_CHARS


@pytest.mark.parametrize("kwargs", [
    {"domain_id": "x", "campaign_id": CAMPAIGN, "store_product_id": PRODUCT},
    {"domain_id": DOMAIN, "campaign_id": "x", "store_product_id": PRODUCT},
    {"domain_id": DOMAIN, "campaign_id": CAMPAIGN, "store_product_id": ""},
    {"domain_id": DOMAIN, "campaign_id": CAMPAIGN, "store_product_id": "p" * 65},
    {"domain_id": DOMAIN, "campaign_id": CAMPAIGN, "store_product_id": PRODUCT, "offset": -1},
    {"domain_id": DOMAIN, "campaign_id": CAMPAIGN, "store_product_id": PRODUCT, "limit": 0},
    {"domain_id": DOMAIN, "campaign_id": CAMPAIGN, "store_product_id": PRODUCT, "limit": 101},
])
def test_list_product_ads_rejects_bad_input(monkeypatch, kwargs):
    monkeypatch.setattr(tools.client, "get", lambda *a, **k: pytest.fail("backend called"))
    with pytest.raises(AekoToolInputError):
        tools.aeko_list_product_ads(**kwargs)


def test_list_product_ads_rejects_inconsistent_total(monkeypatch):
    monkeypatch.setattr(tools.client, "get", lambda path, params=None: {"ads": [ad(), ad(str(uuid4()))], "total": 5})
    with pytest.raises(AekoToolError) as exc:
        tools.aeko_list_product_ads(DOMAIN, CAMPAIGN, PRODUCT, limit=1)
    assert code(exc)["code"] == "INVALID_BACKEND_RESPONSE"


def placement(**extra):
    return {"ad_set_item_id": ITEM, "store_product_id": PRODUCT, "product_title": "Cream", "title": "T",
            "body": "B", "created_at": "2026-10-28T00:00:00Z", "why": "pick one",
            "options": [{"campaign_id": CAMPAIGN, "ad_group_id": GROUP, "label": "Camp › Group", "score": 70},
                        {"campaign_id": CAMPAIGN, "ad_group_id": str(uuid4()), "label": "Camp › Two", "score": None}],
            **extra}


def test_list_open_placements(monkeypatch):
    calls = []
    def get(path, params=None):
        calls.append((path, params))
        return {"items": [placement(), placement(ad_set_item_id=str(uuid4()), options=[])]}
    monkeypatch.setattr(tools.client, "get", get)
    result = tools.aeko_list_open_placements(DOMAIN, ACCOUNT)
    assert calls == [(f"{tools.BASE}/placements", {"domain_id": DOMAIN, "ad_account_id": ACCOUNT})]
    assert result.total == 2 and result.items[0].options[0].score == 70
    assert result.items[0].options[1].score is None and result.items[1].options == []


def test_list_open_placements_empty_and_invalid(monkeypatch):
    monkeypatch.setattr(tools.client, "get", lambda path, params=None: {"items": []})
    assert tools.aeko_list_open_placements(DOMAIN).items == []
    with pytest.raises(AekoToolInputError):
        tools.aeko_list_open_placements("bad")
    monkeypatch.setattr(tools.client, "get", lambda path, params=None: {"items": "nope"})
    with pytest.raises(AekoToolError):
        tools.aeko_list_open_placements(DOMAIN)


def test_list_open_placements_shrinks_big_list(monkeypatch):
    items = [placement(ad_set_item_id=str(uuid4()), body="b" * 300, title="t" * 300, why="w" * 500) for _ in range(120)]
    monkeypatch.setattr(tools.client, "get", lambda path, params=None: {"items": items})
    result = tools.aeko_list_open_placements(DOMAIN)
    assert result.output_limited and result.returned_count < 120 and result.total == 120
    assert tools.text_bytes(result) <= tools.MAX_PAGE_CHARS


def test_answer_places_into_group(monkeypatch):
    calls = []
    def post(path, json=None, params=None, headers=None):
        calls.append((path, json, params))
        return {"status": "placed", "ad_set_item_id": ITEM, "campaign_id": CAMPAIGN,
                "ad_group_id": GROUP, "label": "Camp › Group", "ad_id": AD}
    monkeypatch.setattr(tools.client, "post", post)
    result = tools.aeko_answer_open_placement(DOMAIN, ITEM, ad_group_id=GROUP)
    assert calls == [(f"{tools.BASE}/placements/{ITEM}", {"ad_group_id": GROUP}, {"domain_id": DOMAIN})]
    assert result.status == "placed" and result.ad_id == AD


def test_answer_skips(monkeypatch):
    calls = []
    def post(path, json=None, params=None, headers=None):
        calls.append(json)
        return {"status": "skipped", "ad_set_item_id": ITEM}
    monkeypatch.setattr(tools.client, "post", post)
    result = tools.aeko_answer_open_placement(DOMAIN, ITEM, skip=True)
    assert calls == [{"skip": True}] and result.status == "skipped" and result.ad_id is None


@pytest.mark.parametrize("kwargs", [
    {"domain_id": "bad", "ad_set_item_id": ITEM, "skip": True},
    {"domain_id": DOMAIN, "ad_set_item_id": "bad", "skip": True},
    {"domain_id": DOMAIN, "ad_set_item_id": ITEM},
    {"domain_id": DOMAIN, "ad_set_item_id": ITEM, "ad_group_id": GROUP, "skip": True},
    {"domain_id": DOMAIN, "ad_set_item_id": ITEM, "ad_group_id": "bad"},
    {"domain_id": DOMAIN, "ad_set_item_id": ITEM, "skip": "yes"},
])
def test_answer_rejects_bad_input_before_request(monkeypatch, kwargs):
    monkeypatch.setattr(tools.client, "post", lambda *a, **k: pytest.fail("backend called"))
    with pytest.raises(AekoToolInputError) as exc:
        tools.aeko_answer_open_placement(**kwargs)
    assert code(exc)["mutation_state"] == "not_attempted"


@pytest.mark.parametrize("status,request_sent,state", [(409, True, "rejected"), (422, True, "rejected"),
                                                       (500, True, "unknown"), (None, False, "not_attempted"),
                                                       (None, True, "unknown")])
def test_answer_failure_reports_mutation_state(monkeypatch, status, request_sent, state):
    def post(*a, **k):
        raise AekoAPIError("backend text", http_status=status, request_sent=request_sent, code="PLACEMENT_NOT_PENDING" if status == 409 else None)
    monkeypatch.setattr(tools.client, "post", post)
    with pytest.raises(AekoToolError) as exc:
        tools.aeko_answer_open_placement(DOMAIN, ITEM, ad_group_id=GROUP)
    payload = code(exc)
    assert payload["mutation_state"] == state
    if status == 409:
        assert payload["code"] == "PLACEMENT_NOT_PENDING"


@pytest.mark.parametrize("exc,state,err", [
    (httpx.ReadTimeout("t"), "unknown", "WRITE_RESULT_UNKNOWN"),
    (httpx.WriteTimeout("t"), "unknown", "WRITE_RESULT_UNKNOWN"),
    (httpx.ConnectTimeout("t"), "not_attempted", "BACKEND_UNREACHABLE"),
    (httpx.PoolTimeout("t"), "not_attempted", "BACKEND_UNREACHABLE"),
    (httpx.ConnectError("t"), "not_attempted", "BACKEND_UNREACHABLE"),
    (json.JSONDecodeError("bad", "x", 0), "unknown", "WRITE_RESULT_UNKNOWN"),
    (RuntimeError("boom secret"), "unknown", "WRITE_RESULT_UNKNOWN"),
])
def test_answer_transport_failures_are_structured(monkeypatch, exc, state, err):
    def post(*a, **k):
        raise exc
    monkeypatch.setattr(tools.client, "post", post)
    with pytest.raises(AekoToolError) as caught:
        tools.aeko_answer_open_placement(DOMAIN, ITEM, skip=True)
    payload = code(caught)
    assert payload["code"] == err and payload["mutation_state"] == state
    assert "secret" not in str(caught.value)


def test_answer_unexpected_response_is_unknown_state(monkeypatch):
    monkeypatch.setattr(tools.client, "post", lambda *a, **k: {"status": "weird"})
    with pytest.raises(AekoToolError) as exc:
        tools.aeko_answer_open_placement(DOMAIN, ITEM, skip=True)
    assert code(exc)["mutation_state"] == "unknown"
