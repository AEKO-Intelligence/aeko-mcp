"""MCP tools for Ideal Customer Profiles used as tracked-prompt persona angles."""

import json
from typing import Any, Optional

from ..server import client, mcp
from ._annotations import READ_ONLY, WRITE_ONCE


def _safe(method, *args, **kwargs) -> tuple[Any, Optional[str]]:
    try:
        return method(*args, **kwargs), None
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


def _json_block(title: str, payload: Any) -> str:
    return f"# {title}\n\n```json\n{json.dumps(payload, ensure_ascii=False, indent=2, default=str)}\n```"


@mcp.tool(title="List ICPs", annotations=READ_ONLY)
def aeko_list_icps() -> str:
    """List the account's Ideal Customer Profiles.

    Use this before tracking prompts with a persona angle. The returned `id`
    is the `icp_id` accepted by `aeko_track_prompt` and suggested-prompt
    tracking tools.
    """
    result, err = _safe(client.get, "/api/icps")
    if err:
        return f"# Failed to list ICPs\n\n```\n{err}\n```"
    return _json_block("ICPs", result)


@mcp.tool(title="Create ICP", annotations=WRITE_ONCE)
def aeko_create_icp(
    name: str,
    persona_type_id: Optional[str] = None,
    target_country: Optional[str] = None,
    age_range: Optional[str] = None,
    interests: Optional[str] = None,
    purchase_motivation: Optional[str] = None,
    preferred_channels: Optional[str] = None,
    notes: Optional[str] = None,
    status: Optional[str] = None,
    source: Optional[str] = None,
) -> str:
    """Create an ICP that can be attached to tracked prompts.

    Persona is not directly settable on tracked prompts; choose or create an
    ICP that represents the persona, then pass its `id` as `icp_id`.
    """
    body = {
        "name": name,
        "persona_type_id": persona_type_id,
        "target_country": target_country,
        "age_range": age_range,
        "interests": interests,
        "purchase_motivation": purchase_motivation,
        "preferred_channels": preferred_channels,
        "notes": notes,
        "status": status,
        "source": source,
    }
    payload = {k: v for k, v in body.items() if v is not None}
    result, err = _safe(client.post, "/api/icps", json=payload)
    if err:
        return f"# Failed to create ICP\n\n```\n{err}\n```"
    return _json_block("ICP created", result)


@mcp.tool(title="Suggest ICPs", annotations=WRITE_ONCE)
def aeko_suggest_icps() -> str:
    """Generate draft ICPs for the current account.

    This calls AEKO's AI suggestion endpoint and returns drafts; use
    `aeko_create_icp` to persist one the merchant accepts.
    """
    result, err = _safe(client.post, "/api/icps/suggest", json={})
    if err:
        return f"# Failed to suggest ICPs\n\n```\n{err}\n```"
    return _json_block("Suggested ICPs", result)
