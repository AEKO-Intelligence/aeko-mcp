"""Action-item / Plan.md tools.

These wrap the backend's action-items endpoints so executor skills
(`/aeko-update-pdp`, `/aeko-create-content`, `/aeko-fix-technical`) can
fetch a Plan.md, execute it, and report completion. The Plan.md payload
is YAML frontmatter + templated prose body — the skill parses both.

Contract reference: `docs/contracts/action-item-contract.md`.
"""
from typing import Any, List, Optional

from ..server import mcp, client
from ._annotations import READ_ONLY, WRITE


def _render_item_summary(item: dict, index: int | None = None) -> list[str]:
    """Compact one-item block for the list view."""
    lines: list[str] = []
    title = item.get("title") or "(untitled)"
    prefix = f"{index}. " if index is not None else ""
    lines.append(f"### {prefix}{title}")
    header_bits: list[str] = []
    artifact_type = item.get("artifact_type")
    priority = item.get("priority")
    status = item.get("status")
    if artifact_type:
        header_bits.append(f"`{artifact_type}`")
    if priority:
        header_bits.append(str(priority))
    if status:
        header_bits.append(str(status))
    if header_bits:
        lines.append(f"- {' · '.join(header_bits)}")
    item_id = item.get("id")
    if item_id:
        lines.append(f"- **item_id**: `{item_id}`")
    execution_class = item.get("execution_class")
    write_mode = item.get("write_mode")
    meta_bits: list[str] = []
    if execution_class:
        meta_bits.append(f"execution: {execution_class}")
    if write_mode:
        meta_bits.append(f"write_mode: {write_mode}")
    if meta_bits:
        lines.append(f"- {' | '.join(meta_bits)}")
    target_url = item.get("target_url")
    product_id = item.get("product_id")
    if target_url:
        lines.append(f"- **Target**: {target_url}")
    elif product_id:
        lines.append(f"- **Product**: `{product_id}`")
    preview = item.get("preview")
    if preview:
        trimmed = preview if len(preview) <= 160 else preview[:157] + "..."
        lines.append(f"- {trimmed}")
    if item_id:
        executor_by_class = {
            "store_write_artifact": "/aeko-update-pdp",
            "local_content_artifact": "/aeko-create-content",
            "technical_artifact": "/aeko-fix-technical",
        }
        hint = executor_by_class.get(execution_class or "", "/aeko-action-center")
        lines.append(f"- Run: `{hint} {item_id}`")
    lines.append("")
    return lines


def _list_items(
    tab: str,
    domain_id: Optional[str],
    status: Optional[str],
    limit: int,
    offset: int,
) -> str:
    params: dict[str, Any] = {"tab": tab, "limit": limit, "offset": offset}
    if domain_id is not None:
        params["domain_id"] = domain_id
    if status is not None:
        params["status"] = status
    resp = client.get("/api/action-items", params=params)
    items: list[dict] = resp.get("items") or []
    total = resp.get("total", len(items))

    tab_label = tab.capitalize()
    if not items:
        scope = f" in domain `{domain_id}`" if domain_id else ""
        status_note = f" with status=`{status}`" if status else ""
        return (
            f"# {tab_label} items\n\n"
            f"No pending {tab} items{scope}{status_note}. "
            f"Check back after the next suggestion scan, or explore other tabs."
        )

    lines: list[str] = [f"# {tab_label} items ({len(items)} of {total})"]
    if domain_id:
        lines.append(f"- Domain: `{domain_id}`")
    if status:
        lines.append(f"- Status filter: `{status}`")
    lines.append("")
    for idx, item in enumerate(items, start=1):
        lines.extend(_render_item_summary(item, index=idx))
    if total > len(items):
        hidden = total - len(items)
        lines.append(f"_{hidden} more not shown — increase `limit` or page with `offset`._")
    return "\n".join(lines)


@mcp.tool(title="List action items", annotations=READ_ONLY)
def aeko_list_action_items(
    domain_id: Optional[str] = None,
    status: Optional[str] = "pending,ready",
    limit: int = 50,
    offset: int = 0,
) -> str:
    """List pending Action-tab items for a domain.

    Action items are the user-facing optimization tasks (PDP rewrites, content
    drafts, external-media placements) that `/aeko-action-center` dispatches
    to the right executor based on `execution_class` — `/aeko-update-pdp` for
    store writes, `/aeko-create-content` for local content artifacts. Each
    item carries a title, priority, artifact_type, execution_class,
    write_mode, and a short `preview` snippet of its Plan.md prose.

    Returns a markdown list with a ready-to-copy executor command under each
    item so the user (or Claude) can pick one and run it directly.

    Args:
        domain_id: UUID string of the domain to scope results. Omit to list
            across all the caller's domains.
        status: Comma-separated status filter. Defaults to `pending,ready` —
            the states that mean "executable now". Pass `completed` to see
            history, or `dismissed` for the archive. Pass an explicit list
            (e.g. `pending,ready,completed`) to combine.
        limit: Max items to return (1-200). Defaults to 50.
        offset: Pagination offset. Defaults to 0.
    """
    return _list_items("action", domain_id, status, limit, offset)


@mcp.tool(title="List technical items", annotations=READ_ONLY)
def aeko_list_technical_items(
    domain_id: Optional[str] = None,
    status: Optional[str] = "pending,ready",
    limit: int = 50,
    offset: int = 0,
) -> str:
    """List pending Technical-tab items for a domain.

    Technical items are infrastructure-level AEO fixes (llms.txt, robots.txt,
    site-level JSON-LD, canonical tags, sitemap coverage). `/aeko-action-center`
    dispatches these to `/aeko-fix-technical <item_id>`.

    Args:
        domain_id: UUID string of the domain to scope results. Omit to list
            across all the caller's domains.
        status: Comma-separated status filter. Defaults to `pending,ready`.
            Pass `completed` for history, `dismissed` for the archive.
        limit: Max items to return (1-200). Defaults to 50.
        offset: Pagination offset. Defaults to 0.
    """
    return _list_items("technical", domain_id, status, limit, offset)


@mcp.tool(title="Get action plan (Plan.md)", annotations=READ_ONLY)
def aeko_get_action_plan(item_id: str) -> str:
    """Fetch the Plan.md for one Action or Technical item.

    Returns a single markdown string: YAML frontmatter between `---` fences,
    followed by the templated prose body. Consumers parse frontmatter for
    machine values (execution_class, write_mode, target_url, etc.) and treat
    prose as narrative guidance. Shared endpoint — serves both Action-tab and
    Technical-tab items. Normally called by the executor skills
    (`/aeko-update-pdp`, `/aeko-create-content`, `/aeko-fix-technical`) but
    safe to call standalone to inspect an item's contract.

    Status gate: backend 409s if the item is not in {ready, completed}. The
    409 body is plain text like "Plan is still being generated — retry in a
    moment" — surface it to the user verbatim.

    Args:
        item_id: The `itm_<hex>` identifier.
    """
    return client.get_text(f"/api/action-items/{item_id}", accept="text/markdown")


@mcp.tool(title="Complete action item", annotations=WRITE)
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
