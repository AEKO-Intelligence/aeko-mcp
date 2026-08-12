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


def test_client_preserves_branchable_http_error_codes():
    for code in (402, 409, 422, 429, 502, 503):
        assert str(code) in client_mod.ERROR_MESSAGES[code]


def test_client_formats_tracked_prompt_quota_detail():
    class _QuotaResp:
        def json(self):
            return {"detail": {"would_add": 6, "remaining": 2, "blocked": True}}

    assert client_mod._extract_detail_message(_QuotaResp()) == (
        "This request would add 6 tracked-prompt variant(s), but only 2 slot(s) remain."
    )


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


# --- Ad-group bid + creative update guardrails ------------------------------------


def test_ad_update_tools_are_registered_as_idempotent_writes():
    registered = {
        tool.name: tool for tool in marketing.mcp._tool_manager.list_tools()
    }
    for name in ("aeko_update_ad_group", "aeko_update_ad_creative"):
        annotations = registered[name].annotations
        assert annotations.readOnlyHint is False
        assert annotations.idempotentHint is True
        assert annotations.destructiveHint is False


def test_ad_group_bid_defaults_to_dry_run_with_full_bidding_object(monkeypatch):
    flag = _no_write(monkeypatch)
    out = marketing.aeko_update_ad_group(
        "ag1",
        "idem",
        max_bid_micros=1_200_000,
        current_max_bid_micros=1_000_000,
        max_bid_ceiling_micros=2_000_000,
    )

    assert "DRY RUN" in out
    assert '"billing_event_type": "impression"' in out
    assert '"max_bid_micros": 1200000' in out
    assert flag["posted"] is False


def test_ad_group_bid_rejects_outside_backend_bounds(monkeypatch):
    flag = _no_write(monkeypatch)

    below = marketing.aeko_update_ad_group(
        "ag1", "idem", max_bid_micros=0, dry_run=False
    )
    above = marketing.aeko_update_ad_group(
        "ag1", "idem", max_bid_micros=100_000_001, dry_run=False
    )

    assert "must be between 1 and 100000000" in below
    assert "must be between 1 and 100000000" in above
    assert flag["posted"] is False


def test_ad_group_real_bid_write_requires_both_caps(monkeypatch):
    flag = _no_write(monkeypatch)
    out = marketing.aeko_update_ad_group(
        "ag1", "idem", max_bid_micros=1_000_000, dry_run=False
    )

    assert "requires BOTH" in out
    assert flag["posted"] is False


def test_ad_group_bid_rejects_ceiling_and_delta(monkeypatch):
    flag = _no_write(monkeypatch)
    ceiling = marketing.aeko_update_ad_group(
        "ag1",
        "idem",
        max_bid_micros=2_000_000,
        dry_run=False,
        current_max_bid_micros=1_000_000,
        max_bid_ceiling_micros=1_500_000,
        max_delta_pct=200,
    )
    delta = marketing.aeko_update_ad_group(
        "ag1",
        "idem",
        max_bid_micros=2_000_000,
        dry_run=False,
        current_max_bid_micros=1_000_000,
        max_bid_ceiling_micros=3_000_000,
        max_delta_pct=25,
    )

    assert "exceeds the ceiling" in ceiling
    assert "exceeds max_delta_pct" in delta
    assert flag["posted"] is False


def test_ad_group_real_bid_write_posts_guarded_payload(monkeypatch):
    calls = []

    def fake_post(path, json=None, headers=None):
        calls.append({"path": path, "json": json, "headers": headers})
        return {"id": "ag1", "bidding": json["bidding_config"]}

    monkeypatch.setattr(marketing.client, "post", fake_post)
    out = marketing.aeko_update_ad_group(
        "ag1",
        "idem-bid",
        max_bid_micros=900_000,
        dry_run=False,
        current_max_bid_micros=1_000_000,
        max_bid_ceiling_micros=1_500_000,
        max_delta_pct=25,
    )

    assert "Ad group updated" in out
    assert calls == [
        {
            "path": "/api/marketing/ad-groups/ag1",
            "json": {
                "bidding_config": {
                    "billing_event_type": "impression",
                    "max_bid_micros": 900_000,
                }
            },
            "headers": {"Idempotency-Key": "idem-bid"},
        }
    ]


