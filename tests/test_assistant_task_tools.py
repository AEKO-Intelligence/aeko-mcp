"""Offline tests for the task fence and persisted-output adapters."""

from uuid import uuid4

import pytest

from aeko_mcp.server import mcp
from aeko_mcp.tools import assistant_tasks
from aeko_mcp.tools._structured import AekoToolInputError


ITEM = "itm_saved_task"
CLAIM = str(uuid4())
CONTEXT = str(uuid4())
SUGGESTION = str(uuid4())
EVIDENCE = str(uuid4())


def test_new_tools_are_registered_with_read_write_annotations():
    tools = {tool.name: tool for tool in mcp._tool_manager.list_tools()}
    reads = {"aeko_list_action_outputs", "aeko_get_action_output", "aeko_get_ad_copy_formats"}
    writes = {"aeko_create_assistant_task", "aeko_track_task_suggestions", "aeko_save_action_output", "aeko_create_ad_copy_format"}
    assert reads | writes <= tools.keys()
    assert all(tools[name].annotations.readOnlyHint for name in reads)
    assert all(not tools[name].annotations.readOnlyHint for name in writes)


def test_selected_batch_preserves_exact_task_claim_rows_and_variants(monkeypatch):
    calls = []
    monkeypatch.setattr(assistant_tasks.client, "post", lambda path, *, json: calls.append((path, json)) or {"requested": 1, "tracked": 1, "results": []})
    row = {"context_id": CONTEXT, "suggested_prompt_id": SUGGESTION, "prompt": "Exact question?"}
    assistant_tasks.aeko_track_task_suggestions(ITEM, CLAIM, [row], ["openai"], ["US"])
    assert calls == [(f"/api/action-items/{ITEM}/track-suggestions", {
        "claim_id": CLAIM, "rows": [row], "ai_platforms": ["openai"], "countries": ["US"],
    })]


def test_selected_batch_accepts_saved_null_prompt(monkeypatch):
    calls = []
    monkeypatch.setattr(assistant_tasks.client, "post", lambda path, *, json: calls.append(json) or {"requested": 1})
    row = {"context_id": CONTEXT, "suggested_prompt_id": SUGGESTION, "prompt": None}
    assistant_tasks.aeko_track_task_suggestions(ITEM, CLAIM, [row], ["openai"], ["US"])
    assert calls[0]["rows"] == [row]


def test_invalid_selected_batch_never_reaches_backend(monkeypatch):
    monkeypatch.setattr(assistant_tasks.client, "post", lambda *args, **kwargs: pytest.fail("backend reached"))
    with pytest.raises(AekoToolInputError):
        assistant_tasks.aeko_track_task_suggestions(ITEM, CLAIM, [{"context_id": CONTEXT, "suggested_prompt_id": SUGGESTION, "other": "x"}], ["openai"], ["US"])
    with pytest.raises(AekoToolInputError):
        assistant_tasks.aeko_track_task_suggestions(ITEM, CLAIM, [], ["openai"], ["US"])
    with pytest.raises(AekoToolInputError):
        assistant_tasks.aeko_track_task_suggestions(ITEM, CLAIM, [{"context_id": CONTEXT, "suggested_prompt_id": SUGGESTION}], [], ["US"])


def test_report_save_preserves_fence_and_cannot_forge_tracking_receipt(monkeypatch):
    calls = []
    monkeypatch.setattr(assistant_tasks.client, "post", lambda path, *, json: calls.append((path, json)) or {"id": str(uuid4())})
    assistant_tasks.aeko_save_action_output(ITEM, CLAIM, "report-key", "report_markdown", "assistant-output-v1", "# Comparison [evidence:" + EVIDENCE + "]", evidence_ids=[EVIDENCE])
    assert calls[0][0] == f"/api/action-items/{ITEM}/outputs"
    assert calls[0][1]["claim_id"] == CLAIM
    assert calls[0][1]["evidence_ids"] == [EVIDENCE]
    with pytest.raises(AekoToolInputError):
        assistant_tasks.aeko_save_action_output(ITEM, CLAIM, "fake", "tracking_receipt", "v1", "success")
    assert len(calls) == 1


