"""aeko-mcp: F0 idempotency-header forwarding + marketing tool guardrails (no network)."""
from aeko_mcp import client as client_mod
from aeko_mcp.tools import marketing


# --- F0: client forwards a custom Idempotency-Key header ---------------------------


class _FakeResp:
    content = b"{}"

    def raise_for_status(self):
        return None

    def json(self):
        return {}


class _FakeHttpx:
    def __init__(self):
        self.calls = []

    def post(self, path, json=None, params=None, headers=None):
        self.calls.append({"path": path, "json": json, "params": params, "headers": headers})
        return _FakeResp()


def test_client_post_forwards_idempotency_key_over_auth():
    c = client_mod.AekoClient.__new__(client_mod.AekoClient)
    c._client = _FakeHttpx()
    ctx = c.set_request_auth_token("tok123")
    try:
        c.post("/x", json={"a": 1}, headers={"Idempotency-Key": "key-1"})
    finally:
        c.reset_request_auth_token(ctx)
    hdr = c._client.calls[0]["headers"]
    assert hdr["Idempotency-Key"] == "key-1"
    assert hdr["Authorization"] == "Bearer tok123"  # auth preserved alongside the extra header


# --- Budget guardrails live in the tool, not just skill prose ----------------------


def _no_write(monkeypatch):
    flag = {"posted": False}
    monkeypatch.setattr(marketing.client, "post", lambda *a, **k: flag.__setitem__("posted", True) or {})
    return flag


def test_budget_dry_run_default_writes_nothing(monkeypatch):
    flag = _no_write(monkeypatch)
    out = marketing.aeko_update_campaign_budget(
        "c1", 5_000_000, "idem", current_budget_micros=4_000_000, max_delta_pct=50
    )
    assert "DRY RUN" in out and flag["posted"] is False


def test_budget_rejects_below_floor(monkeypatch):
    flag = _no_write(monkeypatch)
    out = marketing.aeko_update_campaign_budget("c1", 500_000, "idem", dry_run=False)
    assert "below the minimum" in out and flag["posted"] is False


def test_budget_real_write_requires_both_caps(monkeypatch):
    # HARD guard: a real write with a cap omitted is rejected outright (can't bypass delta/ceiling).
    flag = _no_write(monkeypatch)
    out = marketing.aeko_update_campaign_budget("c1", 2_000_000, "idem", dry_run=False)
    assert "requires BOTH" in out and flag["posted"] is False


def test_budget_rejects_over_ceiling(monkeypatch):
    flag = _no_write(monkeypatch)
    out = marketing.aeko_update_campaign_budget(
        "c1", 9_000_000, "idem", dry_run=False, current_budget_micros=4_000_000, max_budget_micros=5_000_000
    )
    assert "ceiling" in out and flag["posted"] is False


def test_budget_rejects_over_delta(monkeypatch):
    flag = _no_write(monkeypatch)
    out = marketing.aeko_update_campaign_budget(
        "c1", 10_000_000, "idem", dry_run=False,
        current_budget_micros=1_000_000, max_budget_micros=100_000_000, max_delta_pct=25,
    )
    assert "exceeds max_delta_pct" in out and flag["posted"] is False


# --- Compose + pause validation ---------------------------------------------------


def test_create_ad_group_requires_exactly_one_placement():
    out = marketing.aeko_create_ad_group_from_context(
        "d1", "Ad Group A", ["hint"], [{"store_product_id": "p1"}], "idem",
        campaign_id="c1", new_campaign_name="Xyz",  # both -> invalid
    )
    assert "exactly one placement" in out


def test_create_ad_group_rejects_short_name():
    out = marketing.aeko_create_ad_group_from_context(
        "d1", "AG", ["hint"], [{"store_product_id": "p1"}], "idem", campaign_id="c1",
    )
    assert "at least 3 characters" in out


def test_create_ad_group_rejects_too_many_ads():
    ads = [{"store_product_id": f"p{i}"} for i in range(101)]
    out = marketing.aeko_create_ad_group_from_context(
        "d1", "Ad Group A", ["hint"], ads, "idem", campaign_id="c1",
    )
    assert "at most 100 ads" in out


