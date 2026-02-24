from ..server import mcp, client


PLATFORM_DISPLAY = {
    "openai": "GPT-4",
    "anthropic": "Claude",
    "google": "Gemini",
    "perplexity": "Perplexity",
}


def _format_prompts(data: dict) -> str:
    prompts = data.get("prompts", [])
    total = data.get("total_count", len(prompts))
    page = data.get("page", 1)
    total_pages = data.get("total_pages", 1)

    if not prompts:
        return "No research prompts found matching your filters. Try broadening your search criteria."

    lines = [
        "# Research Prompts",
        "",
        f"Showing page {page} of {total_pages} ({total} total prompts).",
        "",
    ]

    for i, p in enumerate(prompts, 1):
        platform = PLATFORM_DISPLAY.get(p.get("ai_platform", ""), p.get("ai_platform", "Unknown"))
        prompt_text = p.get("prompt_en") or p.get("raw_prompt", "")
        country = p.get("country", "N/A")
        query_type = p.get("query_type") or "N/A"
        funnel = p.get("funnel_stage") or "N/A"
        tags = ", ".join(p.get("tags", [])) or "None"
        scopes = ", ".join(p.get("scopes", [])) or "None"
        keywords = ", ".join(p.get("keywords", [])) or "None"

        lines.append(f"## {i}. {prompt_text[:100]}{'...' if len(prompt_text) > 100 else ''}")
        lines.append("")
        lines.append(f"- **ID**: `{p.get('id', 'N/A')}`")
        lines.append(f"- **Platform**: {platform}")
        lines.append(f"- **Country**: {country}")
        lines.append(f"- **Query Type**: {query_type}")
        lines.append(f"- **Funnel Stage**: {funnel}")
        lines.append(f"- **Scopes**: {scopes}")
        lines.append(f"- **Keywords**: {keywords}")
        lines.append(f"- **Tags**: {tags}")

        # Latest response
        resp = p.get("latest_response")
        if resp:
            lines.append("")
            lines.append("**Latest Response:**")
            resp_date = resp.get("response_date", "N/A")
            sentiment = resp.get("sentiment", "N/A")
            mention_count = resp.get("mention_count", 0)
            citation_count = resp.get("citation_count", 0)
            source_count = resp.get("source_count", 0)
            lines.append(f"- Date: {resp_date} | Sentiment: {sentiment}")
            lines.append(f"- Mentions: {mention_count} | Citations: {citation_count} | Sources: {source_count}")

            snippet = resp.get("response_snippet_en") or resp.get("response_snippet", "")
            if snippet:
                lines.append(f"- Snippet: {snippet[:200]}{'...' if len(snippet) > 200 else ''}")

            # Mention metrics
            metrics = resp.get("mention_metrics", [])
            if metrics:
                lines.append("")
                lines.append("**Mention Breakdown:**")
                lines.append("")
                lines.append("| Brand | Score | Mentions | Citations | Sentiment |")
                lines.append("|-------|-------|----------|-----------|-----------|")
                for m in metrics[:10]:
                    name = m.get("mention_name", "Unknown")
                    score = m.get("visibility_score")
                    score_str = f"{score:.1f}" if score is not None else "N/A"
                    mc = m.get("mention_count", 0)
                    cc = m.get("citation_count", 0)
                    sent = m.get("sentiment", "N/A")
                    lines.append(f"| {name} | {score_str} | {mc} | {cc} | {sent} |")

        lines.append("")

    if total_pages > 1:
        lines.append(f"*Page {page}/{total_pages}. Use page parameter to see more results.*")
        lines.append("")

    return "\n".join(lines)