def test_ad_group_non_bid_write_skips_bid_caps_but_honors_dry_run(monkeypatch):
    calls = []

    def fake_post(path, json=None, headers=None):
        calls.append({"path": path, "json": json, "headers": headers})
        return {"id": "ag1", **json}

    monkeypatch.setattr(marketing.client, "post", fake_post)
    preview = marketing.aeko_update_ad_group(
        "ag1", "idem-copy", description="New description"
    )
    written = marketing.aeko_update_ad_group(
        "ag1",
        "idem-copy",
        name="New ad group",
        context_hints=[],
        dry_run=False,
    )

    assert "DRY RUN" in preview
    assert "Ad group updated" in written
    assert calls == [
        {
            "path": "/api/marketing/ad-groups/ag1",
            "json": {"name": "New ad group", "context_hints": []},
            "headers": {"Idempotency-Key": "idem-copy"},
        }
    ]


def test_ad_group_update_rejects_empty_or_invalid_fields(monkeypatch):
    flag = _no_write(monkeypatch)

    empty = marketing.aeko_update_ad_group("ag1", "idem")
    short_name = marketing.aeko_update_ad_group("ag1", "idem", name="AG")
    long_description = marketing.aeko_update_ad_group(
        "ag1", "idem", description="x" * 5001
    )

    assert "at least one" in empty
    assert "at least 3 characters" in short_name
    assert "at most 5000" in long_description
    assert flag["posted"] is False


def test_ad_creative_rejects_partial_whole_object_replace(monkeypatch):
    flag = _no_write(monkeypatch)
    out = marketing.aeko_update_ad_creative(
        "ad1", "idem", title="A complete-looking title"
    )

    assert "requires `creative_type`, `title`, and `body`" in out
    assert "Read `aeko_list_ads` first" in out
    assert flag["posted"] is False


def test_chat_card_prevalidates_url_image_and_price(monkeypatch):
    flag = _no_write(monkeypatch)
    base = {
        "ad_id": "ad1",
        "idempotency_key": "idem",
        "creative_type": "chat_card",
        "title": "Chat card title",
        "body": "Chat card body",
    }

    no_target = marketing.aeko_update_ad_creative(**base, image_url="https://img.example/a.png")
    no_image = marketing.aeko_update_ad_creative(**base, target_url="https://example.com/p")
    priced = marketing.aeko_update_ad_creative(
        **base,
        target_url="https://example.com/p",
        image_url="https://img.example/a.png",
        price="$10",
    )
    invalid_url = marketing.aeko_update_ad_creative(
        **base,
        target_url="javascript:alert(1)",
        image_url="https://img.example/a.png",
    )

    assert "requires `target_url`" in no_target
    assert "requires `file_id` or `image_url`" in no_image
    assert "must not include `price`" in priced
    assert "must be an http(s) URL" in invalid_url
    assert flag["posted"] is False


def test_ad_creative_validates_lengths_before_posting(monkeypatch):
    flag = _no_write(monkeypatch)
    out = marketing.aeko_update_ad_creative(
        "ad1",
        "idem",
        creative_type="product_ad_template",
        title="ok",
        body="body",
    )

    assert "between 3 and 50" in out
    assert flag["posted"] is False


def test_ad_creative_posts_complete_replace_with_idempotency_key(monkeypatch):
    calls = []

    def fake_post(path, json=None, headers=None):
        calls.append({"path": path, "json": json, "headers": headers})
        return {"id": "ad1", **json}

    monkeypatch.setattr(marketing.client, "post", fake_post)
    out = marketing.aeko_update_ad_creative(
        "ad1",
        "idem-creative",
        name="Updated ad",
        creative_type="chat_card",
        title="Updated title",
        body="Updated body",
        target_url="https://example.com/product",
        image_url="https://img.example/product.png",
    )

    assert "Ad creative updated" in out
    assert calls == [
        {
            "path": "/api/marketing/ads/ad1",
            "json": {
                "name": "Updated ad",
                "creative": {
                    "type": "chat_card",
                    "title": "Updated title",
                    "body": "Updated body",
                    "target_url": "https://example.com/product",
                    "image_url": "https://img.example/product.png",
                },
            },
            "headers": {"Idempotency-Key": "idem-creative"},
        }
    ]


