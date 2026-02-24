import os
import httpx

ERROR_MESSAGES = {
    401: "Authentication failed. Check your AEKO_API_KEY environment variable.",
    403: "Access denied. Your subscription may not include this feature.",
    404: "Resource not found. Check the domain_id or analysis_id.",
    500: "AEKO server error. Please try again later.",
}


class AekoClient:
    def __init__(self):
        self.api_url = os.environ.get("AEKO_API_URL", "https://api.aeko.ai")
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
            msg = ERROR_MESSAGES.get(e.response.status_code, f"API error: {e.response.status_code}")
            raise RuntimeError(msg) from None
        except httpx.ConnectError:
            raise RuntimeError("Cannot connect to AEKO API. Check AEKO_API_URL.") from None

    def post(self, path: str, json: dict | None = None) -> dict:
        try:
            resp = self._client.post(path, json=json)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            msg = ERROR_MESSAGES.get(e.response.status_code, f"API error: {e.response.status_code}")
            raise RuntimeError(msg) from None
        except httpx.ConnectError:
            raise RuntimeError("Cannot connect to AEKO API. Check AEKO_API_URL.") from None

    def close(self):
        self._client.close()
