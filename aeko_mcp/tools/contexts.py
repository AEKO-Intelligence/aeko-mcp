"""MCP tools for reading and writing curated AEKO Context memories.

Contexts are source-backed memories saved in the AEKO dashboard. Unlike raw
review rows, these are deliberately curated by the user and can be reused to
ground tracked prompts and content plans.
"""
import json
from typing import Any, Optional

from ..server import mcp, client
from ._annotations import DESTRUCTIVE, READ_ONLY, WRITE, WRITE_ONCE


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


@mcp.tool(title="Update AEKO context", annotations=DESTRUCTIVE)
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
    review-derived contexts. The backend does not let PATCH create that field on
    a Context that lacks it. ``status=archived`` is refused here; use
    ``aeko_archive_context`` so archival cannot bypass its dedicated skill gate.
    """
    if status == "archived":
        return (
            "# Context update refused\n\n"
            "`status=archived` must use `aeko_archive_context` and its separate "
            "typed confirmation gate."
        )

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


@mcp.tool(title="Archive AEKO context", annotations=WRITE)
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


def _normalize_market(market: str) -> str:
    return (market or "").strip().upper()


def _market_refusal(market: str) -> Optional[str]:
    normalized = _normalize_market(market)
    if not 2 <= len(normalized) <= 8:
        return "# `market` must contain 2 to 8 characters."
    return None


def _opportunity_table(title: str, items: Any) -> list[str]:
    rows = items if isinstance(items, list) else []
    lines = [
        f"## {title} ({len(rows)})",
        "",
        "| Context | State | Market | Opportunity | Confidence | Stage | Recommendation / next action | Reason codes |",
        "|---|---|---|---:|---|---|---|---|",
    ]
    if not rows:
        lines.append("| None | — | — | — | — | — | — | — |")
        return lines

    for raw_item in rows:
        item = raw_item if isinstance(raw_item, dict) else {}
        context_id = item.get("context_id", "?")
        context_title = _clean(item.get("title")) or "(untitled Context)"
        state = _clean(item.get("state")) or "unknown"
        rollup = item.get("rollup") if isinstance(item.get("rollup"), dict) else {}
        market = (
            _clean(rollup.get("market"))
            or _clean(item.get("headline_market"))
            or "—"
        )
        score = rollup.get("opportunity_score")
        score_text = "—" if score is None else str(score)
        confidence = rollup.get("confidence")
        if isinstance(confidence, dict):
            confidence = confidence.get("label") or confidence.get("score")
        confidence_text = _clean(confidence) or "—"
        stage = _clean(rollup.get("measurement_stage")) or "—"

        recommendation = (
            item.get("recommendation")
            if isinstance(item.get("recommendation"), dict)
            else {}
        )
        recommendation_type = _clean(recommendation.get("type"))
        next_action = (
            recommendation.get("next_action")
            if isinstance(recommendation.get("next_action"), dict)
            else {}
        )
        action_type = _clean(next_action.get("type"))
        action_label = _clean(next_action.get("label"))
        action_bits = [bit for bit in (recommendation_type, action_type, action_label) if bit]
        action_text = " → ".join(dict.fromkeys(action_bits)) if action_bits else "—"
        reason_codes = recommendation.get("reason_codes")
        if not isinstance(reason_codes, list):
            reason_codes = []
        reasons_text = ", ".join(str(code) for code in reason_codes) or "—"

        lines.append(
            f"| `{context_id}` {context_title} | {state} | {market} | {score_text} | "
            f"{confidence_text} | {stage} | {action_text} | {reasons_text} |"
        )
    return lines


def _format_context_opportunities(domain_id: str, result: dict[str, Any]) -> str:
    quota = result.get("focus_quota")
    if not isinstance(quota, dict):
        quota = {}
    used = quota.get("used", 0)
    limit = quota.get("limit", 5)
    lines = [
        "# Context opportunities",
        "",
        f"- **Domain ID**: `{domain_id}`",
        f"- **Focus quota**: {used} of {limit} used",
    ]
    for title, field in (
        ("Focused", "focused"),
        ("Recommended", "recommended"),
        ("All Contexts", "contexts"),
    ):
        lines.extend(["", *_opportunity_table(title, result.get(field))])
    return "\n".join(lines)


@mcp.tool(title="List Context opportunities", annotations=READ_ONLY)
def aeko_list_context_opportunities(
    domain_id: str,
    market: Optional[str] = None,
) -> str:
    """Rank saved Contexts by opportunity and show Focus recommendations.

    The Markdown decision surface includes Focus quota and the backend's
    measured score, confidence, stage, recommendation, next action, and reason
    codes. Read-only. Pro+ is enforced server-side.
    """
    params = {"domain_id": domain_id}
    if market is not None:
        refusal = _market_refusal(market)
        if refusal:
            return refusal
        params["market"] = _normalize_market(market)
    result, err = _safe(client.get, "/api/contexts/opportunities", params=params)
    if err:
        return f"# Failed to list Context opportunities\n\n```\n{err}\n```"
    payload = result if isinstance(result, dict) else {}
    return _format_context_opportunities(domain_id, payload)


@mcp.tool(title="Get Context metrics", annotations=READ_ONLY)
def aeko_get_context_metrics(
    context_id: str,
    market: Optional[str] = None,
) -> str:
    """Read the stored opportunity-detail payload for one Context.

    Returns the rollup, Focus period, recommendation, and stored rendering as
    JSON for later tool calls. Read-only. Pro+ is enforced server-side.
    """
    params: dict[str, Any] = {}
    if market is not None:
        refusal = _market_refusal(market)
        if refusal:
            return refusal
        params["market"] = _normalize_market(market)
    result, err = _safe(
        client.get,
        f"/api/contexts/{context_id}/metrics",
        params=params,
    )
    if err:
        return f"# Failed to get Context metrics\n\n```\n{err}\n```"
    return _json_block("Context metrics", result)


@mcp.tool(title="List focused Contexts", annotations=READ_ONLY)
def aeko_list_focused_contexts(domain_id: str, market: str) -> str:
    """List open Focus periods for one domain and market.

    Read-only. Pro+ is enforced server-side.
    """
    refusal = _market_refusal(market)
    if refusal:
        return refusal
    normalized_market = _normalize_market(market)
    result, err = _safe(
        client.get,
        "/api/contexts/focus",
        params={"domain_id": domain_id, "market": normalized_market},
    )
    if err:
        return f"# Failed to list focused Contexts\n\n```\n{err}\n```"
    return _json_block(f"Focused Contexts ({normalized_market})", result)


@mcp.tool(title="Focus Context", annotations=WRITE_ONCE)
def aeko_focus_context(
    context_id: str,
    market: str,
    objective: str,
    slot_number: Optional[int] = None,
    reason: Optional[str] = None,
) -> str:
    """Claim a scarce Focus slot for one saved Context and market.

    ``objective`` must be ``organic``, ``paid``, or ``both``. Do not retry a
    ``focus_slots_full`` conflict or auto-pick a different slot; show the
    returned occupants and ask the user what to unfocus. Pro+ is enforced
    server-side, and this write requires an active subscription.
    """
    refusal = _market_refusal(market)
    if refusal:
        return refusal
    normalized_objective = (objective or "").strip().lower()
    if normalized_objective not in {"organic", "paid", "both"}:
        return "# `objective` must be `organic`, `paid`, or `both`."
    if slot_number is not None and not 1 <= int(slot_number) <= 5:
        return "# `slot_number` must be between 1 and 5."
    if reason is not None and len(reason) > 2000:
        return "# `reason` must be at most 2000 characters."

    body: dict[str, Any] = {
        "market": _normalize_market(market),
        "objective": normalized_objective,
    }
    if slot_number is not None:
        body["slot_number"] = int(slot_number)
    if reason is not None:
        body["reason"] = reason
    result, err = _safe(
        client.post,
        f"/api/contexts/{context_id}/focus",
        json=body,
    )
    if err:
        recovery = ""
        if "focus_slots_full" in err or "CONTEXT_FOCUS_CAP_REACHED" in err:
            recovery = (
                "\n\nReview the returned focused Contexts with the user. Unfocus one "
                "before retrying if all slots are full; do not retry or choose a slot automatically."
            )
        return f"# Failed to focus Context\n\n```\n{err}\n```{recovery}"
    return _json_block("Context focused", result)


@mcp.tool(title="Unfocus Context", annotations=DESTRUCTIVE)
def aeko_unfocus_context(context_id: str, market: str, end_reason: str) -> str:
    """End one Context's open Focus measurement period.

    This is destructive because the stored baseline period cannot be reopened;
    a later focus starts a new period. Pro+ is enforced server-side, and this
    write requires an active subscription.
    """
    refusal = _market_refusal(market)
    if refusal:
        return refusal
    normalized_reason = (end_reason or "").strip()
    if not normalized_reason:
        return "# `end_reason` must be a non-empty string."
    if len(normalized_reason) > 2000:
        return "# `end_reason` must be at most 2000 characters."
    result, err = _safe(
        client.post,
        f"/api/contexts/{context_id}/unfocus",
        json={
            "market": _normalize_market(market),
            "end_reason": normalized_reason,
        },
    )
    if err:
        return f"# Failed to unfocus Context\n\n```\n{err}\n```"
    return _json_block("Context unfocused", result)


@mcp.tool(title="Update Context translation", annotations=WRITE)
def aeko_update_context_translation(
    context_id: str,
    language: str,
    text: str,
) -> str:
    """Replace one stored language rendering for a Context.

    The backend marks the rendering source as ``edited`` and returns the full
    translations map. Pro+ is enforced server-side, and this write requires
    an active subscription.
    """
    normalized_language = (language or "").strip().lower().replace("_", "-")
    if not 2 <= len(normalized_language) <= 16:
        return "# `language` must contain 2 to 16 characters."
    normalized_text = (text or "").strip()
    if not normalized_text:
        return "# `text` must be a non-empty string."
    result, err = _safe(
        client.put,
        f"/api/contexts/{context_id}/translations",
        json={"language": normalized_language, "text": normalized_text},
    )
    if err:
        return f"# Failed to update Context translation\n\n```\n{err}\n```"
    return _json_block("Context translation updated", result)
