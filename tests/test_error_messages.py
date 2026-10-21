"""Backend failures read as plain sentences in tool results."""

import httpx
import pytest

from aeko_mcp.client import AekoAPIError, _http_error, error_text
from aeko_mcp.tools import assistant_tasks, content_ideas, marketing
from aeko_mcp.tools._structured import AekoToolError


def _error(status: int, body=None) -> AekoAPIError:
    request = httpx.Request("GET", "http://backend.test/api/x")
    response = (
        httpx.Response(status, json=body, request=request)
        if body is not None
        else httpx.Response(status, request=request)
    )
    return _http_error(httpx.HTTPStatusError("failed", request=request, response=response))


def test_404_detail_stands_alone_without_a_generic_guess():
    error = _error(
        404,
        {"detail": {"code": "OPENAI_ADS_ACCOUNT_NOT_CONNECTED", "message": "Connect an OpenAI Ads account first."}},
    )

    assert str(error) == "[OPENAI_ADS_ACCOUNT_NOT_CONNECTED] Connect an OpenAI Ads account first."
    assert error.code == "OPENAI_ADS_ACCOUNT_NOT_CONNECTED"


def test_404_without_detail_does_not_name_retired_ids():
    message = str(_error(404))

    assert message == "Not found. Check the IDs passed to the tool."
    assert "analysis_id" not in message


def test_422_validation_list_renders_field_messages_not_a_raw_dump():
    detail = [
        {
            "type": "model_attributes_type",
            "loc": ["body", "conditions", 0, "window"],
            "msg": "Input should be a valid dictionary or object to extract fields from",
            "input": "today",
        },
        {"type": "missing", "loc": ["body", "guards"], "msg": "Field required", "input": {}},
    ]

    message = str(_error(422, {"detail": detail}))

    assert message == (
        "API error 422 (validation failed). — "
        "conditions[0].window: Input should be a valid dictionary or object to extract fields from; "
        "guards: Field required"
    )
    assert "model_attributes_type" not in message
    assert "'loc'" not in message


def test_422_validation_list_is_capped():
    detail = [{"loc": ["body", f"field_{i}"], "msg": "Field required"} for i in range(8)]

    message = str(_error(422, {"detail": detail}))

    assert "field_4: Field required" in message
    assert "field_5" not in message
    assert message.endswith("and 3 more")


def test_422_validation_list_keeps_a_field_named_body_and_odd_locations():
    detail = [
        {"loc": ["body", "creative", "body"], "msg": "String too long"},
        {"loc": ["query", "path"], "msg": "Field required"},
        {"loc": "domain_id", "msg": "Invalid UUID"},
        {"loc": 7, "msg": "Bad item"},
        {"msg": "Something else"},
        "plain string error",
    ]

    message = str(_error(422, {"detail": detail}))

    assert "creative.body: String too long" in message
    assert "path: Field required" in message
    assert "domain_id: Invalid UUID" in message
    assert "[7]: Bad item" in message
    assert "Something else" in message
    assert message.endswith("and 1 more")


def test_error_text_drops_the_python_class_name_for_backend_failures():
    assert error_text(AekoAPIError("Campaign not found", http_status=404)) == "Campaign not found"
    assert error_text(ValueError("bad input")) == "ValueError: bad input"


def test_ad_tool_without_connected_account_reads_plainly(monkeypatch):
    def fail(*args, **kwargs):
        raise _error(
            404,
            {"detail": {"code": "OPENAI_ADS_ACCOUNT_NOT_CONNECTED", "message": "Connect an OpenAI Ads account first."}},
        )

    monkeypatch.setattr(marketing.client, "get", fail)
    output = marketing.aeko_get_ad_rule_capabilities("domain-1")

    assert output == (
        "# Failed to get ad rule capabilities\n\n```\n"
        "[OPENAI_ADS_ACCOUNT_NOT_CONNECTED] Connect an OpenAI Ads account first.\n```"
    )


def test_content_idea_handoff_not_found_reads_plainly(monkeypatch):
    def fail(*args, **kwargs):
        raise _error(404, {"detail": "Content idea handoff not found"})

    monkeypatch.setattr(content_ideas.client, "get", fail)
    output = content_ideas.aeko_get_content_idea_handoff("00000000-0000-0000-0000-000000000000")

    assert "Content idea handoff not found" in output
    assert "RuntimeError" not in output
    assert "analysis_id" not in output


def test_outputs_of_a_plain_action_item_explain_what_to_read_instead(monkeypatch):
    def fail(*args, **kwargs):
        raise _error(404, {"detail": {"code": "ASSISTANT_TASK_NOT_FOUND"}})

    monkeypatch.setattr(assistant_tasks.client, "get", fail)
    with pytest.raises(AekoToolError) as caught:
        assistant_tasks.aeko_list_action_outputs("itm_plain_item")

    payload = caught.value.payload
    assert payload["code"] == "ASSISTANT_TASK_NOT_FOUND"
    assert payload["http_status"] == 404
    assert "not a saved assistant task" in payload["message"]
    assert "aeko_get_action_plan" in payload["message"]
