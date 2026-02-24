from ..server import mcp, client


def _format_diff(value: float | None) -> str:
    """Format a percentage diff value like +12.3% or -5.0%."""
    if value is None:
        return "N/A"
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.1f}%"


def _format_visibility(data: dict) -> str:
    metrics = data.get("metrics", {})
    trend = data.get("trend", [])
    brand_keyword = data.get("brand_keyword", "")
    brand_mentions = data.get("brand_mentions", [])

    lines = [f"# Visibility Summary for \"{brand_keyword}\"", ""]

    # Metrics overview
    lines.append("## Key Metrics (Last 30 Days)")
    lines.append("")
    lines.append(f"| Metric | Value | vs Previous Period |")
    lines.append(f"|--------|-------|--------------------|")
    lines.append(
        f"| Mentions | {metrics.get('total_mentions', 0)} "
        f"| {_format_diff(metrics.get('mentions_diff'))} |"
    )
    lines.append(
        f"| Citations | {metrics.get('total_citations', 0)} "
        f"| {_format_diff(metrics.get('citations_diff'))} |"
    )
    lines.append(
        f"| Sources | {metrics.get('total_sources', 0)} "
        f"| {_format_diff(metrics.get('sources_diff'))} |"
    )
    lines.append(
        f"| Sentiment | {metrics.get('avg_sentiment_score', 0):.1f}% positive "
        f"| {_format_diff(metrics.get('sentiment_diff'))} |"
    )
    lines.append("")

    # Trend
    if trend:
        lines.append("## Monthly Trend")
        lines.append("")
        lines.append("| Month | Mentions | Citations | Sources | Sentiment |")
        lines.append("|-------|----------|-----------|---------|-----------|")
        for t in trend:
            lines.append(
                f"| {t['month']} {t['year']} | {t['mentions']} "
                f"| {t['citations']} | {t['sources']} "
                f"| {t['sentiment']:.1f}% |"
            )
        lines.append("")

    # Brand mentions (top 10)
    if brand_mentions:
        lines.append(f"## Recent Brand Mentions (showing {min(len(brand_mentions), 10)} of {len(brand_mentions)})")
        lines.append("")
        for m in brand_mentions[:10]:
            sentiment_label = m.get("sentiment", "neutral")
            lines.append(f"- **{m.get('ai_model', 'Unknown')}** | {sentiment_label} | {m.get('frequency', 0)} mentions, {m.get('citation_count', 0)} citations")
            prompt_text = m.get("prompt_en") or m.get("text", "")
            if prompt_text:
                lines.append(f"  - Prompt: {prompt_text[:120]}{'...' if len(prompt_text) > 120 else ''}")
            snippet = m.get("response_snippet", "")
            if snippet:
                lines.append(f"  - Snippet: {snippet[:150]}{'...' if len(snippet) > 150 else ''}")
        lines.append("")

    return "\n".join(lines)


def _format_domain(data: dict) -> str:
    lines = [f"# Domain: {data.get('name', 'Unknown')}", ""]
    lines.append(f"- **URL**: {data.get('base_url', 'N/A')}")
    lines.append(f"- **Korean Name**: {data.get('ko_name') or 'N/A'}")
    lines.append(f"- **Industry Scope**: {data.get('scope') or 'N/A'}")
    lines.append("")

    lines.append("## AI Readiness Checklist")
    lines.append("")

    has_llms = data.get("has_llms_txt")
    robots_blocks = data.get("robots_blocks_ai")
    has_jsonld = data.get("has_json_ld")

    def _check(val: bool | None) -> str:
        if val is None:
            return "Unknown"
        return "Yes" if val else "No"

    lines.append(f"| Check | Status |")
    lines.append(f"|-------|--------|")
    lines.append(f"| Has llms.txt | {_check(has_llms)} |")
    lines.append(f"| Robots.txt blocks AI | {_check(robots_blocks)} |")
    lines.append(f"| Has JSON-LD structured data | {_check(has_jsonld)} |")
    lines.append("")

    if robots_blocks is True:
        lines.append("> **Warning**: Your robots.txt is blocking AI crawlers. This may prevent AI engines from indexing your content.")
        lines.append("")
    if has_llms is False:
        lines.append("> **Tip**: Adding an llms.txt file helps AI engines understand your site structure and content.")
        lines.append("")

    return "\n".join(lines)


@mcp.tool()
def aeko_get_visibility_summary(domain_id: str) -> str:
    """Get brand visibility metrics across AI engines (ChatGPT, Claude, Gemini, Perplexity).

    Returns mention counts, citation counts, source counts, sentiment trends,
    month-over-month changes, and recent brand mentions with response snippets.

    Args:
        domain_id: UUID of the domain to analyze.
    """
    data = client.get("/api/visibility/summary", params={"domain_id": domain_id})
    return _format_visibility(data)


@mcp.tool()
def aeko_get_domain_info(domain_id: str) -> str:
    """Get domain details and AI-readiness infrastructure status.

    Shows whether the domain has llms.txt, whether robots.txt blocks AI crawlers,
    and whether JSON-LD structured data is present.

    Args:
        domain_id: UUID of the domain.
    """
    data = client.get(f"/api/domains/{domain_id}")
    return _format_domain(data)
