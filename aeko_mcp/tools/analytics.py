"""MCP tools for AEKO measurement and analytics reads."""

import json
from typing import Any, Optional

from ..server import client, mcp
from ._annotations import READ_ONLY


def _json_block(title: str, payload: Any) -> str:
    return f"# {title}\n\n```json\n{json.dumps(payload, ensure_ascii=False, indent=2, default=str)}\n```"


def _prompt_ids_param(prompt_ids: Optional[list[str]]) -> Optional[str]:
    if not prompt_ids:
        return None
    return ",".join(str(pid) for pid in prompt_ids if str(pid).strip())


@mcp.tool(title="Get share of voice", annotations=READ_ONLY)
def aeko_get_share_of_voice(
    domain_id: str,
    prompt_ids: Optional[list[str]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> str:
    """Read Share of Voice for a domain across tracked prompt responses.

    Starter+ feature server-side. Optional filters scope to prompt ids and a
    date range (`YYYY-MM-DD`).
    """
    params: dict[str, Any] = {"domain_id": domain_id}
    encoded_prompt_ids = _prompt_ids_param(prompt_ids)
    if encoded_prompt_ids:
        params["prompt_ids"] = encoded_prompt_ids
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date
    data = client.get("/api/monitoring/sov", params=params)
    return _json_block("GET /api/monitoring/sov", data)


@mcp.tool(title="Get answer drift", annotations=READ_ONLY)
def aeko_get_answer_drift(
    domain_id: str,
    days: int = 30,
    prompt_ids: Optional[list[str]] = None,
) -> str:
    """Read answer drift for a domain over a recent lookback window."""
    params: dict[str, Any] = {
        "domain_id": domain_id,
        "days": max(1, min(int(days), 365)),
    }
    encoded_prompt_ids = _prompt_ids_param(prompt_ids)
    if encoded_prompt_ids:
        params["prompt_ids"] = encoded_prompt_ids
    data = client.get("/api/monitoring/drift", params=params)
    return _json_block("GET /api/monitoring/drift", data)


@mcp.tool(title="Get measure dashboard", annotations=READ_ONLY)
def aeko_get_measure(
    domain_id: str,
    view: str = "readiness",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> str:
    """Read AEKO Measure views: readiness, discovery, or impact."""
    normalized_view = view.strip().lower()
    if normalized_view not in {"readiness", "discovery", "impact"}:
        return "Invalid `view`. Use one of: readiness, discovery, impact."
    params: dict[str, Any] = {"domain_id": domain_id}
    if normalized_view in {"discovery", "impact"}:
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
    path = f"/api/measure/{normalized_view}"
    data = client.get(path, params=params)
    return _json_block(f"GET {path}", data)