def _format_responses(data: dict) -> str:
    # data could be a single response or a list
    responses = data if isinstance(data, list) else [data]

    if not responses:
        return "No responses found for this prompt."

    lines = ["# Prompt Responses", ""]

    for i, resp in enumerate(responses[:20], 1):
        resp_date = resp.get("response_date", "N/A")
        sentiment = resp.get("sentiment", "N/A")
        mention_count = resp.get("mention_count", 0)
        citation_count = resp.get("citation_count", 0)
        source_count = resp.get("source_count", 0)

        lines.append(f"## Response {i}")
        lines.append(f"- **Date**: {resp_date}")
        lines.append(f"- **Sentiment**: {sentiment}")
        lines.append(f"- **Mentions**: {mention_count} | **Citations**: {citation_count} | **Sources**: {source_count}")

        snippet = resp.get("response_snippet_en") or resp.get("response_snippet", "")
        if snippet:
            lines.append(f"- **Snippet**: {snippet[:300]}{'...' if len(snippet) > 300 else ''}")

        full = resp.get("full_response", "")
        if full:
            lines.append("")
            lines.append("**Full Response:**")
            lines.append("")
            # Truncate very long responses
            if len(full) > 2000:
                lines.append(full[:2000])
                lines.append(f"\n*...truncated ({len(full)} total characters)*")
            else:
                lines.append(full)

        # Mentions breakdown
        mentions = resp.get("mentions", {})
        if mentions:
            lines.append("")
            lines.append("**Brands Mentioned:**")
            for name, count in mentions.items():
                lines.append(f"- {name}: {count}x")

        # Citations
        citations = resp.get("raw_citations", [])
        if citations:
            lines.append("")
            lines.append("**Cited Sources:**")
            for c in citations[:10]:
                if isinstance(c, dict):
                    title = c.get("title", "")
                    url = c.get("url", "")
                    lines.append(f"- [{title or url}]({url})" if url else f"- {title}")

        lines.append("")

    return "\n".join(lines)


def _format_tracked_prompts(data: list) -> str:
    if not data:
        return "No tracked prompts found. Add prompts to track how AI engines respond to queries relevant to your products."

    lines = ["# Tracked Prompts", ""]
    lines.append(f"You are tracking {len(data)} prompt(s).")
    lines.append("")

    lines.append("| # | Prompt | Platform | Country | Status |")
    lines.append("|---|--------|----------|---------|--------|")

    for i, p in enumerate(data, 1):
        prompt_text = p.get("prompt_en") or p.get("raw_prompt", "N/A")
        # Truncate for table
        if len(prompt_text) > 60:
            prompt_text = prompt_text[:57] + "..."
        platform = PLATFORM_DISPLAY.get(p.get("ai_platform", ""), p.get("ai_platform", "N/A"))
        country = p.get("country", "N/A")
        status = p.get("status", "tracked")
        lines.append(f"| {i} | {prompt_text} | {platform} | {country} | {status} |")

    lines.append("")
    lines.append("Use individual prompt IDs to get detailed response data.")
    lines.append("")

    return "\n".join(lines)


@mcp.tool()
def aeko_search_research_prompts(
    scope: str | None = None,
    keyword: str | None = None,
    country: str | None = None,
    ai_platform: str | None = None,
    query_type: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> str:
    """Search the research prompt library with filters.

    Browse pre-built research prompts to understand how AI engines respond
    to queries in your industry. At least one filter must be provided.

    Args:
        scope: Industry scope (e.g., "beauty", "fashion", "electronics").
        keyword: Search text in prompt content or keywords.
        country: Country code (e.g., "US", "KR", "JP").
        ai_platform: AI platform filter ("openai", "anthropic", "google", "perplexity").
        query_type: Query type filter (e.g., "comparison", "recommendation").
        page: Page number (default 1).
        page_size: Results per page (default 20, max 100).
    """
    params: dict = {"page": page, "page_size": page_size}
    if scope:
        params["scope"] = scope
    if keyword:
        params["keyword"] = keyword
    if country:
        params["country"] = country
    if ai_platform:
        params["ai_platform"] = ai_platform
    if query_type:
        params["query_type"] = query_type
    data = client.get("/api/research/prompts", params=params)
    return _format_prompts(data)


@mcp.tool()
def aeko_get_tracked_prompts() -> str:
    """List all prompts you are actively tracking.

    Shows your tracked prompts with their AI platform, country,
    and tracking status. These prompts are periodically re-queried
    to monitor changes in AI engine responses over time.
    """
    data = client.get("/api/tracked-prompts")
    return _format_tracked_prompts(data)
