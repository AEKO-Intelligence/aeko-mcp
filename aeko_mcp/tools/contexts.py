"""MCP tools for reading and writing curated AEKO Context memories.

Contexts are source-backed memories saved in the AEKO dashboard. Unlike raw
review rows, these are deliberately curated by the user and can be reused to
ground tracked prompts and content plans.
"""
import json
from typing import Any, Optional

from ..server import mcp, client
from ._annotations import DESTRUCTIVE, READ_ONLY, WRITE


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


def _json_block(title: str, payload: Any) -> str:
    return f"# {title}\n\n```json\n{json.dumps(payload, ensure_ascii=False, indent=2, default=str)}\n```"


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
            "Save review-derived or manual Context memories in the AEKO Context tab, "
            "then call this tool again. Context memory is a Pro+ feature."
        )

    lines = [f"# Saved AEKO contexts ({len(items)})", ""]
    for idx, item in enumerate(items, start=1):
        context_id = item.get("id", "?")
        title = item.get("title") or "(untitled context)"
        summary = _clean(item.get("summary"))
        context_for_prompt = _clean(item.get("context_for_prompt"))
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
        if context_for_prompt:
            lines.append("- **프롬프트 컨텍스트**:")
            lines.extend(f"  > {line}" for line in context_for_prompt.splitlines())
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


@mcp.tool(title="Create AEKO context", annotations=WRITE)
def aeko_create_context(
    domain_id: str,
    title: str,
    problem: Optional[str] = None,
    solution: Optional[str] = None,
    outcome: Optional[str] = None,
    customer_state: Optional[str] = None,
    recent_concern: Optional[str] = None,
    product_experience: Optional[str] = None,
    felt_effect: Optional[str] = None,
    occasion: Optional[str] = None,
    recipient: Optional[str] = None,
    evidence: Optional[str] = None,
    summary: Optional[str] = None,
    kind: Optional[str] = None,
    scope: Optional[str] = None,
    category_ref: Optional[str] = None,
    context_type: Optional[str] = None,
    lang: Optional[str] = None,
    source_review_id: Optional[str] = None,
    source_review_snapshot: Optional[dict] = None,
    product_external_ref: Optional[str] = None,
) -> str:
    """Save a curated Context memory for a domain.

    Context is a Pro+ feature. This creates a user-curated memory (`curated=true`)
    that can later be attached to prompts via `context_ids`.
    """
    body: dict[str, Any] = {
        "domain_id": domain_id,
        "title": title,
    }
    optional = {
        "problem": problem,
        "solution": solution,
        "outcome": outcome,
        "customer_state": customer_state,
        "recent_concern": recent_concern,
        "product_experience": product_experience,
        "felt_effect": felt_effect,
        "occasion": occasion,
        "recipient": recipient,
        "evidence": evidence,
        "summary": summary,
        "kind": kind,
        "scope": scope,
        "category_ref": category_ref,
        "context_type": context_type,
        "lang": lang,
        "source_review_id": source_review_id,
        "source_review_snapshot": source_review_snapshot,
        "product_external_ref": product_external_ref,
    }
    body.update({k: v for k, v in optional.items() if v is not None})
    body["source"] = "review" if source_review_id else "manual"
    body["curated"] = True

    result, err = _safe(client.post, "/api/contexts", json=body)
    if err:
        return f"# Failed to create context\n\n```\n{err}\n```"
    return _json_block("Context created", result)


@mcp.tool(title="Update AEKO context", annotations=WRITE)
def aeko_update_context(
    context_id: str,
    title: Optional[str] = None,
    context_for_prompt: Optional[str] = None,
    problem: Optional[str] = None,
    solution: Optional[str] = None,
    outcome: Optional[str] = None,
    customer_state: Optional[str] = None,
    recent_concern: Optional[str] = None,
    product_experience: Optional[str] = None,
    felt_effect: Optional[str] = None,
    occasion: Optional[str] = None,
    recipient: Optional[str] = None,
    evidence: Optional[str] = None,
    summary: Optional[str] = None,
    kind: Optional[str] = None,
    scope: Optional[str] = None,
    category_ref: Optional[str] = None,
    curated: Optional[bool] = None,
    context_type: Optional[str] = None,
    lang: Optional[str] = None,
    status: Optional[str] = None,
) -> str:
    """Update a curated Context memory. Omitted fields are left unchanged.

    ``context_for_prompt`` is the authoritative grounding text for converted and
    review-derived contexts. Update that field when changing what prompt tracking
    should inject; changing only ``summary`` does not override it.
    """
    body = {
        "title": title,
        "context_for_prompt": context_for_prompt,
        "problem": problem,
        "solution": solution,
        "outcome": outcome,
        "customer_state": customer_state,
        "recent_concern": recent_concern,
        "product_experience": product_experience,
        "felt_effect": felt_effect,
        "occasion": occasion,
        "recipient": recipient,
        "evidence": evidence,
        "summary": summary,
        "kind": kind,
        "scope": scope,
        "category_ref": category_ref,
        "curated": curated,
        "context_type": context_type,
        "lang": lang,
        "status": status,
    }
    payload = {k: v for k, v in body.items() if v is not None}
    if not payload:
        return "# No context updates provided."

    result, err = _safe(client.patch, f"/api/contexts/{context_id}", json=payload)
    if err:
        return f"# Failed to update context\n\n```\n{err}\n```"
    return _json_block("Context updated", result)


@mcp.tool(title="Archive AEKO context", annotations=DESTRUCTIVE)
def aeko_archive_context(context_id: str) -> str:
    """Soft-archive a Context memory.

    The backend keeps historical tracked-prompt references intact; this removes
    the Context from active library listings.
    """
    result, err = _safe(client.delete, f"/api/contexts/{context_id}")
    if err:
        return f"# Failed to archive context\n\n```\n{err}\n```"
    return _json_block("Context archived", result)


@mcp.tool(title="Create contexts from reviews", annotations=WRITE)
def aeko_create_contexts_from_reviews(
    domain_id: str,
    integration_id: str,
    min_context_score: int = 60,
    review_ids: Optional[list[str]] = None,
) -> str:
    """Save Context-tab review selections as curated Context memories.

    The backend resolves the filtered review set, promotes existing grounding
    contexts when possible, and creates one curated memory per review.
    """
    body: dict[str, Any] = {
        "domain_id": domain_id,
        "integration_id": integration_id,
        "min_context_score": max(0, min(int(min_context_score), 100)),
    }
    if review_ids is not None:
        body["review_ids"] = review_ids

    result, err = _safe(client.post, "/api/contexts/from-reviews", json=body)
    if err:
        return f"# Failed to create contexts from reviews\n\n```\n{err}\n```"
    return _json_block("Contexts created from reviews", result)
