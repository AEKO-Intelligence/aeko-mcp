import os
from contextvars import ContextVar

import httpx

# Fallback messages when the backend doesn't surface a useful ``detail``.
# Whenever the backend sends a FastAPI-style {"detail": ...} body, that
# message wins — so backend upgrade pitches (e.g., Pro+ for Content
# Generation, or trial-expired prompts) reach the user instead of
# getting masked by a generic fallback.
ERROR_MESSAGES = {
    401: "Authentication failed. Your AEKO session may be expired or invalid. Reconnect through your MCP client.",
    402: "Tracked-prompt quota exceeded (HTTP 402). Review the current package limit and narrow the fan-out.",
    403: "Access denied. Your subscription may not include this feature.",
    404: "Resource not found. Check the domain_id or analysis_id.",
    409: "API error 409 (conflict).",
    422: "API error 422 (validation failed).",
    429: "API error 429 (rate limited).",
    500: "AEKO server error. Please try again later.",
    502: "Upstream service failed (HTTP 502).",
    503: "Service unavailable (HTTP 503).",
}

CONNECT_ERROR_MESSAGE = "Cannot connect to AEKO API. Check AEKO_API_URL."


class AekoAPIError(RuntimeError):
    """A failed AEKO backend call with its machine-readable details retained.

    ``str(error)`` is exactly the message this client has always raised, so
    tools that render errors as text keep their output. Structured tool
    boundaries read the attributes instead of parsing that message.

    ``request_sent`` is False only when the connection could not be
    established, so the backend cannot have received the request.
    """

    def __init__(
        self,
        message: str,
        *,
        http_status: int | None = None,
        code: str | None = None,
        audit_id: str | None = None,
        request_sent: bool = True,
    ):
        super().__init__(message)
        self.http_status = http_status
        self.code = code
        self.audit_id = audit_id
        self.request_sent = request_sent


def legacy_error_name(exc: BaseException) -> str:
    """Return the class label that text-rendering tools have always printed."""
    return "RuntimeError" if isinstance(exc, AekoAPIError) else type(exc).__name__


_request_auth_token: ContextVar[str | None] = ContextVar("aeko_request_auth_token", default=None)
_request_auth_active: ContextVar[bool] = ContextVar("aeko_request_auth_active", default=False)


def _extract_detail_message(resp: httpx.Response) -> str | None:
    """Pull a human-readable message out of a FastAPI error response.

    FastAPI uses ``{"detail": ...}`` where ``detail`` is either a string
    or a dict. For store-write platform errors the backend returns a
    dict like ``{"code": "REAUTH", "message": "...", "audit_id": "..."}``
    — we surface the nested ``message`` in that case. Returns None if
    the body is not JSON or has no usable ``detail``.
    """
    try:
        body = resp.json()
    except Exception:
        return None
    if not isinstance(body, dict):
        return None
    detail = body.get("detail")
    if detail is None:
        return None
    if isinstance(detail, str):
        return detail
    if isinstance(detail, dict):
        if {"would_add", "remaining", "blocked"}.issubset(detail):
            return (
                "This request would add "
                f"{detail['would_add']} tracked-prompt variant(s), but only "
                f"{detail['remaining']} slot(s) remain."
            )
        # Focus conflicts carry the current slot occupants an agent must show
        # before asking the user what to unfocus. Preserve the complete detail
        # instead of collapsing it to only ``[code] message`` below.
        if detail.get("code") == "focus_slots_full":
            return str(detail)
        # Store-write platform error shape.
        message = detail.get("message")
        code = detail.get("code")
        if message and code:
            return f"[{code}] {message}"
        if message:
            return str(message)
        return str(detail)
    return str(detail)


def _extract_detail_fields(resp: httpx.Response) -> tuple[str | None, str | None]:
    """Return the typed ``detail.code`` and ``detail.audit_id``, when present."""
    try:
        body = resp.json()
    except Exception:
        return None, None
    detail = body.get("detail") if isinstance(body, dict) else None
    if not isinstance(detail, dict):
        return None, None
    code = detail.get("code")
    audit_id = detail.get("audit_id")
    return (
        code if isinstance(code, str) else None,
        audit_id if isinstance(audit_id, str) else None,
    )


