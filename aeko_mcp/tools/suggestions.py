from ..server import mcp, client
from ._annotations import READ_ONLY, WRITE


def _format_suggestions(data: dict) -> str:
    suggestions = data if isinstance(data, list) else data.get("suggestions", [])

    if not suggestions:
        return "No optimization suggestions available for this domain yet. Suggestions are generated after visibility data and page analyses are collected."

    lines = ["# Optimization Suggestions", ""]
    lines.append(f"Found {len(suggestions)} suggestion(s) to improve your AI visibility.")
    lines.append("")

    # Group by priority
    priority_order = ["critical", "high", "medium", "low"]
    grouped = {p: [s for s in suggestions if s.get("priority") == p] for p in priority_order}
    other = [s for s in suggestions if s.get("priority") not in priority_order]

    priority_labels = {
        "critical": "Critical",
        "high": "High Priority",
        "medium": "Medium Priority",
        "low": "Low Priority",
    }

    def _render_group(label: str, items: list):
        if not items:
            return
        lines.append(f"## {label}")
        lines.append("")
        for i, s in enumerate(items, 1):
            title = s.get("title") or s.get("type", "Suggestion")
            lines.append(f"### {i}. {title}")

            key = s.get("key")
            if key:
                lines.append(f"- **Key**: `{key}`")

            description = s.get("description") or s.get("message", "")
            if description:
                lines.append(description)

            category = s.get("category") or s.get("type")
            if category:
                lines.append(f"- **Category**: {category}")

            entity_url = s.get("entity_url")
            if entity_url:
                lines.append(f"- **Page**: {entity_url}")

            mcp_hint = s.get("mcp_tool_hint")
            if mcp_hint:
                lines.append(f"- **MCP Tool**: {mcp_hint}")

            metadata = s.get("metadata", {})
            if metadata.get("ai_readiness_score") is not None:
                lines.append(f"- **AI-Readiness Score**: {metadata['ai_readiness_score']}/100")
            if metadata.get("citation_count") is not None:
                lines.append(f"- **Citations**: {metadata['citation_count']}")

            lines.append("")

    for p in priority_order:
        _render_group(priority_labels[p], grouped[p])

    if other:
        _render_group("Other", other)

    return "\n".join(lines)


@mcp.tool(annotations=READ_ONLY)
def aeko_get_suggestions(domain_id: str) -> str:
    """Get prioritized optimization suggestions for a domain.

    Returns actionable recommendations to improve how AI engines
    (ChatGPT, Claude, Gemini, Perplexity) discover, understand,
    and recommend your products. Organized by priority level.

    Args:
        domain_id: UUID of the domain.
    """
    data = client.get("/api/suggestions", params={"domain_id": domain_id})
    return _format_suggestions(data)


@mcp.tool(annotations=WRITE)
def aeko_complete_suggestion(suggestion_id: str) -> str:
    """Mark a v1 suggestion as completed in the AEKO dashboard.

    Call this after you've finished implementing a suggestion (e.g., after
    creating a blog article, generating JSON-LD, or optimizing a page).

    Args:
        suggestion_id: UUID of the v1 suggestion to mark as complete. This is
            the ``id`` field from ``aeko_get_suggestions`` output, NOT the
            v2 ``suggestion_key`` from ``aeko_get_suggestions_v2``. The v2
            API is read-only; v2-flow skills should skip this step.
    """
    # Backend route: POST /api/suggestions/{suggestion_id}/complete
    # Body is optional (CompleteRequest with completed_via); we always stamp
    # "mcp" so the dashboard timeline can distinguish MCP-driven completions.
    client.post(
        f"/api/suggestions/{suggestion_id}/complete",
        json={"completed_via": "mcp"},
    )
    return f"Suggestion '{suggestion_id}' marked as completed in AEKO dashboard."