def test_ad_creative_name_only_update_does_not_blank_creative(monkeypatch):
    calls = []

    def fake_post(path, json=None, headers=None):
        calls.append(json)
        return {"id": "ad1", **json}

    monkeypatch.setattr(marketing.client, "post", fake_post)
    marketing.aeko_update_ad_creative("ad1", "idem", name="Renamed ad")

    assert calls == [{"name": "Renamed ad"}]


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


# --- OpenAI Ads pacing rules -------------------------------------------------------


def _rule_definition():
    return {
        "domain_id": "domain-1",
        "name": "Pause waste",
        "description": "Pause campaigns after a high-spend low-click window.",
        "scope_level": "campaign",
        "scope_filter": {"target": "all", "ids": []},
        "match": "all",
        "conditions": [
            {
                "metric": "spend",
                "operator": "gte",
                "threshold_micros": 50_000_000,
                "window": {"kind": "last_n_hours", "hours": 6},
            }
        ],
        "guards": {
            "min_impressions": 1000,
            "min_clicks": 0,
            "min_spend_micros": 5_000_000,
            "min_elapsed_fraction": 0.05,
            "min_hours_observed": 1,
        },
        "action": "pause",
        "cooldown_minutes": 120,
        "max_actions_per_day": 20,
        "max_entities_per_run": 10,
    }


def _call_create_or_validate(tool):
    definition = _rule_definition()
    return tool(
        definition["domain_id"],
        definition["name"],
        definition["scope_level"],
        definition["scope_filter"],
        definition["match"],
        definition["conditions"],
        definition["action"],
        definition["guards"],
        definition["cooldown_minutes"],
        definition["max_actions_per_day"],
        definition["max_entities_per_run"],
        definition["description"],
    )


def test_ad_rule_read_tools_call_exact_routes_and_queries(monkeypatch):
    calls = []

    def fake_get(path, params=None):
        calls.append({"path": path, "params": params})
        return [] if path.endswith(("rules", "rule-executions", "rule-runs")) else {"ok": True}

    monkeypatch.setattr(marketing.client, "get", fake_get)

    marketing.aeko_list_ad_rules("domain-1")
    marketing.aeko_list_ad_rules("domain-1", include_disabled=True)
    marketing.aeko_get_ad_rule("rule-1")
    marketing.aeko_get_ad_rule_capabilities("domain-1")
    marketing.aeko_list_ad_rule_executions(
        "domain-1",
        rule_id="rule-1",
        status="succeeded",
        limit=500,
    )
    marketing.aeko_list_ad_rule_runs("domain-1")

    assert calls == [
        {
            "path": "/api/marketing/rules",
            "params": {"domain_id": "domain-1", "include_disabled": False},
        },
        {
            "path": "/api/marketing/rules",
            "params": {"domain_id": "domain-1", "include_disabled": True},
        },
        {"path": "/api/marketing/rules/rule-1", "params": None},
        {
            "path": "/api/marketing/rules/capabilities",
            "params": {"domain_id": "domain-1"},
        },
        {
            "path": "/api/marketing/rule-executions",
            "params": {
                "domain_id": "domain-1",
                "limit": 200,
                "rule_id": "rule-1",
                "status": "succeeded",
            },
        },
        {
            "path": "/api/marketing/rule-runs",
            "params": {"domain_id": "domain-1", "limit": 20},
        },
    ]