def test_inject_reviews_chunks_over_200(monkeypatch):
    calls = {"n": 0, "sizes": []}

    def fake_post(path, json=None, headers=None):
        n = len(json["reviews"])
        calls["n"] += 1
        calls["sizes"].append(n)
        return {"integration_id": "i1", "requested": n, "inserted": n, "updated": 0,
                "skipped_unmatched": 0, "unmatched_refs": [], "classification_enqueued": True}

    monkeypatch.setattr(marketing.client, "post", fake_post)
    reviews = [{"external_review_id": f"r{i}", "external_product_ref": "sku-1", "body": "x"} for i in range(450)]
    out = marketing.aeko_inject_reviews("d1", reviews)
    assert calls["n"] == 3 and calls["sizes"] == [200, 200, 50]
    assert '"inserted": 450' in out  # aggregated across batches


def test_set_state_rejects_unknown_actions():
    assert "Allowed actions" in marketing.aeko_set_ad_state("a1", "delete", "idem")
    assert "Allowed actions" in marketing.aeko_set_campaign_state("c1", "delete", "idem")


def test_set_campaign_state_can_activate_and_archive_with_confirm(monkeypatch):
    calls = []

    def fake_post(path, json=None, headers=None):
        calls.append({"path": path, "json": json, "headers": headers})
        return {"id": "c1", "status": path.rsplit("/", 1)[-1]}

    monkeypatch.setattr(marketing.client, "post", fake_post)
    active_denied = marketing.aeko_set_campaign_state("c1", "active", "idem-active")
    active = marketing.aeko_set_campaign_state("c1", "active", "idem-active", confirm_active=True)
    denied = marketing.aeko_set_campaign_state("c1", "archive", "idem-archive")
    archived = marketing.aeko_set_campaign_state("c1", "archive", "idem-archive", confirm_archive=True)

    assert "confirm_active=True" in active_denied
    assert "Campaign active" in active
    assert "confirm_archive=True" in denied
    assert "Campaign archive" in archived
    assert calls == [
        {"path": "/api/marketing/campaigns/c1/activate", "json": None, "headers": {"Idempotency-Key": "idem-active"}},
        {"path": "/api/marketing/campaigns/c1/archive", "json": None, "headers": {"Idempotency-Key": "idem-archive"}},
    ]


def test_set_ad_and_ad_group_state(monkeypatch):
    calls = []

    def fake_post(path, json=None, headers=None):
        calls.append({"path": path, "json": json, "headers": headers})
        return {"id": path.split("/")[-2], "status": path.rsplit("/", 1)[-1]}

    monkeypatch.setattr(marketing.client, "post", fake_post)
    ad_denied = marketing.aeko_set_ad_state("ad1", "active", "idem-ad")
    ad = marketing.aeko_set_ad_state("ad1", "active", "idem-ad", confirm_active=True)
    ad_group = marketing.aeko_set_ad_group_state("ag1", "pause", "idem-ag")

    assert "confirm_active=True" in ad_denied
    assert "Ad active" in ad
    assert "Ad group pause" in ad_group
    assert calls == [
        {"path": "/api/marketing/ads/ad1/activate", "json": None, "headers": {"Idempotency-Key": "idem-ad"}},
        {"path": "/api/marketing/ad-groups/ag1/pause", "json": None, "headers": {"Idempotency-Key": "idem-ag"}},
    ]


def test_marketing_setup_tools_call_expected_routes(monkeypatch):
    gets = []
    posts = []

    def fake_get(path, params=None):
        gets.append({"path": path, "params": params})
        return {"path": path, "ready": True}

    def fake_post(path, json=None, params=None, headers=None):
        posts.append({"path": path, "json": json, "params": params, "headers": headers})
        return {"status": "queued", "ad_account_id": "acct1"}

    monkeypatch.setattr(marketing.client, "get", fake_get)
    monkeypatch.setattr(marketing.client, "post", fake_post)

    account = marketing.aeko_get_ad_account_status("domain-1")
    feed = marketing.aeko_get_feed_status("domain-1")
    sync = marketing.aeko_sync_feed("domain-1", "idem-feed")

    assert "Ad account status" in account
    assert "Feed status" in feed
    assert "Feed sync queued" in sync
    assert gets == [
        {"path": "/api/marketing/ad-account", "params": {"domain_id": "domain-1"}},
        {"path": "/api/marketing/feed", "params": {"domain_id": "domain-1"}},
    ]
    assert posts == [
        {
            "path": "/api/marketing/feed/sync",
            "json": None,
            "params": {"domain_id": "domain-1"},
            "headers": {"Idempotency-Key": "idem-feed"},
        }
    ]