def test_format_proposal_is_structured_and_never_creates_a_format(monkeypatch):
    calls = []
    monkeypatch.setattr(assistant_tasks.client, "post", lambda path, *, json: calls.append((path, json)) or {"id": str(uuid4())})
    definition = {"name": "Question-led", "title_instructions": "State the question", "description_instructions": "Answer clearly", "examples": [], "language_codes": ["en"]}
    assistant_tasks.aeko_save_action_output(ITEM, CLAIM, "proposal-key", "ad_copy_format_proposal", "assistant-output-v1", data=definition)
    assert calls == [(f"/api/action-items/{ITEM}/outputs", {
        "claim_id": CLAIM, "idempotency_key": "proposal-key", "kind": "ad_copy_format_proposal",
        "schema_version": "assistant-output-v1", "markdown": None, "data": definition, "evidence_ids": [],
    })]
    with pytest.raises(AekoToolInputError):
        assistant_tasks.aeko_save_action_output(ITEM, CLAIM, "bad", "ad_copy_format_proposal", "assistant-output-v1", markdown="# Activated", data=definition)
    assert len(calls) == 1


def test_context_group_proposal_uses_claimed_output_only(monkeypatch):
    calls = []
    monkeypatch.setattr(assistant_tasks.client, "post", lambda path, *, json: calls.append((path, json)) or {"id": str(uuid4())})
    groups = {"groups": [{"name": "Gift moments", "rationale": "Shared occasion", "context_ids": [CONTEXT]}]}
    assistant_tasks.aeko_save_action_output(ITEM, CLAIM, "groups-key", "context_group_proposal", "assistant-output-v1", data=groups)
    assert calls == [(f"/api/action-items/{ITEM}/outputs", {
        "claim_id": CLAIM, "idempotency_key": "groups-key", "kind": "context_group_proposal",
        "schema_version": "assistant-output-v1", "markdown": None, "data": groups, "evidence_ids": [],
    })]
    with pytest.raises(AekoToolInputError):
        assistant_tasks.aeko_save_action_output(ITEM, CLAIM, "bad-groups", "context_group_proposal", "assistant-output-v1", markdown="Created campaign", data=groups)
    assert len(calls) == 1


def test_rule_proposal_preserves_frozen_evidence_and_typed_change_fence(monkeypatch):
    calls = []
    monkeypatch.setattr(assistant_tasks.client, "post", lambda path, *, json: calls.append((path, json)) or {"id": str(uuid4())})
    rule = str(uuid4())
    proposal = {"rule_id": rule, "expected_version": 3, "rationale": "Use the observed daily range", "changes": {"description": "Review this threshold"}}
    assistant_tasks.aeko_save_action_output(ITEM, CLAIM, "rule-key", "ad_rule_proposal", "assistant-output-v1", data=proposal, evidence_ids=[EVIDENCE])
    assert calls == [(f"/api/action-items/{ITEM}/outputs", {
        "claim_id": CLAIM, "idempotency_key": "rule-key", "kind": "ad_rule_proposal",
        "schema_version": "assistant-output-v1", "markdown": None, "data": proposal, "evidence_ids": [EVIDENCE],
    })]
    for invalid in (
        {**proposal, "changes": {"enabled": True}},
        {**proposal, "expected_version": 0},
        {**proposal, "rule_id": "other"},
        {**proposal, "changes": {"conditions": None}},
    ):
        with pytest.raises(AekoToolInputError):
            assistant_tasks.aeko_save_action_output(ITEM, CLAIM, "bad-rule", "ad_rule_proposal", "assistant-output-v1", data=invalid, evidence_ids=[EVIDENCE])
    with pytest.raises(AekoToolInputError):
        assistant_tasks.aeko_save_action_output(ITEM, CLAIM, "missing-evidence", "ad_rule_proposal", "assistant-output-v1", data=proposal)
    with pytest.raises(AekoToolInputError):
        assistant_tasks.aeko_save_action_output(ITEM, CLAIM, "fake-report", "report_markdown", "assistant-output-v1", markdown="# Report", data={"hidden": "claim"})
    assert len(calls) == 1