def test_create_ad_rule_posts_complete_disabled_mcp_payload(monkeypatch):
    calls = []

    def fake_post(path, json=None, params=None, headers=None):
        calls.append(
            {"path": path, "json": json, "params": params, "headers": headers}
        )
        return {"id": "rule-1", "enabled": False}

    monkeypatch.setattr(marketing.client, "post", fake_post)
    out = _call_create_or_validate(marketing.aeko_create_ad_rule)

    assert "created (disabled)" in out
    expected = _rule_definition()
    expected.update({"enabled": False, "created_by": "mcp"})
    assert calls == [
        {
            "path": "/api/marketing/rules",
            "json": expected,
            "params": None,
            "headers": None,
        }
    ]


def test_validate_ad_rule_posts_same_unsaved_definition_without_insights(monkeypatch):
    calls = []

    def fake_post(path, json=None, params=None, headers=None):
        calls.append({"path": path, "json": json})
        return {"valid": True, "normalized": json, "warnings": []}

    monkeypatch.setattr(marketing.client, "post", fake_post)
    out = _call_create_or_validate(marketing.aeko_validate_ad_rule)

    assert '"valid": true' in out
    expected = _rule_definition()
    expected.update({"enabled": False, "created_by": "mcp"})
    assert calls == [
        {"path": "/api/marketing/rules/validate", "json": expected}
    ]


def test_update_and_delete_ad_rule_call_exact_routes(monkeypatch):
    patches = []
    deletes = []

    def fake_patch(path, json=None, headers=None):
        patches.append({"path": path, "json": json, "headers": headers})
        return {"id": "rule-1", **json}

    def fake_delete(path, params=None):
        deletes.append({"path": path, "params": params})
        return {"id": "rule-1", "deleted_at": "2026-07-24T00:00:00Z"}

    monkeypatch.setattr(marketing.client, "patch", fake_patch)
    monkeypatch.setattr(marketing.client, "delete", fake_delete)

    marketing.aeko_update_ad_rule(
        "rule-1",
        name="New name",
        max_entities_per_run=25,
        description="",
    )
    marketing.aeko_delete_ad_rule("rule-1")

    assert patches == [
        {
            "path": "/api/marketing/rules/rule-1",
            "json": {
                "name": "New name",
                "description": "",
                "max_entities_per_run": 25,
            },
            "headers": None,
        }
    ]
    assert deletes == [
        {"path": "/api/marketing/rules/rule-1", "params": None}
    ]


def test_set_ad_rule_enabled_uses_enable_query_and_disable_route(monkeypatch):
    calls = []

    def fake_post(path, json=None, params=None, headers=None):
        calls.append(
            {"path": path, "json": json, "params": params, "headers": headers}
        )
        return {"id": "rule-1", "enabled": path.endswith("/enable")}

    monkeypatch.setattr(marketing.client, "post", fake_post)

    enabled = marketing.aeko_set_ad_rule_enabled(
        "rule-1",
        True,
        acknowledge_broad_match=True,
    )
    disabled = marketing.aeko_set_ad_rule_enabled("rule-1", False)

    assert "Ad rule enabled" in enabled
    assert "Ad rule disabled" in disabled
    assert calls == [
        {
            "path": "/api/marketing/rules/rule-1/enable",
            "json": None,
            "params": {"acknowledge_broad_match": True},
            "headers": None,
        },
        {
            "path": "/api/marketing/rules/rule-1/disable",
            "json": None,
            "params": None,
            "headers": None,
        },
    ]


def test_set_ad_rule_enabled_surfaces_broad_match_ack_recovery(monkeypatch):
    def fake_post(path, json=None, params=None, headers=None):
        raise RuntimeError(
            "{'code': 'MARKETING_RULE_BROAD_MATCH_ACK_REQUIRED', "
            "'matched_count': 6, 'target_count': 10}"
        )

    monkeypatch.setattr(marketing.client, "post", fake_post)
    out = marketing.aeko_set_ad_rule_enabled("rule-1", True)

    assert "Broad-match acknowledgement required" in out
    assert "acknowledge_broad_match=True" in out
    assert "matched_count" in out and "target_count" in out


