"""MCP wrappers for Context opportunity, Focus, metrics, and translations."""
from aeko_mcp import client as client_mod
from aeko_mcp.server import mcp
from aeko_mcp.tools import contexts


def _opportunity(context_id, state, recommendation_type="track_prompts"):
    return {
        "context_id": context_id,
        "title": f"Context {context_id}",
        "state": state,
        "headline_market": "US",
        "rollup": {
            "market": "US",
            "opportunity_score": 82.5,
            "confidence": "high",
            "measurement_stage": "measured",
        },
        "recommendation": {
            "type": recommendation_type,
            "reason_codes": ["insufficient_prompt_coverage"],
            "next_action": {
                "type": "manage_prompts",
                "label": "Track prompts",
            },
        },
    }


def test_context_focus_tools_are_registered_with_expected_annotations():
    registered = {tool.name: tool for tool in mcp._tool_manager.list_tools()}

    for name in (
        "aeko_list_context_opportunities",
        "aeko_get_context_metrics",
        "aeko_list_focused_contexts",
    ):
        annotations = registered[name].annotations
        assert annotations.readOnlyHint is True
        assert annotations.idempotentHint is True

    focus = registered["aeko_focus_context"].annotations
    assert focus.readOnlyHint is False
    assert focus.idempotentHint is False
    assert focus.destructiveHint is False

    unfocus = registered["aeko_unfocus_context"].annotations
    assert unfocus.readOnlyHint is False
    assert unfocus.destructiveHint is True

    translation = registered["aeko_update_context_translation"].annotations
    assert translation.readOnlyHint is False
    assert translation.idempotentHint is True
    assert translation.destructiveHint is False


def test_existing_context_archive_safety_annotations_remain_intact():
    registered = {tool.name: tool for tool in mcp._tool_manager.list_tools()}

    update = registered["aeko_update_context"].annotations
    archive = registered["aeko_archive_context"].annotations
    assert update.destructiveHint is True
    assert archive.readOnlyHint is False
    assert archive.idempotentHint is True
    assert archive.destructiveHint is False


def test_list_context_opportunities_calls_route_and_renders_decision_surface(
    monkeypatch,
):
    calls = []
    payload = {
        "domain_id": "domain-1",
        "focus_quota": {"used": 1, "limit": 5},
        "focused": [_opportunity("ctx-focused", "focused", "scale_creative")],
        "recommended": [_opportunity("ctx-recommended", "saved")],
        "contexts": [
            _opportunity("ctx-focused", "focused", "scale_creative"),
            _opportunity("ctx-recommended", "saved"),
        ],
    }

    def fake_get(path, params=None):
        calls.append((path, params))
        return payload

    monkeypatch.setattr(contexts.client, "get", fake_get)
    output = contexts.aeko_list_context_opportunities("domain-1", market="us")

    assert calls == [
        ("/api/contexts/opportunities", {"domain_id": "domain-1", "market": "US"})
    ]
    assert "**Focus quota**: 1 of 5 used" in output
    assert "## Focused (1)" in output
    assert "## Recommended (1)" in output
    assert "## All Contexts (2)" in output
    assert "`ctx-focused`" in output
    assert "focused" in output
    assert "82.5" in output
    assert "high" in output
    assert "measured" in output
    assert "scale_creative" in output
    assert "manage_prompts" in output
    assert "insufficient_prompt_coverage" in output


def test_get_context_metrics_calls_detail_route_with_normalized_market(monkeypatch):
    calls = []

    def fake_get(path, params=None):
        calls.append((path, params))
        return {"context_id": "ctx-1", "market": "KR", "rollup": {"score": 71}}

    monkeypatch.setattr(contexts.client, "get", fake_get)
    output = contexts.aeko_get_context_metrics("ctx-1", market="kr")

    assert calls == [("/api/contexts/ctx-1/metrics", {"market": "KR"})]
    assert "# Context metrics" in output
    assert '"market": "KR"' in output


def test_list_focused_contexts_calls_route_with_required_market(monkeypatch):
    calls = []

    def fake_get(path, params=None):
        calls.append((path, params))
        return [{"context_id": "ctx-1", "market": "JP", "slot_number": 1}]

    monkeypatch.setattr(contexts.client, "get", fake_get)
    output = contexts.aeko_list_focused_contexts("domain-1", "jp")

    assert calls == [
        ("/api/contexts/focus", {"domain_id": "domain-1", "market": "JP"})
    ]
    assert "Focused Contexts (JP)" in output
    assert '"slot_number": 1' in output


def test_context_read_tools_reject_invalid_market_before_call(monkeypatch):
    called = {"get": False}

    def unexpected_get(*args, **kwargs):
        called["get"] = True
        return {}

    monkeypatch.setattr(contexts.client, "get", unexpected_get)
    outputs = [
        contexts.aeko_list_context_opportunities("domain-1", market="x"),
        contexts.aeko_get_context_metrics("ctx-1", market="x"),
        contexts.aeko_list_focused_contexts("domain-1", "x"),
    ]

    assert all("2 to 8 characters" in output for output in outputs)
    assert called["get"] is False


