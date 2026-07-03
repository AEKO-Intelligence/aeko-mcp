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

    def post(self, path, json=None, headers=None):
        self.calls.append({"path": path, "json": json, "headers": headers})
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


def test_set_state_pause_only():
    assert "pause" in marketing.aeko_set_ad_state("a1", "archive", "idem")
    assert "pause" in marketing.aeko_set_campaign_state("c1", "activate", "idem")