def test_preview_ad_rule_selects_saved_or_unsaved_route(monkeypatch):
    calls = []

    def fake_post(path, json=None, params=None, headers=None):
        calls.append({"path": path, "json": json})
        return {
            "run_id": "run-1",
            "dry_run": True,
            "target_count": 1,
            "matched_count": 0,
            "matched_entities": [],
        }

    monkeypatch.setattr(marketing.client, "post", fake_post)
    saved = marketing.aeko_preview_ad_rule(rule_id="rule-1")
    unsaved_rule = _rule_definition()
    unsaved = marketing.aeko_preview_ad_rule(rule=unsaved_rule)
    rejected_both = marketing.aeko_preview_ad_rule(
        rule_id="rule-1",
        rule=unsaved_rule,
    )
    rejected_neither = marketing.aeko_preview_ad_rule()

    assert "dry run" in saved and "dry run" in unsaved
    assert "exactly one" in rejected_both and "exactly one" in rejected_neither
    assert calls == [
        {"path": "/api/marketing/rules/rule-1/preview", "json": None},
        {"path": "/api/marketing/rules/preview", "json": unsaved_rule},
    ]


def test_set_ad_automation_enabled_posts_to_narrow_automation_endpoint(monkeypatch):
    """The kill switch must NOT go through PATCH /ad-account.

    That endpoint also writes the SFTP password and conversions API token, so it is
    guarded by require_user_context (CIAM/Shopify only) and returned 401 for every MCP
    token — leaving an agent able to arm automation but never stop it. The switch now
    has its own credential-free dual-auth endpoint.
    """
    calls = []

    def fake_post(path, json=None, params=None, headers=None):
        calls.append({"path": path, "json": json, "headers": headers})
        return {"domain_id": json["domain_id"], "rules_enabled": json["enabled"]}

    def fail_patch(*args, **kwargs):  # pragma: no cover - must never be reached
        raise AssertionError(
            "aeko_set_ad_automation_enabled used PATCH; that route is CIAM-only "
            "and writes ad-account credentials."
        )

    monkeypatch.setattr(marketing.client, "post", fake_post)
    monkeypatch.setattr(marketing.client, "patch", fail_patch)
    out = marketing.aeko_set_ad_automation_enabled("domain-1", False)

    assert "Ad automation disabled" in out
    assert calls == [
        {
            "path": "/api/marketing/ad-account/automation",
            "json": {"domain_id": "domain-1", "enabled": False},
            "headers": None,
        }
    ]


def test_set_ad_automation_enabled_can_re_enable(monkeypatch):
    def fake_post(path, json=None, params=None, headers=None):
        return {"domain_id": json["domain_id"], "rules_enabled": json["enabled"]}

    monkeypatch.setattr(marketing.client, "post", fake_post)
    assert "Ad automation enabled" in marketing.aeko_set_ad_automation_enabled("d1", True)


def test_ad_rule_tools_are_registered_with_expected_annotations():
    registered = {
        tool.name: tool for tool in marketing.mcp._tool_manager.list_tools()
    }
    read_only = {
        "aeko_list_ad_rules",
        "aeko_get_ad_rule",
        "aeko_get_ad_rule_capabilities",
        "aeko_list_ad_rule_executions",
        "aeko_list_ad_rule_runs",
    }
    writes = {
        "aeko_create_ad_rule",
        "aeko_update_ad_rule",
        "aeko_delete_ad_rule",
        "aeko_set_ad_rule_enabled",
        "aeko_validate_ad_rule",
        "aeko_preview_ad_rule",
        "aeko_set_ad_automation_enabled",
    }

    assert read_only | writes <= set(registered)
    for name in read_only:
        assert registered[name].annotations.readOnlyHint is True
        assert registered[name].annotations.idempotentHint is True
    for name in writes:
        assert registered[name].annotations.readOnlyHint is False
    for name in {
        "aeko_delete_ad_rule",
        "aeko_set_ad_rule_enabled",
        "aeko_set_ad_automation_enabled",
    }:
        assert registered[name].annotations.destructiveHint is True
