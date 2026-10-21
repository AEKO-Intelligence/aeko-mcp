"""Transport-level bearer gate of ``create_streamable_http_app``.

MCP clients only refresh a token or re-run OAuth after an HTTP 401. These
tests pin the gate's contract: no bearer gets the discovery challenge, a
bearer the embedding app's validator rejects gets ``invalid_token``, and a
validator failure never blocks the request.
"""

import logging

import anyio
import httpx
import pytest

from aeko_mcp import server

ISSUER = "https://aeko.example"
RESOURCE_METADATA = f"{ISSUER}/.well-known/oauth-protected-resource"
INVALID_TOKEN_CHALLENGE = (
    'Bearer error="invalid_token", '
    'error_description="The access token is invalid or expired", '
    f'resource_metadata="{RESOURCE_METADATA}"'
)


class _InnerApp:
    """Stands in for FastMCP's app and records what reached it."""

    def __init__(self):
        self.calls: list[dict] = []

    async def __call__(self, scope, receive, send):
        self.calls.append(
            {"method": scope.get("method"), "auth": server.client._headers()}
        )
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": b'{"ok":true}'})


class _Validator:
    def __init__(self, result=True, error: Exception | None = None):
        self.result = result
        self.error = error
        self.seen: list[str] = []

    async def __call__(self, token: str) -> bool:
        self.seen.append(token)
        if self.error is not None:
            raise self.error
        return self.result


@pytest.fixture
def inner(monkeypatch):
    app = _InnerApp()
    monkeypatch.setattr(server.mcp, "streamable_http_app", lambda: app)
    return app


def _request(app, method="POST", token=None, headers=None):
    request_headers = dict(headers or {})
    if token is not None:
        request_headers["Authorization"] = f"Bearer {token}"

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://mcp.test"
        ) as http:
            return await http.request(method, "/", headers=request_headers, json=None)

    return anyio.run(run)


def test_missing_bearer_keeps_discovery_challenge(inner):
    validator = _Validator()
    app = server.create_streamable_http_app(issuer_url=ISSUER, token_validator=validator)

    response = _request(app)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == (
        f'Bearer realm="aeko", resource_metadata="{RESOURCE_METADATA}"'
    )
    assert response.json()["error"] == "unauthorized"
    assert validator.seen == []
    assert inner.calls == []


def test_rejected_bearer_gets_invalid_token_401(inner):
    validator = _Validator(result=False)
    app = server.create_streamable_http_app(issuer_url=ISSUER, token_validator=validator)

    response = _request(app, token="aeko_ot1_expired")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == INVALID_TOKEN_CHALLENGE
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {
        "error": "invalid_token",
        "error_description": "The access token is invalid or expired",
    }
    assert validator.seen == ["aeko_ot1_expired"]
    assert inner.calls == []


def test_accepted_bearer_reaches_mcp_with_request_auth(inner):
    validator = _Validator(result=True)
    app = server.create_streamable_http_app(issuer_url=ISSUER, token_validator=validator)

    response = _request(app, token="aeko_ot1_live")

    assert response.status_code == 200
    assert validator.seen == ["aeko_ot1_live"]
    assert inner.calls == [
        {"method": "POST", "auth": {"Authorization": "Bearer aeko_ot1_live"}}
    ]


def test_validator_failure_lets_request_through_and_logs(inner, caplog):
    validator = _Validator(error=RuntimeError("database unavailable"))
    app = server.create_streamable_http_app(issuer_url=ISSUER, token_validator=validator)

    with caplog.at_level(logging.WARNING, logger="aeko_mcp.server"):
        response = _request(app, token="aeko_ot1_unknown_state")

    assert response.status_code == 200
    assert len(inner.calls) == 1
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings, "a validator failure must be logged"
    assert all("aeko_ot1_unknown_state" not in r.getMessage() for r in warnings)


def test_options_preflight_skips_validation(inner):
    validator = _Validator(result=False)
    app = server.create_streamable_http_app(issuer_url=ISSUER, token_validator=validator)

    without_token = _request(app, method="OPTIONS")
    with_rejected_token = _request(app, method="OPTIONS", token="aeko_ot1_bad")

    assert without_token.status_code == 200
    assert with_rejected_token.status_code == 200
    assert validator.seen == []
    assert [call["method"] for call in inner.calls] == ["OPTIONS", "OPTIONS"]


def test_without_validator_any_bearer_is_forwarded(inner):
    app = server.create_streamable_http_app(issuer_url=ISSUER)

    response = _request(app, token="anything")

    assert response.status_code == 200
    assert inner.calls[0]["auth"] == {"Authorization": "Bearer anything"}


def test_validator_without_issuer_omits_resource_metadata(inner):
    validator = _Validator(result=False)
    app = server.create_streamable_http_app(token_validator=validator)

    rejected = _request(app, token="bad")
    no_token = _request(app)

    assert rejected.status_code == 401
    assert rejected.headers["www-authenticate"] == (
        'Bearer error="invalid_token", '
        'error_description="The access token is invalid or expired"'
    )
    # Standalone servers without an issuer keep forwarding token-less calls.
    assert no_token.status_code == 200
    assert validator.seen == ["bad"]


def test_rejection_does_not_leak_request_auth(inner):
    rejecting = server.create_streamable_http_app(
        issuer_url=ISSUER, token_validator=_Validator(result=False)
    )
    _request(rejecting, token="aeko_ot1_bad")

    assert server.client._headers() == {}