def _format_http_error(e: httpx.HTTPStatusError) -> str:
    """Build the best available error string for a failed HTTP call.

    Priority: backend-supplied detail > code-specific fallback > generic.
    """
    code = e.response.status_code
    backend_msg = _extract_detail_message(e.response)
    fallback = ERROR_MESSAGES.get(code, f"API error: {code}")
    if backend_msg:
        return f"{fallback} — {backend_msg}" if code in ERROR_MESSAGES and backend_msg != fallback else backend_msg
    return fallback


def _http_error(e: httpx.HTTPStatusError) -> AekoAPIError:
    code, audit_id = _extract_detail_fields(e.response)
    return AekoAPIError(
        _format_http_error(e),
        http_status=e.response.status_code,
        code=code,
        audit_id=audit_id,
    )


def _connect_error() -> AekoAPIError:
    return AekoAPIError(CONNECT_ERROR_MESSAGE, request_sent=False)


class AekoClient:
    def __init__(self):
        self.api_url = os.environ.get("AEKO_API_URL", "https://aeko-backend.purplehill-6906b42f.koreacentral.azurecontainerapps.io")
        self._client = httpx.Client(base_url=self.api_url, timeout=30.0)

    def set_request_auth_token(self, token: str | None):
        token_ctx = _request_auth_token.set(token)
        active_ctx = _request_auth_active.set(True)
        return token_ctx, active_ctx

    def reset_request_auth_token(self, ctx_tokens) -> None:
        token_ctx, active_ctx = ctx_tokens
        _request_auth_token.reset(token_ctx)
        _request_auth_active.reset(active_ctx)

    def _headers(self) -> dict[str, str]:
        token = _request_auth_token.get() if _request_auth_active.get() else None
        return {"Authorization": f"Bearer {token}"} if token else {}

    def get(self, path: str, params: dict | None = None) -> dict:
        try:
            resp = self._client.get(path, params=params, headers=self._headers())
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            raise _http_error(e) from None
        except httpx.ConnectError:
            raise _connect_error() from None

    def get_text(
        self,
        path: str,
        params: dict | None = None,
        accept: str = "text/markdown",
    ) -> str:
        """GET an endpoint that returns non-JSON text (e.g. Plan.md)."""
        headers = {**self._headers(), "Accept": accept}
        try:
            resp = self._client.get(path, params=params, headers=headers)
            resp.raise_for_status()
            return resp.text
        except httpx.HTTPStatusError as e:
            raise _http_error(e) from None
        except httpx.ConnectError:
            raise _connect_error() from None

    def _merged_headers(self, extra: dict | None) -> dict[str, str]:
        """Auth headers plus any per-call extras (e.g. an Idempotency-Key for
        redelivery-safe OpenAI Ads writes). Extras win on key collision."""
        headers = self._headers()
        if extra:
            headers.update({k: str(v) for k, v in extra.items() if v is not None})
        return headers

    def patch(self, path: str, json: dict | None = None, headers: dict | None = None) -> dict:
        try:
            resp = self._client.patch(path, json=json, headers=self._merged_headers(headers))
            resp.raise_for_status()
            return resp.json() if resp.content else {}
        except httpx.HTTPStatusError as e:
            raise _http_error(e) from None
        except httpx.ConnectError:
            raise _connect_error() from None

    def post(
        self,
        path: str,
        json: dict | None = None,
        params: dict | None = None,
        headers: dict | None = None,
    ) -> dict:
        try:
            resp = self._client.post(path, json=json, params=params, headers=self._merged_headers(headers))
            resp.raise_for_status()
            return resp.json() if resp.content else {}
        except httpx.HTTPStatusError as e:
            raise _http_error(e) from None
        except httpx.ConnectError:
            raise _connect_error() from None

    def put(self, path: str, json: dict | None = None, headers: dict | None = None) -> dict:
        try:
            resp = self._client.put(path, json=json, headers=self._merged_headers(headers))
            resp.raise_for_status()
            return resp.json() if resp.content else {}
        except httpx.HTTPStatusError as e:
            raise _http_error(e) from None
        except httpx.ConnectError:
            raise _connect_error() from None

    def delete(self, path: str, params: dict | None = None) -> dict:
        try:
            resp = self._client.delete(path, params=params, headers=self._headers())
            resp.raise_for_status()
            return resp.json() if resp.content else {}
        except httpx.HTTPStatusError as e:
            raise _http_error(e) from None
        except httpx.ConnectError:
            raise _connect_error() from None

    def close(self):
        self._client.close()
