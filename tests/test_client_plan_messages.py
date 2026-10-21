"""Plan-gate errors reach MCP users as neutral availability statements."""

import httpx

from aeko_mcp.client import AekoAPIError, _http_error


def _error(status: int, body) -> AekoAPIError:
    request = httpx.Request("GET", "http://backend.test/api/ga4/status")
    response = httpx.Response(status, json=body, request=request)
    return _http_error(httpx.HTTPStatusError("failed", request=request, response=response))


def test_upgrade_required_code_renders_as_not_included_in_plan():
    error = _error(403, {"detail": {"code": "UPGRADE_REQUIRED", "feature": "measure_discovery"}})

    message = str(error)
    assert "This feature (measure_discovery) isn't included in your current plan." in message
    assert "UPGRADE_REQUIRED" not in message
    assert "upgrade" not in message.lower()
    # Structured callers still get the machine-readable code.
    assert error.code == "UPGRADE_REQUIRED"
    assert error.http_status == 403


def test_upgrade_required_without_feature_key():
    message = str(_error(403, {"detail": {"code": "UPGRADE_REQUIRED"}}))

    assert "This feature isn't included in your current plan." in message


def test_plain_backend_detail_still_wins():
    message = str(_error(403, {"detail": "Drift Detection isn't included in your current plan."}))

    assert message.endswith("Drift Detection isn't included in your current plan.")
