"""Offline contract checks for immutable action evidence and MCP errors."""

from uuid import uuid4

import anyio
import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from aeko_mcp.client import AekoAPIError
from aeko_mcp.tools import action_plan
from aeko_mcp.tools._structured import AekoToolError, AekoToolInputError


EVIDENCE = str(uuid4())
ITEM = "itm_context_search_test"


def payload(**changes):
    data = {
        "item_id": ITEM,
        "evidence_id": EVIDENCE,
        "kind": "review",
        "original_text": "É silencioso à noite. 조용해요.",
        "source_revision": "original-review-v1",
        "content_hash": "a" * 64,
        "metadata": {"language": "pt", "market": "BR", "verdict": "conditional"},
        "offset": 0,
        "next_offset": None,
        "complete": True,
    }
    data["total_chars"] = len(data["original_text"])
    data.update(changes)
    return data


def test_original_language_and_provenance_are_preserved(monkeypatch):
    calls = []
    original = payload()

    def get(path, *, params):
        calls.append((path, params))
        return original

    monkeypatch.setattr(action_plan.client, "get", get)
    result = action_plan.aeko_get_action_evidence(ITEM, EVIDENCE)
    assert result.model_dump() == original
    assert calls == [(f"/api/action-items/{ITEM}/evidence/{EVIDENCE}", {"offset": 0, "max_chars": 8000})]


def test_following_character_offsets_preserves_unicode(monkeypatch):
    original = "조용해요. É silencioso."

    def get(path, *, params):
        start = params["offset"]
        text = original[start:start + params["max_chars"]]
        end = start + len(text)
        return payload(original_text=text, offset=start, total_chars=len(original),
                       complete=end == len(original), next_offset=None if end == len(original) else end)

    monkeypatch.setattr(action_plan.client, "get", get)
    chunks = []
    offset = 0
    while True:
        result = action_plan.aeko_get_action_evidence(ITEM, EVIDENCE, offset=offset, max_chars=4)
        chunks.append(result.original_text)
        if result.complete:
            break
        offset = result.next_offset
    assert "".join(chunks) == original


@pytest.mark.parametrize("arguments", [
    {"item_id": "itm_x/../../users"}, {"item_id": "itm_x?expand=all"},
    {"item_id": "unknown"}, {"evidence_id": "not-a-uuid"},
    {"offset": -1}, {"offset": True}, {"max_chars": 0},
    {"max_chars": 8001}, {"max_chars": True},
])
def test_invalid_inputs_never_reach_backend(monkeypatch, arguments):
    def unexpected(*args, **kwargs):
        pytest.fail("invalid input reached backend")

    monkeypatch.setattr(action_plan.client, "get", unexpected)
    with pytest.raises(AekoToolInputError):
        action_plan.aeko_get_action_evidence(**{"item_id": ITEM, "evidence_id": EVIDENCE, **arguments})


@pytest.mark.parametrize("changes", [
    {"item_id": "itm_other"}, {"evidence_id": str(uuid4())},
    {"offset": 1}, {"complete": False}, {"next_offset": 1},
    {"total_chars": 0}, {"original_text": "x" * 8001},
    {"metadata": {"unbounded": "x" * 65536}},
    {"content_hash": "not-a-digest"},
])
def test_malformed_backend_snapshot_is_not_success(monkeypatch, changes):
    monkeypatch.setattr(action_plan.client, "get", lambda *args, **kwargs: payload(**changes))
    with pytest.raises(AekoToolError) as error:
        action_plan.aeko_get_action_evidence(ITEM, EVIDENCE)
    assert error.value.code == "INVALID_BACKEND_RESPONSE"


def test_diagnostic_does_not_become_claim_support(monkeypatch):
    data = payload(kind="pdp_readability_check", metadata={"readability_reason": "image_only", "score": None})
    monkeypatch.setattr(action_plan.client, "get", lambda *args, **kwargs: data)
    result = action_plan.aeko_get_action_evidence(ITEM, EVIDENCE)
    assert result.kind == "pdp_readability_check"
    assert result.metadata["score"] is None


def test_v3_save_preserves_selected_scope_and_original_instructions(monkeypatch):
    calls = []
    plan = {
        "schema_version": "context-search-v1", "run_id": str(uuid4()),
        "result_revision": str(uuid4()), "product_store_id": str(uuid4()),
        "task_kind": "pdp_revision", "destination": "local_pdp_preview",
        "evidence_ids": [EVIDENCE], "observation_ids": [],
        "template_version": "context-search-templates-v1", "basis_digest": "b" * 64,
        "instruction_body": "원문과 조건을 유지해 주세요. É silencioso à noite.",
    }

    def save(path, *, json, headers):
        calls.append((path, json, headers))
        return {"id": ITEM, "status": "ready"}

    monkeypatch.setattr(action_plan.client, "post", save)
    action_plan.aeko_create_action_item(
        domain_id=str(uuid4()), artifact_type="own_store_markdown",
        idempotency_key="saved-search-plan-v1", context_search_plan=plan,
    )
    assert len(calls) == 1
    assert calls[0][0] == "/api/action-items"
    assert calls[0][1]["context_search_plan"] == plan
    assert "content_format" not in calls[0][1]
    assert calls[0][2] == {"Idempotency-Key": "saved-search-plan-v1"}


def test_revoked_evidence_raises_bounded_mcp_error(monkeypatch):
    def missing(*args, **kwargs):
        raise AekoAPIError("private body aeko_ot1_secret", http_status=404)

    monkeypatch.setattr(action_plan.client, "get", missing)

    async def call():
        async with create_connected_server_and_client_session(action_plan.mcp._mcp_server) as session:
            result = await session.call_tool("aeko_get_action_evidence", {"item_id": ITEM, "evidence_id": EVIDENCE})
            tools = {tool.name: tool for tool in (await session.list_tools()).tools}
            return result, tools["aeko_get_action_evidence"]

    result, tool = anyio.run(call)
    assert result.isError is True
    text = "".join(block.text for block in result.content if hasattr(block, "text"))
    assert "aeko_ot1_secret" not in text
    assert "NOT_FOUND" in text
    assert tool.annotations.readOnlyHint is True
    assert {"original_text", "source_revision", "next_offset", "complete"} <= set(tool.outputSchema["properties"])