def test_focus_context_validates_and_posts_normalized_payload(monkeypatch):
    calls = []

    def fake_post(path, json=None, headers=None):
        calls.append({"path": path, "json": json, "headers": headers})
        return {"id": "focus-1", "context_id": "ctx-1", **json}

    monkeypatch.setattr(contexts.client, "post", fake_post)
    output = contexts.aeko_focus_context(
        "ctx-1",
        "us",
        "BOTH",
        slot_number=2,
        reason="Launch measurement",
    )

    assert calls == [
        {
            "path": "/api/contexts/ctx-1/focus",
            "json": {
                "market": "US",
                "objective": "both",
                "slot_number": 2,
                "reason": "Launch measurement",
            },
            "headers": None,
        }
    ]
    assert "Context focused" in output
    assert '"market": "US"' in output


def test_focus_context_rejects_objective_slot_and_reason_before_post(monkeypatch):
    called = {"post": False}

    def unexpected_post(*args, **kwargs):
        called["post"] = True
        return {}

    monkeypatch.setattr(contexts.client, "post", unexpected_post)
    invalid_objective = contexts.aeko_focus_context("ctx-1", "US", "growth")
    invalid_slot = contexts.aeko_focus_context(
        "ctx-1", "US", "paid", slot_number=6
    )
    invalid_reason = contexts.aeko_focus_context(
        "ctx-1", "US", "organic", reason="x" * 2001
    )

    assert "organic`" in invalid_objective
    assert "between 1 and 5" in invalid_slot
    assert "at most 2000" in invalid_reason
    assert called["post"] is False


def test_client_preserves_complete_focus_conflict_detail():
    detail = {
        "code": "focus_slots_full",
        "error_code": "CONTEXT_FOCUS_CAP_REACHED",
        "message": "All 5 Focus slots are already in use.",
        "limit": 5,
        "current_focused": [{"context_title": "Occupied Context"}],
        "focused": [{"context_id": "ctx-occupied", "slot": 1}],
    }

    class FakeResponse:
        def json(self):
            return {"detail": detail}

    message = client_mod._extract_detail_message(FakeResponse())

    assert "focus_slots_full" in message
    assert "current_focused" in message
    assert "Occupied Context" in message
    assert "ctx-occupied" in message


def test_focus_context_surfaces_quota_detail_and_no_retry_guidance(monkeypatch):
    detail = {
        "code": "focus_slots_full",
        "message": "All 5 Focus slots are already in use.",
        "focused": [{"context_id": "ctx-occupied", "slot": 1}],
    }

    def fail(*args, **kwargs):
        raise RuntimeError(str(detail))

    monkeypatch.setattr(contexts.client, "post", fail)
    output = contexts.aeko_focus_context("ctx-new", "US", "organic")

    assert "focus_slots_full" in output
    assert "ctx-occupied" in output
    assert "Unfocus one before retrying" in output
    assert "do not retry or choose a slot automatically" in output


def test_unfocus_context_validates_reason_and_posts_end_period(monkeypatch):
    calls = []

    def fake_post(path, json=None, headers=None):
        calls.append({"path": path, "json": json, "headers": headers})
        return {"id": "focus-1", "ended_at": "2026-08-12T00:00:00Z", **json}

    monkeypatch.setattr(contexts.client, "post", fake_post)
    empty = contexts.aeko_unfocus_context("ctx-1", "US", "   ")
    output = contexts.aeko_unfocus_context(
        "ctx-1", "kr", "Rotate to higher-opportunity Context"
    )

    assert "non-empty" in empty
    assert calls == [
        {
            "path": "/api/contexts/ctx-1/unfocus",
            "json": {
                "market": "KR",
                "end_reason": "Rotate to higher-opportunity Context",
            },
            "headers": None,
        }
    ]
    assert "Context unfocused" in output


def test_update_context_translation_normalizes_and_puts_complete_entry(monkeypatch):
    calls = []

    def fake_put(path, json=None, headers=None):
        calls.append({"path": path, "json": json, "headers": headers})
        return {
            json["language"]: {
                "text": json["text"],
                "source": "edited",
                "updated_at": "2026-08-12T00:00:00Z",
            }
        }

    monkeypatch.setattr(contexts.client, "put", fake_put)
    output = contexts.aeko_update_context_translation(
        "ctx-1", "EN_us", "  Edited Context rendering  "
    )

    assert calls == [
        {
            "path": "/api/contexts/ctx-1/translations",
            "json": {"language": "en-us", "text": "Edited Context rendering"},
            "headers": None,
        }
    ]
    assert "Context translation updated" in output
    assert '"source": "edited"' in output


def test_update_context_translation_rejects_invalid_input_before_put(monkeypatch):
    called = {"put": False}

    def unexpected_put(*args, **kwargs):
        called["put"] = True
        return {}

    monkeypatch.setattr(contexts.client, "put", unexpected_put)
    invalid_language = contexts.aeko_update_context_translation("ctx-1", "e", "Text")
    empty_text = contexts.aeko_update_context_translation("ctx-1", "en", "   ")

    assert "2 to 16 characters" in invalid_language
    assert "non-empty" in empty_text
    assert called["put"] is False