def test_output_reads_are_task_scoped(monkeypatch):
    calls = []
    monkeypatch.setattr(assistant_tasks.client, "get", lambda path: calls.append(path) or {"outputs": []})
    assistant_tasks.aeko_list_action_outputs(ITEM)
    assistant_tasks.aeko_get_action_output(ITEM, EVIDENCE)
    assert calls == [f"/api/action-items/{ITEM}/outputs", f"/api/action-items/{ITEM}/outputs/{EVIDENCE}"]
    with pytest.raises(AekoToolInputError):
        assistant_tasks.aeko_get_action_output("itm_unsafe/path", EVIDENCE)


def test_task_creation_does_not_accept_arbitrary_action_id(monkeypatch):
    monkeypatch.setattr(assistant_tasks.client, "post", lambda *args, **kwargs: pytest.fail("backend reached"))
    with pytest.raises(AekoToolInputError):
        assistant_tasks.aeko_create_assistant_task("ads.activate.v1", {"domain_id": str(uuid4())}, "key")


@pytest.mark.parametrize("action_id,page_id", [
    ("tracking.selected_questions_report.v1", "tracking"),
    ("tracking.platform_responses_report.v1", "tracking"),
    ("competitors.question_gaps_report.v1", "competitors"),
    ("competitors.source_patterns_report.v1", "competitors"),
    ("visibility.overview_report.v1", "overview"),
    ("markets.comparison_report.v1", "markets"),
    ("contexts.group_proposal.v1", "contexts"),
    ("contexts.related_questions_report.v1", "contexts"),
    ("reviews.strengths_report.v1", "reviews"),
    ("ads.performance_report.v1", "ad_performance"),
    ("measure.ga4_report.v1", "measure"),
    ("technical.findings_plan.v1", "technical"),
    ("ads.rule_change_proposal.v1", "ad_rules"),
])
def test_catalog_actions_can_be_saved_without_execution(monkeypatch, action_id, page_id):
    calls = []
    monkeypatch.setattr(assistant_tasks.client, "post", lambda path, *, json, headers: calls.append((path, json, headers)) or {"id": ITEM, "status": "ready"})
    assistant_tasks.aeko_create_assistant_task(action_id, {"page_id": page_id}, "stable-key")
    assert calls[0][0] == "/api/action-items/assistant-tasks"
    assert calls[0][1]["action_id"] == action_id
    assert calls[0][2] == {"Idempotency-Key": "stable-key"}


def test_writing_format_tools_use_definition_routes_without_running_ads(monkeypatch):
    domain = str(uuid4())
    calls = []
    monkeypatch.setattr(assistant_tasks.client, "get", lambda path, *, params: calls.append(("get", path, params)) or {"formats": []})
    monkeypatch.setattr(assistant_tasks.client, "post", lambda path, *, json: calls.append(("post", path, json)) or {"id": str(uuid4()), "version": 1})
    assistant_tasks.aeko_get_ad_copy_formats(domain)
    assistant_tasks.aeko_create_ad_copy_format(domain, "Clear answer", "Lead with question", "Give grounded answer", [], ["pt-BR"])
    assert calls[0] == ("get", "/api/ad-copy-formats", {"domain_id": domain})
    assert calls[1] == ("post", "/api/ad-copy-formats", {
        "domain_id": domain, "name": "Clear answer", "title_instructions": "Lead with question",
        "description_instructions": "Give grounded answer", "examples": [], "language_codes": ["pt-BR"],
    })


def test_writing_format_create_carries_stable_optional_idempotency_key(monkeypatch):
    calls = []
    monkeypatch.setattr(assistant_tasks.client, "post", lambda path, **kwargs: calls.append((path, kwargs)) or {"id": str(uuid4()), "version": 1})
    domain = str(uuid4())
    assistant_tasks.aeko_create_ad_copy_format(domain, "Answer", "Title", "Body", [], ["en"], "stable-format-key")
    assert calls[0][0] == "/api/ad-copy-formats"
    assert calls[0][1]["headers"] == {"Idempotency-Key": "stable-format-key"}
    with pytest.raises(AekoToolInputError):
        assistant_tasks.aeko_create_ad_copy_format(domain, "Answer", "Title", "Body", [], ["en"], "")
    assert len(calls) == 1
