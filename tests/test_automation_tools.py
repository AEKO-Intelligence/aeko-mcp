import json
from uuid import uuid4

import pytest

from aeko_mcp.server import mcp
from aeko_mcp.tools import automations as tools

DOMAIN = str(uuid4())
INSTANCE = str(uuid4())
RUN = str(uuid4())
ACCOUNT = str(uuid4())
GROUP = str(uuid4())


def test_tools_registered_with_explicit_read_and_mutation_annotations():
    registered = {tool.name: tool for tool in mcp._tool_manager.list_tools()}
    assert set((
        "aeko_list_automations", "aeko_resolve_automation_contract",
        "aeko_create_automation_instance", "aeko_run_automation_instance",
        "aeko_get_automation_run",
    )) <= set(registered)
    assert registered["aeko_list_automations"].annotations.readOnlyHint is True
    assert registered["aeko_resolve_automation_contract"].annotations.readOnlyHint is True
    assert registered["aeko_create_automation_instance"].annotations.readOnlyHint is False
    assert registered["aeko_run_automation_instance"].annotations.readOnlyHint is False


def test_discovery_filters_to_supported_definitions_and_instances(monkeypatch):
    monkeypatch.setattr(tools.client, "get", lambda *a, **kw: {
        "definitions": [{"key": "ad_performance_shortlist", "stages": [{"stage_type": "source", "name": "Shortlist", "handler": "ad_performance_shortlist", "config": {"prompt": "private"}}]}, {"key": "brief_based_ads"}],
        "instances": [{"id": INSTANCE, "automation_key": "review_context_workflow", "brief_text": "secret"},
                     {"id": "x", "automation_key": "brief_based_ads"}],
    })
    result = json.loads(tools.aeko_list_automations(DOMAIN))
    assert [row["key"] for row in result["templates"]] == ["ad_performance_shortlist"]
    assert "private" not in json.dumps(result)
    assert len(result["instances"]) == 1
    assert "brief_text" not in json.dumps(result)


def test_resolve_contract_is_transient_manual_and_validates_params(monkeypatch):
    calls = []
    def post(*args, **kwargs):
        calls.append((args, kwargs))
        return {"ready": True, "reason_code": None, "job_contract": {"x": 1}, "credits_remaining": 9}
    monkeypatch.setattr(tools.client, "post", post)
    params = {"ad_account_id": ACCOUNT, "ad_group_id": GROUP, "target_kpi": "ctr"}
    result = json.loads(tools.aeko_resolve_automation_contract(DOMAIN, "ad_performance_shortlist", params))
    assert result["ready"] is True
    args, kwargs = calls[0]
    assert args[0] == "/api/automations/ad_performance_shortlist/resolve-contract"
    assert kwargs["params"] == {"domain_id": DOMAIN}
    assert kwargs["json"]["cadence"] == "manual"
    assert kwargs["json"]["model_class"] == "basic"
    assert "destination" not in kwargs["json"]
    with pytest.raises(tools.AekoToolInputError):
        tools.aeko_resolve_automation_contract(DOMAIN, "ad_performance_shortlist", {**params, "target_kpi": "roas"})


def test_create_forces_disabled_manual_hold_ads_and_never_runs(monkeypatch):
    calls = []
    monkeypatch.setattr(tools.client, "post", lambda *a, **kw: calls.append((a, kw)) or {
        "id": INSTANCE, "automation_key": "review_based_ads", "name": "Hold", "enabled": False,
        "cadence": "manual", "params": {}, "destination": {"policy": "hold"}, "model_class": "basic",
    })
    params = {"ad_account_id": ACCOUNT, "target_language": "ko", "target_market": "KR",
              "ad_group_name": "Review context", "max_bid_micros": 1000}
    result = json.loads(tools.aeko_create_automation_instance(DOMAIN, "review_based_ads", "Hold", params))
    assert result["destination"] == {"policy": "hold"}
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[0] == "/api/automations/review_based_ads/instances"
    assert kwargs["json"]["cadence"] == "manual"
    assert kwargs["json"]["destination"] == {"policy": "hold"}


