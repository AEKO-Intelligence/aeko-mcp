from ..server import mcp, client
from ._annotations import READ_ONLY


def _format_analysis(data: dict) -> str:
    title = data.get("product_title") or "Untitled Product"
    url = data.get("product_url", "N/A")
    status = data.get("status", "unknown")
    country = data.get("country", "N/A")
    language = data.get("language") or "N/A"

    lines = [f"# Product Analysis: {title}", ""]
    lines.append(f"- **URL**: {url}")
    lines.append(f"- **Target Market**: {country}")
    lines.append(f"- **Language**: {language}")
    lines.append(f"- **Status**: {status}")
    lines.append("")

    if status == "pending":
        lines.append("Analysis is still being processed. Check back shortly.")
        return "\n".join(lines)

    if status == "failed":
        error = data.get("error_message", "Unknown error")
        lines.append(f"Analysis failed: {error}")
        return "\n".join(lines)

    analyzed_at = data.get("analyzed_at")
    if analyzed_at:
        lines.append(f"*Analyzed at: {analyzed_at}*")
        lines.append("")

    # Analysis result
    result = data.get("analysis_result")
    if result and isinstance(result, dict):
        lines.append("## Analysis Results")
        lines.append("")

        # Handle structured analysis fields
        summary = result.get("summary") or result.get("overview")
        if summary:
            lines.append(summary)
            lines.append("")

        strengths = result.get("strengths", [])
        if strengths:
            lines.append("### Strengths")
            for s in strengths:
                lines.append(f"- {s}")
            lines.append("")

        weaknesses = result.get("weaknesses") or result.get("gaps", [])
        if weaknesses:
            lines.append("### Weaknesses / Gaps")
            for w in weaknesses:
                lines.append(f"- {w}")
            lines.append("")

        recommendations = result.get("recommendations") or result.get("action_items", [])
        if recommendations:
            lines.append("### Recommendations")
            for r in recommendations:
                if isinstance(r, str):
                    lines.append(f"- {r}")
                elif isinstance(r, dict):
                    lines.append(f"- **{r.get('title', 'Action')}**: {r.get('description', str(r))}")
            lines.append("")

        positioning = result.get("positioning")
        if positioning:
            lines.append("### Market Positioning")
            lines.append(positioning if isinstance(positioning, str) else str(positioning))
            lines.append("")

    # Competitor data
    competitors = data.get("competitor_data")
    if competitors and isinstance(competitors, dict):
        lines.append("## Competitor Landscape")
        lines.append("")

        comp_list = competitors.get("competitors", [])
        if comp_list:
            lines.append("| Competitor | URL | Key Differentiator |")
            lines.append("|------------|-----|--------------------|")
            for c in comp_list[:10]:
                if isinstance(c, dict):
                    name = c.get("name", "Unknown")
                    comp_url = c.get("url", "N/A")
                    diff = c.get("differentiator") or c.get("strength", "N/A")
                    lines.append(f"| {name} | {comp_url} | {diff} |")
            lines.append("")

        comp_summary = competitors.get("summary") or competitors.get("analysis")
        if comp_summary:
            lines.append(comp_summary if isinstance(comp_summary, str) else str(comp_summary))
            lines.append("")

    return "\n".join(lines)


@mcp.tool(annotations=READ_ONLY)
def aeko_get_product_analysis(analysis_id: str) -> str:
    """Get competitive analysis for a specific product.

    Returns the AI-generated analysis including strengths, weaknesses,
    recommendations, market positioning, and competitor landscape for
    a product in a target market.

    Args:
        analysis_id: UUID of the product analysis.
    """
    data = client.get(f"/api/product-analyses/{analysis_id}")
    return _format_analysis(data)
