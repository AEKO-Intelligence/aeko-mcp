import json
from typing import Any, Optional

from ..server import mcp, client
from ._annotations import READ_ONLY, WRITE_ONCE


def _json_block(title: str, payload: Any) -> str:
    return f"# {title}\n\n```json\n{json.dumps(payload, ensure_ascii=False, indent=2, default=str)}\n```"


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

    # Metrics overview — totals are all-time; diffs are 7-day week-over-week.
    lines.append("## Key Metrics (All-Time Totals, 7-Day WoW Change)")
    lines.append("")
    lines.append(f"| Metric | Value (all-time) | vs Previous 7 Days |")
    lines.append(f"|--------|------------------|--------------------|")
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

    # Trend — backend returns ~13 weekly buckets (TrendItem: label, period_start, ...)
    if trend:
        lines.append("## Weekly Trend")
        lines.append("")
        lines.append("| Week | Mentions | Citations | Sources | Sentiment |")
        lines.append("|------|----------|-----------|---------|-----------|")
        for t in trend:
            week = t.get("label") or t.get("period_start") or "(unknown)"
            lines.append(
                f"| {week} | {t.get('mentions', 0)} "
                f"| {t.get('citations', 0)} | {t.get('sources', 0)} "
                f"| {t.get('sentiment', 0.0):.1f}% |"
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
        # CitedPageItem: url, full_url, count, title, prompts (BrandMentionItem list)
        url = p.get("url") or "(unknown)"
        citation_count = p.get("count", 0)
        prompts = p.get("prompts") or []
        engines_list = sorted({pr.get("ai_model") for pr in prompts if pr.get("ai_model")})
        engines = ", ".join(engines_list)
        top_prompt = (prompts[0].get("prompt_en") or prompts[0].get("text") or "") if prompts else ""
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


@mcp.tool(title="Get visibility summary", annotations=READ_ONLY)
def aeko_get_visibility_summary(
    domain_id: str,
    scope: str = "overview",
    view: Optional[str] = None,
    vertical_scope: Optional[str] = None,
    country: Optional[str] = None,
    ai_platform: Optional[str] = None,
    query_type: Optional[str] = None,
    funnel_stage: Optional[str] = None,
    prompt_ids: Optional[list[str]] = None,
    window: Optional[str] = None,
) -> str:
    """Brand visibility + citation metrics across AI engines.

    One-tool consolidation of the prior `aeko_get_visibility_summary`,
    `aeko_get_cited_sources`, and `aeko_get_metrics` surfaces. New callers
    should pick the view via `view`; `scope` remains the legacy view selector.

    Args:
        domain_id: UUID of the domain.
        scope:
          Legacy view selector. Keep using one of the values below for
          backwards compatibility, or pass `view=...`.
        view:
          - `overview` (default) — all-time mention / citation / source counts
            with 7-day week-over-week diffs, a 13-week weekly trend, and recent
            brand mentions across ChatGPT / Claude / Gemini / Perplexity.
          - `cited_sources` — the subset of your pages AI engines cited,
            with per-page citation counts + triggering prompts.
          - `tracked_prompt_metrics` — 7-day performance across tracked
            prompts with week-over-week trends (mentions / citations /
            sentiment / visibility / mention share).
        window: Optional time window hint. Currently only honored for the
            `tracked_prompt_metrics` scope (backend fixed at 7d + 7d WoW);
            reserved for future use on other scopes.
    """
    selected_view = view or scope
    # Backwards-compatible escape hatch: if a caller accidentally passes a
    # vertical filter via the old `scope` name, use it as the backend filter
    # and keep the visible report on the overview view.
    if selected_view not in _VISIBILITY_SCOPES and vertical_scope is None:
        vertical_scope = scope
        selected_view = view or "overview"
    if selected_view not in _VISIBILITY_SCOPES:
        allowed = ", ".join(sorted(_VISIBILITY_SCOPES))
        return f"Invalid `view`: {selected_view}. Allowed: {allowed}."

    if selected_view == "tracked_prompt_metrics":
        data = client.get("/api/tracked-prompts/metrics", params={"domain_id": domain_id})
        return _format_tracked_metrics(data)

    params: dict[str, Any] = {"domain_id": domain_id}
    if vertical_scope:
        params["scope"] = vertical_scope
    if country:
        params["country"] = country
    if ai_platform:
        params["ai_platform"] = ai_platform
    if query_type:
        params["query_type"] = query_type
    if funnel_stage:
        params["funnel_stage"] = funnel_stage
    if prompt_ids:
        params["prompt_ids"] = ",".join(prompt_ids)

    data = client.get("/api/visibility/summary", params=params)

    if selected_view == "cited_sources":
        return _format_cited_pages(data.get("cited_pages") or [])

    return _format_visibility(data)


@mcp.tool(title="Get domain info", annotations=READ_ONLY)
def aeko_get_domain_info(domain_id: str) -> str:
    """Get domain details and AI-readiness infrastructure status.

    Shows whether the domain has llms.txt, whether robots.txt blocks AI crawlers,
    and whether JSON-LD structured data is present.

    Args:
        domain_id: UUID of the domain.
    """
    data = client.get(f"/api/domains/{domain_id}")
    return _format_domain(data)


@mcp.tool(title="Get citability", annotations=READ_ONLY)
def aeko_get_citability(
    domain_id: Optional[str] = None,
    source_id: Optional[str] = None,
) -> str:
    """Read AI citability scoring for a domain or a crawled source page.

    Pass exactly one of `domain_id` or `source_id`. Starter+ server-side.
    """
    if bool(domain_id) == bool(source_id):
        return "Pass exactly one of domain_id or source_id."
    if domain_id:
        data = client.get("/api/citability/domain", params={"domain_id": domain_id})
        return _json_block("Citability domain score", data)
    data = client.get("/api/citability/page", params={"source_id": source_id})
    return _json_block("Citability page score", data)


def _format_domain_list(domains: list[dict]) -> str:
    """Render the authenticated user's domain list as picker-friendly Markdown.

    Downstream skills grep for the '`<uuid>`' pattern to harvest the id;
    keep the format stable or update callers.
    """
    if not domains:
        return (
            "# Your AEKO Domains\n\n"
            "No domains connected yet. Use `aeko_add_domain` to add one from "
            "the agent, then continue the setup flow."
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
        "or skill, e.g. `aeko_list_own_content(domain_id=...)`."
    )
    return "\n".join(lines)


@mcp.tool(title="List connected domains", annotations=READ_ONLY)
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


@mcp.tool(title="Add domain", annotations=WRITE_ONCE)
def aeko_add_domain(
    base_url: str,
    display_name: Optional[str] = None,
    scope: Optional[str] = None,
    ko_name: Optional[str] = None,
    domain_role: Optional[str] = None,
    has_llms_txt: Optional[bool] = None,
    robots_blocks_ai: Optional[bool] = None,
    has_json_ld: Optional[bool] = None,
    extracted_name: Optional[str] = None,
) -> str:
    """Add a domain to the current AEKO account.

    Starter users can add domains within their plan limit. The backend owns
    canonicalization, ownership checks, and package limits.
    """
    body = {
        "base_url": base_url,
        "display_name": display_name,
        "scope": scope,
        "ko_name": ko_name,
        "domain_role": domain_role,
        "has_llms_txt": has_llms_txt,
        "robots_blocks_ai": robots_blocks_ai,
        "has_json_ld": has_json_ld,
        "extracted_name": extracted_name,
    }
    payload = {k: v for k, v in body.items() if v is not None}
    data = client.post("/api/domains", json=payload)
    return _json_block("Domain added", data)
