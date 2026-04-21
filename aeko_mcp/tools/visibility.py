from typing import Optional

from ..server import mcp, client
from ._annotations import READ_ONLY


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


def _format_cited_pages(cited_pages: list) -> str:
    """Render the cited_pages slice of /api/visibility/summary."""
    if not cited_pages:
        return (
            "# Cited Pages\n\n"
            "No cited pages yet. AI engines haven't referenced your domain's "
            "pages in the responses AEKO has collected."
        )

    lines = [f"# Cited Pages ({len(cited_pages)})", ""]
    lines.append("| Page | Citations | AI Engines | Top Prompt |")
    lines.append("|------|-----------|------------|------------|")
    for p in cited_pages[:20]:
        url = p.get("url") or p.get("page_url") or "(unknown)"
        citation_count = p.get("citation_count") or p.get("count") or 0
        engines_list = p.get("ai_platforms") or p.get("engines") or []
        engines = ", ".join(engines_list) if isinstance(engines_list, list) else str(engines_list)
        top_prompt = p.get("top_prompt") or p.get("prompt") or ""
        if len(top_prompt) > 60:
            top_prompt = top_prompt[:57] + "..."
        lines.append(f"| {url} | {citation_count} | {engines} | {top_prompt} |")
    return "\n".join(lines)


def _format_tracked_metrics(data: dict) -> str:
    """7-day WoW metrics — used when scope='tracked_prompt_metrics'."""
    def _trend(value: Optional[float]) -> str:
        if value is None:
            return "— (no prior data)"
        if value > 0:
            return f"+{value:.1f}% ↑"
        if value < 0:
            return f"{value:.1f}% ↓"
        return "0% →"

    lines = ["# Performance Metrics (Last 7 Days)", ""]
    lines.append("| Metric | Value | vs Previous 7 Days |")
    lines.append("|--------|-------|--------------------|")

    mentions = data.get("total_mentions", 0)
    citations = data.get("total_citations", 0)
    sentiment = data.get("avg_sentiment_score")
    visibility = data.get("avg_visibility_score")

    lines.append(f"| Mentions | {mentions} | {_trend(data.get('mentions_diff'))} |")
    lines.append(f"| Citations | {citations} | {_trend(data.get('citations_diff'))} |")
    if sentiment is not None:
        lines.append(f"| Avg Sentiment | {sentiment:.1f}% | {_trend(data.get('sentiment_diff'))} |")
    if visibility is not None:
        lines.append(f"| Avg Visibility | {visibility:.1f} | {_trend(data.get('visibility_diff'))} |")

    share_pct = data.get("mention_share_pct")
    share_total = data.get("mention_share_total")
    if share_pct is not None and share_total is not None:
        lines.append(f"| Mention Share | {share_pct:.1f}% ({share_total} tracked) | — |")

    lines.append("")
    current = data.get("data_points_current", 0)
    previous = data.get("data_points_previous", 0)
    lines.append(f"*Based on {current} data points (current) vs {previous} (previous period).*")
    return "\n".join(lines)


_VISIBILITY_SCOPES = {"overview", "cited_sources", "tracked_prompt_metrics"}


@mcp.tool(annotations=READ_ONLY)
def aeko_get_visibility_summary(
    domain_id: str,
    scope: str = "overview",
    window: Optional[str] = None,
) -> str:
    """Brand visibility + citation metrics across AI engines.

    One-tool consolidation of the prior `aeko_get_visibility_summary`,
    `aeko_get_cited_sources`, and `aeko_get_metrics` surfaces — pick the
    view via `scope`.

    Args:
        domain_id: UUID of the domain.
        scope:
          - `overview` (default) — mention / citation / source counts, 30-day
            trend, recent brand mentions across ChatGPT / Claude / Gemini /
            Perplexity.
          - `cited_sources` — the subset of your pages AI engines cited,
            with per-page citation counts + triggering prompts.
          - `tracked_prompt_metrics` — 7-day performance across tracked
            prompts with week-over-week trends (mentions / citations /
            sentiment / visibility / mention share).
        window: Optional time window hint. Currently only honored for the
            `tracked_prompt_metrics` scope (backend fixed at 7d + 7d WoW);
            reserved for future use on other scopes.
    """
    if scope not in _VISIBILITY_SCOPES:
        allowed = ", ".join(sorted(_VISIBILITY_SCOPES))
        return f"Invalid `scope`: {scope}. Allowed: {allowed}."

    if scope == "tracked_prompt_metrics":
        data = client.get("/api/tracked-prompts/metrics", params={"domain_id": domain_id})
        return _format_tracked_metrics(data)

    data = client.get("/api/visibility/summary", params={"domain_id": domain_id})

    if scope == "cited_sources":
        return _format_cited_pages(data.get("cited_pages") or [])

    return _format_visibility(data)


@mcp.tool(annotations=READ_ONLY)
def aeko_get_domain_info(domain_id: str) -> str:
    """Get domain details and AI-readiness infrastructure status.

    Shows whether the domain has llms.txt, whether robots.txt blocks AI crawlers,
    and whether JSON-LD structured data is present.

    Args:
        domain_id: UUID of the domain.
    """
    data = client.get(f"/api/domains/{domain_id}")
    return _format_domain(data)


def _format_domain_list(domains: list[dict]) -> str:
    """Render the authenticated user's domain list as picker-friendly Markdown.

    Downstream skills grep for the '`<uuid>`' pattern to harvest the id;
    keep the format stable or update callers.
    """
    if not domains:
        return (
            "# Your AEKO Domains\n\n"
            "No domains connected yet. Add one in the AEKO dashboard "
            "(https://aeko-intelligence.com) before running domain-scoped skills."
        )

    lines = [f"# Your AEKO Domains ({len(domains)})", ""]
    for d in domains:
        name = d.get("name") or d.get("ko_name") or d.get("base_url") or "(unnamed)"
        base_url = d.get("base_url") or ""
        domain_id = d.get("id") or ""
        lines.append(f"- **{name}** — `{domain_id}`")
        if base_url:
            lines.append(f"  - URL: {base_url}")
        scope = d.get("scope")
        if scope:
            lines.append(f"  - Scope: {scope}")
    lines.append("")
    lines.append(
        "Pass the UUID (the backtick-quoted value) to any domain-scoped tool "
        "or skill, e.g. `aeko_get_brand_kit(domain_id=...)`."
    )
    return "\n".join(lines)


@mcp.tool(annotations=READ_ONLY)
def aeko_list_domains() -> str:
    """List every domain the authenticated AEKO user has connected.

    Use this when a skill or tool needs a domain UUID and the user hasn't
    supplied one. Returns each domain's UUID, human-readable name, base URL,
    and industry scope so the caller can auto-select (if there's one) or
    offer a pick-list. No arguments; reads the bearer token from the MCP
    session to resolve the current user.
    """
    data = client.get("/api/domains")
    # Backend returns a bare list (List[DomainResponse]).
    return _format_domain_list(data if isinstance(data, list) else [])
