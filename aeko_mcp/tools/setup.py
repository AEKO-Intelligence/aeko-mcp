"""MCP tools for account setup flows."""

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


@mcp.tool(title="Generate starter prompts", annotations=WRITE_ONCE)
def aeko_generate_starter_prompts(domain_id: str) -> str:
    """Generate starter tracked-prompt drafts for a domain.

    The backend gathers available domain, content, and product inputs, stores
    a draft offer, and returns the proposed prompts.
    """
    result, err = _safe(
        client.post,
        "/api/tracked-prompts/starter/generate",
        json={"domain_id": domain_id},
    )
    if err:
        return f"# Failed to generate starter prompts\n\n```\n{err}\n```"
    return _json_block("Starter prompts generated", result)


@mcp.tool(title="Accept starter prompts", annotations=WRITE)
def aeko_accept_starter_prompts(domain_id: str, selections: list[dict]) -> str:
    """Accept selected starter prompts and create tracked prompts."""
    if not selections:
        return "# No starter prompt selections provided."
    result, err = _safe(
        client.post,
        "/api/tracked-prompts/starter/accept",
        json={"domain_id": domain_id, "selections": selections},
    )
    if err:
        return f"# Failed to accept starter prompts\n\n```\n{err}\n```"
    return _json_block("Starter prompts accepted", result)


@mcp.tool(title="Get current target markets", annotations=READ_ONLY)
def aeko_get_current_markets() -> str:
    """Read the account-wide selected market list before replacing it.

    ``aeko_update_markets`` is a full account-level replacement, not a domain
    patch. This read surface returns only ``selected_markets`` from the current
    user record so callers can show an exact before/after diff.
    """
    result, err = _safe(client.get, "/api/user")
    if err:
        return f"# Failed to get current markets\n\n```\n{err}\n```"
    selected = result.get("selected_markets", []) if isinstance(result, dict) else []
    return _json_block("Current target markets", {"selected_markets": selected or []})


@mcp.tool(title="Update target markets", annotations=WRITE)
def aeko_update_markets(markets: list[str]) -> str:
    """Replace the account's selected target markets.

    This is account-wide and replaces the full list; call
    ``aeko_get_current_markets`` and show the exact diff first. Starter can
    select one supported market; Pro/Enterprise can select more according to
    backend package limits.
    """
    if not markets:
        return "# No markets provided — pass at least one country code."
    result, err = _safe(client.put, "/api/user/markets", json={"markets": markets})
    if err:
        return f"# Failed to update markets\n\n```\n{err}\n```"
    return _json_block("Markets updated", result)
