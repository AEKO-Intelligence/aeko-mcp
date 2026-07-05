"""MCP tools for saved prompt views.

The backend still stores these in legacy campaign tables, but the public API
surface is `/api/views`. Tool names avoid "campaign" so they do not collide
with OpenAI Ads campaign tools.
"""

import json
from typing import Any, Optional

from ..server import client, mcp
from ._annotations import READ_ONLY, WRITE, WRITE_ONCE


def _safe(method, *args, **kwargs) -> tuple[Any, Optional[str]]:
    try:
        return method(*args, **kwargs), None
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


def _json_block(title: str, payload: Any) -> str:
    return f"# {title}\n\n```json\n{json.dumps(payload, ensure_ascii=False, indent=2, default=str)}\n```"


@mcp.tool(title="List saved prompt views", annotations=READ_ONLY)
def aeko_list_views(domain_id: str, status: Optional[str] = None) -> str:
    """List saved prompt views for a domain.

    Use a returned `id` as `view_id` when tracking prompts or adding prompts
    to an existing view.
    """
    params: dict[str, Any] = {"domain_id": domain_id}
    if status:
        params["status"] = status
    result, err = _safe(client.get, "/api/views", params=params)
    if err:
        return f"# Failed to list views\n\n```\n{err}\n```"
    return _json_block("Saved prompt views", result)


@mcp.tool(title="Create saved prompt view", annotations=WRITE_ONCE)
def aeko_create_view(
    domain_id: str,
    name: str,
    product_label: Optional[str] = None,
    description: Optional[str] = None,
    scope: Optional[str] = None,
    prompt_ids: Optional[list[str]] = None,
) -> str:
    """Create a saved prompt view, optionally seeded with tracked prompt ids."""
    body = {
        "domain_id": domain_id,
        "name": name,
        "product_label": product_label,
        "description": description,
        "scope": scope,
        "prompt_ids": prompt_ids,
    }
    payload = {k: v for k, v in body.items() if v is not None}
    result, err = _safe(client.post, "/api/views", json=payload)
    if err:
        return f"# Failed to create view\n\n```\n{err}\n```"
    return _json_block("Saved prompt view created", result)


@mcp.tool(title="Add prompts to saved view", annotations=WRITE)
def aeko_add_prompts_to_view(view_id: str, prompt_ids: list[str]) -> str:
    """Add tracked prompts to an existing saved prompt view."""
    if not prompt_ids:
        return "# No prompt ids provided."
    result, err = _safe(
        client.post,
        f"/api/views/{view_id}/prompts",
        json={"prompt_ids": prompt_ids},
    )
    if err:
        return f"# Failed to add prompts to view\n\n```\n{err}\n```"
    return _json_block("Prompts added to view", result)
