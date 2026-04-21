from typing import Any, Optional

from ..server import mcp, client
from ._annotations import READ_ONLY, WRITE


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
        prompt_ko = p.get("prompt_ko")
        country = p.get("country", "N/A")
        query_type = p.get("query_type") or "N/A"
        funnel = p.get("funnel_stage") or "N/A"
        tags = ", ".join(p.get("tags", [])) or "None"
        scopes = ", ".join(p.get("scopes", [])) or "None"
        keywords = ", ".join(p.get("keywords", [])) or "None"

        lines.append(f"## {i}. {prompt_text[:100]}{'...' if len(prompt_text) > 100 else ''}")
        lines.append("")
        if prompt_ko:
            lines.append(f"- **Korean**: {prompt_ko[:100]}{'...' if len(prompt_ko) > 100 else ''}")
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
            snippet_ko = resp.get("response_snippet_ko")
            if snippet_ko:
                lines.append(f"- Snippet (KO): {snippet_ko[:200]}{'...' if len(snippet_ko) > 200 else ''}")

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
        if len(prompt_text) > 60:
            prompt_text = prompt_text[:57] + "..."
        platform = PLATFORM_DISPLAY.get(p.get("ai_platform", ""), p.get("ai_platform", "N/A"))
        country = p.get("country", "N/A")
        status = p.get("status", "tracked")
        lines.append(f"| {i} | {prompt_text} | {platform} | {country} | {status} |")
        prompt_ko = p.get("prompt_ko")
        if prompt_ko:
            ko_text = (prompt_ko[:57] + "...") if len(prompt_ko) > 60 else prompt_ko
            lines.append(f"|   | *{ko_text}* |   |   |   |")

    lines.append("")
    lines.append("Use individual prompt IDs to get detailed response data.")
    lines.append("")

    return "\n".join(lines)


