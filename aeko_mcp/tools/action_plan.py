"""Action-item / Plan.md tools.

These wrap the backend's action-items endpoints so executor skills
(`/aeko-update-pdp`, `/aeko-create-content`, `/aeko-fix-technical`) can
fetch a Plan.md, execute it, and report completion. The Plan.md payload
is YAML frontmatter + templated prose body — the skill parses both.

Contract reference: `docs/contracts/action-item-contract.md`.
"""
import json
from typing import Any, List, Optional

from ..server import mcp, client
from ._annotations import DESTRUCTIVE, READ_ONLY, WRITE, WRITE_ONCE


def _json_block(title: str, payload: Any) -> str:
    return f"# {title}\n\n```json\n{json.dumps(payload, ensure_ascii=False, indent=2, default=str)}\n```"


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
    # Keep product_id visible even when target_url is also populated. Direct
    # PDP execution uses this exact field to deduplicate work for a product.
    if product_id:
        lines.append(f"- **Product**: `{product_id}`")
    created_at = item.get("created_at")
    if created_at:
        lines.append(f"- **Created**: {created_at}")
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

    start = offset + 1
    end = offset + len(items)
    has_more = end < total
    lines: list[str] = [f"# {tab_label} items ({start}-{end} of {total})"]
    lines.append(
        f"- Pagination: `offset={offset}` · `limit={limit}` · "
        f"`has_more={'true' if has_more else 'false'}`"
    )
    if domain_id:
        lines.append(f"- Domain: `{domain_id}`")
    if status:
        lines.append(f"- Status filter: `{status}`")
    lines.append("")
    for idx, item in enumerate(items, start=1):
        lines.extend(_render_item_summary(item, index=idx))
    if has_more:
        remaining = total - end
        lines.append(
            f"_{remaining} more not shown — request the next page with `offset={end}`._"
        )
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

    Status gate: backend serves executable ``ready`` plans and completed history.
    A successful execution claim is stored separately and does not change the
    item's status. Other states return 409; surface the backend message verbatim.

    Args:
        item_id: The `itm_<hex>` identifier.
    """
    return client.get_text(f"/api/action-items/{item_id}", accept="text/markdown")


@mcp.tool(title="Claim action item execution", annotations=WRITE_ONCE)
def aeko_claim_action_item(item_id: str) -> str:
    """Atomically claim one ready ActionItem before generating its artifact.

    The backend creates an owner-scoped execution-claim row while the item stays
    ``ready``. Exactly one concurrent host can win. A second host receives 409
    and must stop without generating or writing anything.

    Args:
        item_id: The ``itm_<hex>`` identifier to claim.
    """
    result = client.post(f"/api/action-items/{item_id}/claim")
    return _json_block("Action item claimed", result)


@mcp.tool(title="Release action item execution", annotations=WRITE)
def aeko_release_action_item(
    item_id: str,
    claim_id: str | None = None,
    force: bool = False,
    confirm_no_active_execution: bool = False,
) -> str:
    """Release an uncompleted claim after an execution aborts.

    Normal release is fenced by the unique ``claim_id`` returned from
    ``aeko_claim_action_item``. ``force=True`` is recovery-only: use it only
    after the user explicitly confirms that no other run is active and no
    store mutation occurred. The item remains ``ready`` until completion.
    Never release after a store write succeeds or may have succeeded; complete
    the item with its audit result instead.

    Args:
        item_id: The ``itm_<hex>`` identifier whose claim should be released.
        claim_id: Unique token returned by ``aeko_claim_action_item``. Required
            for a normal release.
        force: Owner-scoped stale-claim recovery. This is not an automatic
            timeout and must follow explicit user confirmation.
        confirm_no_active_execution: Required alongside ``force=True``. Set
            only after the user confirms that no other execution is active
            and no store mutation occurred.
    """
    body: dict[str, Any] = {
        "force": force,
        "confirm_no_active_execution": confirm_no_active_execution,
    }
    if claim_id is not None:
        body["claim_id"] = claim_id
    result = client.post(f"/api/action-items/{item_id}/release", json=body)
    return _json_block("Action item released", result)


@mcp.tool(title="Create action item", annotations=WRITE_ONCE)
def aeko_create_action_item(
    domain_id: str,
    artifact_type: str,
    idempotency_key: str,
    tab: Optional[str] = None,
    product_id: Optional[str] = None,
    target_url: Optional[str] = None,
    prompt_ids: Optional[list[str]] = None,
    keywords: Optional[list[str]] = None,
    must_include: Optional[list[str]] = None,
    forbidden: Optional[list[str]] = None,
    target_country: Optional[str] = None,
    target_language: Optional[str] = None,
    content_channel: Optional[str] = None,
    content_topic: Optional[str] = None,
    content_scope: Optional[str] = None,
    selected_product_ids: Optional[list[str]] = None,
    context_ids: Optional[list[str]] = None,
    additional_instructions: Optional[str] = None,
) -> str:
    """Create a backend action item and enqueue Plan.md generation.

    Pass a stable `idempotency_key` such as `domain:type:target` so agent
    retries return the existing row instead of minting duplicate action items.
    """
    if not idempotency_key.strip():
        return "`idempotency_key` is required for retry-safe action-item creation."

    fields: dict[str, Any] = {
        "domain_id": domain_id,
        "artifact_type": artifact_type,
        "tab": tab,
        "product_id": product_id,
        "target_url": target_url,
        "prompt_ids": prompt_ids,
        "keywords": keywords,
        "must_include": must_include,
        "forbidden": forbidden,
        "target_country": target_country,
        "target_language": target_language,
        "content_channel": content_channel,
        "content_topic": content_topic,
        "content_scope": content_scope,
        "selected_product_ids": selected_product_ids,
        "context_ids": context_ids,
        "additional_instructions": additional_instructions,
    }
    payload = {k: v for k, v in fields.items() if v is not None}
    result = client.post(
        "/api/action-items",
        json=payload,
        headers={"Idempotency-Key": idempotency_key},
    )
    return _json_block("Action item created", result)


@mcp.tool(title="Dismiss action item", annotations=DESTRUCTIVE)
def aeko_dismiss_action_item(item_id: str) -> str:
    """Dismiss/archive an action or technical item by id."""
    client.delete(f"/api/action-items/{item_id}")
    return f"Action item `{item_id}` dismissed."


@mcp.tool(title="Complete action item", annotations=WRITE)
def aeko_complete_action_item(
    item_id: str,
    artifact_summary: Optional[str] = None,
    artifact_paths: Optional[List[str]] = None,
    write_result: Optional[dict] = None,
    execution_claim_id: Optional[str] = None,
) -> str:
    """Mark an action item as completed after producing its artifact.

    Idempotent: completing an already-completed item is a no-op that returns
    the existing completed_at.

    Args:
        item_id: The `itm_<hex>` identifier.
        artifact_summary: One-line human summary ("PDP preview generated",
            "PDP HTML saved to ./aeko-artifacts/...").
        artifact_paths: Absolute paths of any files written to disk.
        write_result: Optional dict describing store writes, e.g.
            {"mode": "current_product", "audit_id": "...", "admin_url": "..."}
            or {"mode": "private_draft", "draft_id": "..."}. Preview-only PDP
            runs can pass {"mode": "preview_only"}; local content may use None.
        execution_claim_id: Unique token returned by
            ``aeko_claim_action_item``. Required when the item has an active
            execution claim; it fences completion to the winning run.
    """
    body: dict[str, Any] = {}
    if artifact_summary is not None:
        body["artifact_summary"] = artifact_summary
    if artifact_paths is not None:
        body["artifact_paths"] = artifact_paths
    if write_result is not None:
        body["write_result"] = write_result
    if execution_claim_id is not None:
        body["execution_claim_id"] = execution_claim_id

    resp = client.post(f"/api/items/{item_id}/complete", json=body)
    status = resp.get("status", "ok")
    completed_at = resp.get("completed_at", "")
    return f"Item {item_id} marked {status} at {completed_at}."