def test_run_uses_backend_guarded_endpoint_and_exact_idempotency_key(monkeypatch):
    calls = []
    monkeypatch.setattr(tools.client, "post", lambda *a, **kw: calls.append((a, kw)) or {
        "run_id": RUN, "poll_url": f"/api/automations/runs/{RUN}?domain_id={DOMAIN}", "mode": "live",
    })
    result = json.loads(tools.aeko_run_automation_instance(DOMAIN, INSTANCE, "retry-token-123"))
    assert result["run_id"] == RUN
    args, kwargs = calls[0]
    assert args[0] == f"/api/automations/instances/{INSTANCE}/run-starter"
    assert kwargs["params"] == {"domain_id": DOMAIN}
    assert kwargs["headers"] == {"Idempotency-Key": "retry-token-123"}
    with pytest.raises(tools.AekoToolInputError):
        tools.aeko_run_automation_instance(DOMAIN, INSTANCE, " padded ")


def test_run_result_keeps_safe_shortlist_details_and_drops_snapshot_secrets(monkeypatch):
    details = {"target_kpi": "ctr", "currency": "KRW", "date_from": "2026-09-01",
               "exclusions": [{"ad_id": "a", "name": "Ad", "reason": "STALE_REPORTING", "body": "private"}],
               "secret": "must not leak"}
    payload = {
        "id": RUN, "instance_id": INSTANCE, "automation_key": "ad_performance_shortlist",
        "status": "ok", "items_total": 1, "items_by_state": {"selected": 1},
        "stages": [{"index": 0, "stage_type": "source", "details": details}],
        "items": [{"id": "i", "item_type": "ad", "snapshot": {"display_label": "Good", "review_body": "secret"}}],
        "snapshot": {"credential": "secret"}, "output_refs": [], "removed": [],
    }
    monkeypatch.setattr(tools.client, "get", lambda *a, **kw: payload)
    text = tools.aeko_get_automation_run(DOMAIN, RUN)
    result = json.loads(text)
    assert result["stages"][0]["details"]["currency"] == "KRW"
    assert result["stages"][0]["details"]["exclusions"][0]["reason"] == "STALE_REPORTING"
    assert "secret" not in text and "review_body" not in text


@pytest.mark.parametrize("strategy", ["context", "conversational", "auto"])
def test_ad_strategy_is_preserved_in_resolve_and_create(monkeypatch, strategy):
    calls = []
    monkeypatch.setattr(tools.client, "post", lambda *args, **kwargs: calls.append(kwargs) or {
        "ready": True, "id": INSTANCE, "automation_key": "review_based_ads",
    })
    params = {
        "ad_account_id": ACCOUNT, "target_language": "ko", "target_market": "KR",
        "ad_group_name": "Review context", "max_bid_micros": 500000,
        "creative_strategy": strategy,
    }
    tools.aeko_resolve_automation_contract(DOMAIN, "review_based_ads", params)
    tools.aeko_create_automation_instance(DOMAIN, "review_based_ads", "Drafts", params)
    assert all(call["json"]["params"]["creative_strategy"] == strategy for call in calls)
    assert all(call["json"]["destination"] == {"policy": "hold"} for call in calls)


def test_response_informed_requires_plugin_evidence_flow_not_context_template(monkeypatch):
    calls = []
    monkeypatch.setattr(tools.client, "post", lambda *args, **kwargs: calls.append(kwargs))
    params = {
        "ad_account_id": ACCOUNT, "target_language": "ko", "target_market": "KR",
        "ad_group_name": "Review context", "max_bid_micros": 500000,
        "creative_strategy": "response_informed",
    }
    with pytest.raises(tools.AekoToolInputError):
        tools.aeko_create_automation_instance(DOMAIN, "review_based_ads", "Drafts", params)
    assert not calls


def test_run_result_exposes_bounded_strategy_provenance_without_document_bodies(monkeypatch):
    payload = {
        "automation_key": "review_based_ads", "status": "ok", "output_refs": [], "removed": [],
        "items": [{"id": "item-1", "creative_strategy": {
            "key": "conversational", "reason": "Natural phrasing fits this supplied customer situation.",
            "skill_ref": {"document_id": "s1", "version_id": "sv1", "version": 3, "key": "conversational", "text": "private skill body"},
            "eval_ref": {"document_id": "e1", "version_id": "ev1", "version": 2, "key": "conversational", "text": "private eval body"},
        }}],
    }
    monkeypatch.setattr(tools.client, "get", lambda *args, **kwargs: payload)
    rendered = tools.aeko_get_automation_run(DOMAIN, RUN)
    result = json.loads(rendered)["items"][0]["creative_strategy"]
    assert result["key"] == "conversational"
    assert result["skill_ref"]["version_id"] == "sv1"
    assert result["eval_ref"]["version_id"] == "ev1"
    assert "private" not in rendered