@mcp.tool(annotations=READ_ONLY)
def aeko_search_research_prompts(
    scope: str | None = None,
    keyword: str | None = None,
    country: str | None = None,
    ai_platform: str | None = None,
    query_type: str | None = None,
    persona_type: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> str:
    """Search the research prompt library with filters.

    Browse pre-built research prompts to understand how AI engines respond
    to queries in your industry. Powers the find-prompts-to-track loop: the
    skill narrows the library by platform + persona + country, surfaces the
    best candidates, and the user tracks them with `aeko_track_prompt`.

    At least one filter must be provided.

    Args:
        scope: Industry scope (e.g., "beauty", "fashion", "electronics").
        keyword: Search text in prompt content or keywords.
        country: Country code (e.g., "US", "KR", "JP").
        ai_platform: AI platform filter (`openai`, `anthropic`, `google`,
            `perplexity`).
        query_type: Query type filter (e.g., `comparison`, `recommendation`).
        persona_type: Persona type filter — narrows prompts to those tagged
            against a specific buyer persona (e.g., `new_mom`,
            `enthusiast`). Use together with `ai_platform` for
            high-precision audience research.
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
    if persona_type:
        params["persona_type"] = persona_type
    data = client.get("/api/research/prompts", params=params)
    return _format_prompts(data)


@mcp.tool(annotations=READ_ONLY)
def aeko_get_tracked_prompts() -> str:
    """List all prompts you are actively tracking.

    Shows your tracked prompts with their AI platform, country,
    and tracking status. These prompts are periodically re-queried
    to monitor changes in AI engine responses over time.
    """
    data = client.get("/api/tracked-prompts")
    return _format_tracked_prompts(data)


@mcp.tool(annotations=WRITE)
def aeko_track_prompt(
    raw_prompt: str,
    ai_platform: str,
    prompt_en: Optional[str] = None,
    prompt_ko: Optional[str] = None,
    model: Optional[str] = None,
    language: Optional[str] = None,
    country: Optional[str] = None,
    industry: Optional[str] = None,
    vertical: Optional[str] = None,
    persona: Optional[str] = None,
    tags: Optional[list[str]] = None,
) -> str:
    """Start tracking a prompt so AEKO re-queries it across AI engines.

    Use after `aeko_search_research_prompts` to pick a research prompt to
    track — pass the same `raw_prompt` / `ai_platform` / `country` / etc.
    that the search surfaced. Creates a user-owned tracked-prompt row that
    AEKO's pipeline will re-query on cadence so you can watch how AI
    responses shift over time.

    Idempotent: tracking a prompt you already track returns a 409; tracking
    one you previously untracked reactivates it. Package limits (max tracked
    prompts, max markets) apply.

    Args:
        raw_prompt: The prompt text to track (required).
        ai_platform: Target AI engine — `openai`, `anthropic`, `google`, or
            `perplexity` (required).
        prompt_en / prompt_ko: Optional pre-translated forms.
        model: Specific model name (e.g. `claude-sonnet-4-5`).
        language: Language code (`en`, `ko`, etc.). Derived from `country`
            if omitted.
        country: ISO-3166 country code (must be in your account's
            selected_markets).
        industry / vertical: Classification fields matching the research
            prompt's shape — pass through from the search result.
        persona: Optional persona label (max 500 chars).
        tags: Optional list of free-form tags.
    """
    body: dict[str, Any] = {
        "raw_prompt": raw_prompt,
        "ai_platform": ai_platform,
    }
    for key, val in (
        ("prompt_en", prompt_en),
        ("prompt_ko", prompt_ko),
        ("model", model),
        ("language", language),
        ("country", country),
        ("industry", industry),
        ("vertical", vertical),
        ("persona", persona),
        ("tags", tags),
    ):
        if val is not None:
            body[key] = val

    resp = client.post("/api/tracked-prompts", json=body)
    prompt_id = resp.get("id", "?")
    status_val = resp.get("status", "tracked")
    display = resp.get("prompt_en") or resp.get("raw_prompt") or raw_prompt
    return f"Tracked prompt `{prompt_id}` ({status_val}): {display[:120]}"


@mcp.tool(annotations=WRITE)
def aeko_untrack_prompt(prompt_id: str) -> str:
    """Stop tracking a prompt. Historical response data is preserved.

    Sets the user-prompt status to `untracked` — AEKO stops re-querying it,
    but existing responses / citations / source crawls remain readable via
    `aeko_get_tracked_prompt(prompt_id)`. Idempotent: calling on a prompt
    the user never tracked returns 404; calling twice is a no-op after the
    first call.

    Args:
        prompt_id: UUID of the prompt to stop tracking.
    """
    client.delete(f"/api/tracked-prompts/{prompt_id}")
    return f"Untracked prompt `{prompt_id}`. Historical data preserved."


def _format_tracked_prompt_detail(data: dict) -> str:
    """Compact rendering of the citation-forensics payload for one prompt."""
    prompt = data.get("prompt") or {}
    responses = data.get("responses") or []
    window = data.get("window", "latest")

    prompt_text = prompt.get("prompt_en") or prompt.get("raw_prompt") or "(unknown)"
    prompt_ko = prompt.get("prompt_ko")

    lines: list[str] = []
    lines.append(f"# Tracked prompt deep-dive ({window})")
    lines.append("")
    lines.append(f"**Prompt**: {prompt_text}")
    if prompt_ko:
        lines.append(f"**Korean**: {prompt_ko}")
    lines.append(f"- **ID**: `{prompt.get('id', '?')}`")
    meta_bits: list[str] = []
    for key in ("country", "industry", "vertical", "query_type", "funnel_stage", "persona"):
        val = prompt.get(key)
        if val:
            meta_bits.append(f"{key}={val}")
    if meta_bits:
        lines.append(f"- {' · '.join(meta_bits)}")
    lines.append("")

    if not responses:
        lines.append("_No responses yet in this window._")
        return "\n".join(lines)

    for idx, resp in enumerate(responses, 1):
        platform = PLATFORM_DISPLAY.get(
            resp.get("ai_platform", ""), resp.get("ai_platform", "Unknown")
        )
        date = resp.get("response_date", "N/A")
        lines.append(f"## {idx}. {platform} — {date}")

        header_bits: list[str] = []
        mention_count = resp.get("mention_count") or 0
        citation_count = resp.get("citation_count") or 0
        source_count = resp.get("source_count") or 0
        sentiment = resp.get("sentiment")
        header_bits.append(f"mentions={mention_count}")
        header_bits.append(f"citations={citation_count}")
        header_bits.append(f"sources={source_count}")
        if sentiment is not None:
            header_bits.append(f"sentiment={sentiment}")
        lines.append(f"- {' · '.join(header_bits)}")

        snippet = resp.get("response_snippet_en") or resp.get("response_snippet")
        if snippet:
            lines.append(f"- **Snippet**: {snippet[:300]}{'...' if len(snippet) > 300 else ''}")

        mentions = resp.get("mentions") or {}
        if mentions:
            top = sorted(mentions.items(), key=lambda kv: kv[1], reverse=True)[:8]
            brand_str = ", ".join(f"{name} ({count}x)" for name, count in top)
            lines.append(f"- **Brands mentioned**: {brand_str}")

        citations = resp.get("citations") or []
        truncated = resp.get("citations_truncated")
        if citations:
            lines.append("")
            cap_note = " (truncated at 20)" if truncated else ""
            lines.append(f"**Citations{cap_note}**:")
            for cit in citations:
                domain = cit.get("domain") or "(unknown)"
                url = cit.get("source_url") or ""
                src_type = cit.get("source_type") or ""
                pos = cit.get("position_in_response")
                pos_str = f" · pos {pos}" if pos is not None else ""
                type_str = f" [{src_type}]" if src_type else ""
                if url:
                    lines.append(f"- {domain}{type_str}{pos_str} — {url}")
                else:
                    lines.append(f"- {domain}{type_str}{pos_str}")
                ctx = cit.get("context_snippet")
                if ctx:
                    trimmed = ctx if len(ctx) <= 200 else ctx[:197] + "..."
                    lines.append(f"  > {trimmed}")

                crawl = cit.get("crawl") or {}
                if crawl:
                    # Surface the most useful crawl fields compactly.
                    json_ld_types: list[str] = []
                    for block in crawl.get("json_ld") or []:
                        if isinstance(block, dict):
                            t = block.get("@type")
                            if isinstance(t, str):
                                json_ld_types.append(t)
                            elif isinstance(t, list):
                                json_ld_types.extend(x for x in t if isinstance(x, str))
                    if json_ld_types:
                        lines.append(f"    • JSON-LD: {', '.join(sorted(set(json_ld_types)))}")
                    analysis = crawl.get("source_analysis") or {}
                    if isinstance(analysis, dict):
                        score = analysis.get("citability_score")
                        if score is not None:
                            lines.append(f"    • Citability: {score}")

        lines.append("")

    return "\n".join(lines)


@mcp.tool(annotations=READ_ONLY)
def aeko_get_tracked_prompt(
    prompt_id: str,
    window: Optional[str] = None,
) -> str:
    """Full citation-forensics payload for one tracked prompt.

    Returns the prompt's responses per AI platform, each response's citations
    (source URL + domain + position + context snippet), and crawled source
    metadata (JSON-LD types, extracted text, source-analysis scores). This is
    AEKO's "which competitors win this prompt and which sources AI engines
    cite" primitive — core input for `/aeko-prompt-deep-dive`,
    `/aeko-brand-competitor-analysis`, and content skills that mimic winning
    source structures.

    Args:
        prompt_id: UUID of the tracked prompt. Must be a prompt the current
            user has a UserPrompts row for (tracked or previously-tracked).
        window: `latest` (default) = most recent response per AI platform.
            `7d` / `30d` / `90d` = all responses in that window, newest first.
    """
    params: dict[str, Any] = {}
    if window:
        params["window"] = window
    data = client.get(f"/api/tracked-prompts/{prompt_id}", params=params)
    return _format_tracked_prompt_detail(data)


def _format_trend(value: float | None) -> str:
    if value is None:
        return "— (no prior data)"
    if value > 0:
        return f"+{value:.1f}% ↑"
    if value < 0:
        return f"{value:.1f}% ↓"
    return "0% →"


def _format_metrics(data: dict) -> str:
    lines = ["# Performance Metrics (Last 7 Days)", ""]

    lines.append("| Metric | Value | vs Previous 7 Days |")
    lines.append("|--------|-------|--------------------|")

    mentions = data.get("total_mentions", 0)
    citations = data.get("total_citations", 0)
    sentiment = data.get("avg_sentiment_score")
    visibility = data.get("avg_visibility_score")
    position = data.get("avg_position")
    share_pct = data.get("mention_share_pct")
    share_total = data.get("mention_share_total")

    lines.append(f"| Mentions | {mentions} | {_format_trend(data.get('mentions_diff'))} |")
    lines.append(f"| Citations | {citations} | {_format_trend(data.get('citations_diff'))} |")

    if sentiment is not None:
        lines.append(f"| Avg Sentiment | {sentiment:.1f}% | {_format_trend(data.get('sentiment_diff'))} |")

    if visibility is not None:
        lines.append(f"| Avg Visibility | {visibility:.1f} | {_format_trend(data.get('visibility_diff'))} |")

    if position is not None:
        lines.append(f"| Avg Position | {position:.1f} | — |")

    if share_pct is not None and share_total is not None:
        lines.append(f"| Mention Share | {share_pct:.1f}% ({share_total} tracked) | — |")

    lines.append("")

    current = data.get("data_points_current", 0)
    previous = data.get("data_points_previous", 0)
    lines.append(f"*Based on {current} data points (current) vs {previous} (previous period).*")

    return "\n".join(lines)


@mcp.tool(annotations=READ_ONLY)
def aeko_get_metrics(domain_id: str) -> str:
    """Get 7-day performance metrics with week-over-week trends.

    Shows total mentions, citations, average sentiment, visibility score,
    and mention share — each with percentage change vs the previous 7-day
    period. Use this to answer "am I improving?"

    Args:
        domain_id: UUID of the domain to analyze.
    """
    data = client.get("/api/tracked-prompts/metrics", params={"domain_id": domain_id})
    return _format_metrics(data)
