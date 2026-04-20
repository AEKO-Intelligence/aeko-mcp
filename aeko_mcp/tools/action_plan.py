"""Action-item / Plan.md tools.

These wrap the backend's action-items endpoints so the `aeko-run-action`
skill can fetch a Plan.md, execute it, and report completion. The Plan.md
payload is YAML frontmatter + prose body — the skill parses both.

Contract reference: `docs/contracts/action-item-contract.md`.
"""
from typing import Any, List, Optional

from ..server import mcp, client


@mcp.tool()
def aeko_get_action_plan(item_id: str) -> str:
    """Fetch a Plan.md for one action item.

    Returns a single markdown string: YAML frontmatter between `---` fences,
    followed by the prose body. Consumers parse frontmatter for machine values
    and treat prose as narrative guidance.

    Status gate: backend 409s if the item is not in {ready, completed}. The
    409 body is plain text like "Plan is still being generated — retry in a
    moment" — surface it to the user verbatim.

    Args:
        item_id: The `itm_<hex>` identifier.
    """
    return client.get_text(f"/api/action-items/{item_id}", accept="text/markdown")


@mcp.tool()
def aeko_complete_action_item(
    item_id: str,
    artifact_summary: Optional[str] = None,
    artifact_paths: Optional[List[str]] = None,
    write_result: Optional[dict] = None,
) -> str:
    """Mark an action item as completed after producing its artifact.

    Idempotent: completing an already-completed item is a no-op that returns
    the existing completed_at.

    Args:
        item_id: The `itm_<hex>` identifier.
        artifact_summary: One-line human summary ("shadow draft created",
            "PDP HTML saved to ./aeko-artifacts/...").
        artifact_paths: Absolute paths of any files written to disk.
        write_result: Optional dict describing store writes, e.g.
            {"mode": "shadow_product", "audit_id": "...", "admin_url": "...",
             "created_product_id": "..."}. Set to None for preview-only /
             local content runs.
    """
    body: dict[str, Any] = {}
    if artifact_summary is not None:
        body["artifact_summary"] = artifact_summary
    if artifact_paths is not None:
        body["artifact_paths"] = artifact_paths
    if write_result is not None:
        body["write_result"] = write_result

    resp = client.post(f"/api/items/{item_id}/complete", json=body)
    status = resp.get("status", "ok")
    completed_at = resp.get("completed_at", "")
    return f"Item {item_id} marked {status} at {completed_at}."
