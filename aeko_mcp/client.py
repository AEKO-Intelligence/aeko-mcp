import os
import httpx

# Fallback messages when the backend doesn't surface a useful ``detail``.
# Whenever the backend sends a FastAPI-style {"detail": ...} body, that
# message wins — so the Growth+ upgrade pitch on store-write endpoints
# reaches Starter users instead of getting masked by a generic fallback.
ERROR_MESSAGES = {
    401: "Authentication failed. Check your AEKO_API_KEY environment variable.",
    403: "Access denied. Your subscription may not include this feature.",
    404: "Resource not found. Check the domain_id or analysis_id.",
    500: "AEKO server error. Please try again later.",
    502: "Upstream store API failed (Cafe24 / Shopify). The merchant's store token may need to be reconnected in Settings → Store Integrations.",
}


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
        # Store-write platform error shape.
        message = detail.get("message")
        code = detail.get("code")
        if message and code:
            return f"[{code}] {message}"
        if message:
            return str(message)
        return str(detail)
    return str(detail)


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


class AekoClient:
    def __init__(self):
        self.api_url = os.environ.get("AEKO_API_URL", "https://aeko-backend.purplehill-6906b42f.koreacentral.azurecontainerapps.io")
        self.api_key = os.environ.get("AEKO_API_KEY", "")
        self._client = httpx.Client(
            base_url=self.api_url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=30.0,
        )

    def get(self, path: str, params: dict | None = None) -> dict:
        try:
            resp = self._client.get(path, params=params)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            raise RuntimeError(_format_http_error(e)) from None
        except httpx.ConnectError:
            raise RuntimeError("Cannot connect to AEKO API. Check AEKO_API_URL.") from None

    def post(self, path: str, json: dict | None = None) -> dict:
        try:
            resp = self._client.post(path, json=json)
            resp.raise_for_status()
            return resp.json() if resp.content else {}
        except httpx.HTTPStatusError as e:
            raise RuntimeError(_format_http_error(e)) from None
        except httpx.ConnectError:
            raise RuntimeError("Cannot connect to AEKO API. Check AEKO_API_URL.") from None

    def put(self, path: str, json: dict | None = None) -> dict:
        try:
            resp = self._client.put(path, json=json)
            resp.raise_for_status()
            return resp.json() if resp.content else {}
        except httpx.HTTPStatusError as e:
            raise RuntimeError(_format_http_error(e)) from None
        except httpx.ConnectError:
            raise RuntimeError("Cannot connect to AEKO API. Check AEKO_API_URL.") from None

    def delete(self, path: str, params: dict | None = None) -> dict:
        try:
            resp = self._client.delete(path, params=params)
            resp.raise_for_status()
            return resp.json() if resp.content else {}
        except httpx.HTTPStatusError as e:
            raise RuntimeError(_format_http_error(e)) from None
        except httpx.ConnectError:
            raise RuntimeError("Cannot connect to AEKO API. Check AEKO_API_URL.") from None

    def close(self):
        self._client.close()
