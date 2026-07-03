"""MCP tools for reading curated AEKO Context memories.

Contexts are source-backed memories saved in the AEKO dashboard. Unlike raw
review rows, these are deliberately curated by the user and can be reused to
ground tracked prompts and content plans. This module is read-only; creating or
editing memories stays in the AEKO app.
"""
from typing import Any, Optional

from ..server import mcp, client
from ._annotations import READ_ONLY


def _safe(method, *args, **kwargs) -> tuple[Any, Optional[str]]:
    """Wrap client errors into ``(None, message)`` for graceful tool output."""
    try:
        return method(*args, **kwargs), None
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


def _clean(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


@mcp.tool(title="List saved AEKO contexts", annotations=READ_ONLY)
def aeko_list_contexts(
    domain_id: str,
    scope: Optional[str] = None,
    kind: Optional[str] = None,
) -> str:
    """List curated AEKO Context memories for a domain.

    Use this from content-generation skills when the user wants drafts grounded
    in saved brand/customer memory. The backend returns curated memories only;
    this tool additionally accepts optional ``scope`` and ``kind`` filters for
    the review-context memory model.

    Returned memories may include flexible facets:
    ``고객 상태`` (customer_state), ``최근 고민`` (recent_concern), ``제품 경험``
    (product_experience), and ``느낀 효과`` (felt_effect). Legacy
    problem/solution/outcome fields are rendered only as fallback when a memory
    has not yet been migrated to facets.

    Read-only. Pro+ is enforced server-side.

    Args:
        domain_id: UUID of the AEKO domain whose saved contexts you want.
        scope: Optional filter: ``brand``, ``product``, or ``category``.
        kind: Optional free-text memory-type filter, e.g. ``브랜드 충성도``,
            ``재구매``, ``피부 고민``, or ``content angle``.
    """
    params = {
        "domain_id": domain_id,
        "status": "active",
        "curated": "true",
    }
    if scope:
        params["scope"] = scope
    if kind:
        params["kind"] = kind

    result, err = _safe(client.get, "/api/contexts", params=params)
    if err:
        return f"# Failed to list contexts\n\n```\n{err}\n```"

    items = result if isinstance(result, list) else []
    if not items:
        filter_bits = []
        if scope:
            filter_bits.append(f"scope={scope}")
        if kind:
            filter_bits.append(f"kind={kind}")
        filter_text = f" matching `{', '.join(filter_bits)}`" if filter_bits else ""
        return (
            f"# No saved contexts for domain `{domain_id}`{filter_text}\n\n"
            "Save review-derived or manual Context memories in AEKO Brand Settings, "
            "then call this tool again. Context memory is a Pro+ feature."
        )

    lines = [f"# Saved AEKO contexts ({len(items)})", ""]
    for idx, item in enumerate(items, start=1):
        context_id = item.get("id", "?")
        title = item.get("title") or "(untitled context)"
        summary = _clean(item.get("summary"))
        item_kind = _clean(item.get("kind"))
        item_scope = _clean(item.get("scope"))
        category_ref = _clean(item.get("category_ref"))
        product_ref = _clean(item.get("product_external_ref"))
        source_review_id = _clean(item.get("source_review_id"))

        header = f"## {idx}. {title}"
        badges = [bit for bit in (item_kind, item_scope) if bit]
        if badges:
            header += f" · {' / '.join(badges)}"
        lines.append(header)
        lines.append(f"- **context_id**: `{context_id}`")
        if summary:
            lines.append(f"- **요약**: {summary}")

        customer_state = _clean(item.get("customer_state"))
        recent_concern = _clean(item.get("recent_concern"))
        occasion = _clean(item.get("occasion"))
        recipient = _clean(item.get("recipient"))
        product_experience = _clean(item.get("product_experience"))
        felt_effect = _clean(item.get("felt_effect"))

        if customer_state:
            lines.append(f"- **고객 상태**: {customer_state}")
        if recent_concern:
            lines.append(f"- **최근 고민**: {recent_concern}")
        if occasion:
            lines.append(f"- **상황**: {occasion}")
        if recipient:
            lines.append(f"- **대상**: {recipient}")
        if product_experience:
            lines.append(f"- **제품 경험**: {product_experience}")
        if felt_effect:
            lines.append(f"- **느낀 효과**: {felt_effect}")

        # Legacy fallback for rows created before the memory facets shipped.
        if not any((customer_state, recent_concern, occasion, recipient, product_experience, felt_effect)):
            problem = _clean(item.get("problem"))
            solution = _clean(item.get("solution"))
            outcome = _clean(item.get("outcome"))
            if problem:
                lines.append(f"- **문제**: {problem}")
            if solution:
                lines.append(f"- **해결**: {solution}")
            if outcome:
                lines.append(f"- **결과**: {outcome}")

        if category_ref:
            lines.append(f"- **category_ref**: `{category_ref}`")
        if product_ref:
            lines.append(f"- **product_external_ref**: `{product_ref}`")
        if source_review_id:
            lines.append(f"- **source_review_id**: `{source_review_id}`")
        if item.get("created_at"):
            lines.append(f"- **created_at**: {item['created_at']}")
        lines.append("")

    lines.append(
        "Use these saved memories as grounding context for prompts and content plans. "
        "They are curated AEKO Context rows, not raw review rows."
    )
    return "\n".join(lines)
