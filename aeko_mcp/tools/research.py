import re
import unicodedata
from typing import Any, Optional

from ..server import mcp, client
from ._annotations import READ_ONLY, WRITE


_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _normalize_prompt_text(s: str) -> str:
    # NFC + lowercase + drop punctuation + collapse whitespace. CJK
    # word characters are preserved by \w under re.UNICODE.
    if not s:
        return ""
    s = unicodedata.normalize("NFC", s).lower()
    s = re.sub(r"[^\w\s]", " ", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s).strip()
    return s


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

    lines.append("| # | ID | Prompt | Platform | Country | Status |")
    lines.append("|---|----|--------|----------|---------|--------|")

    for i, p in enumerate(data, 1):
        prompt_id = p.get("id", "N/A")
        prompt_text = p.get("prompt_en") or p.get("raw_prompt", "N/A")
        if len(prompt_text) > 60:
            prompt_text = prompt_text[:57] + "..."
        platform = PLATFORM_DISPLAY.get(p.get("ai_platform", ""), p.get("ai_platform", "N/A"))
        country = p.get("country", "N/A")
        status = p.get("status", "tracked")
        lines.append(f"| {i} | `{prompt_id}` | {prompt_text} | {platform} | {country} | {status} |")
        prompt_ko = p.get("prompt_ko")
        if prompt_ko:
            ko_text = (prompt_ko[:57] + "...") if len(prompt_ko) > 60 else prompt_ko
            lines.append(f"|   |   | *{ko_text}* |   |   |   |")

    lines.append("")
    lines.append("Pass an `ID` from the table to `aeko_get_tracked_prompt` for full forensics (cited sources, JSON-LD `@types`, citability scores).")
    lines.append("")

    return "\n".join(lines)


@mcp.tool(title="Search research prompts", annotations=READ_ONLY)
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


@mcp.tool(title="List tracked prompts", annotations=READ_ONLY)
def aeko_get_tracked_prompts() -> str:
    """List all prompts you are actively tracking.

    Shows your tracked prompts with their AI platform, country,
    and tracking status. These prompts are periodically re-queried
    to monitor changes in AI engine responses over time.
    """
    data = client.get("/api/tracked-prompts")
    return _format_tracked_prompts(data)


@mcp.tool(title="Resolve prompt texts to UUIDs", annotations=READ_ONLY)
def aeko_resolve_prompts_by_text(texts: list[str]) -> str:
    """Resolve raw prompt strings to tracked-prompt UUIDs.

    Use when a workflow (e.g. `/aeko-create-content`) receives
    `prompts_to_rank_on` entries as *text* (older Plan-builders,
    manually authored Plans) and needs UUIDs to pass to
    `aeko_get_tracked_prompt` for citation forensics. Replaces the
    fragile pattern of grep-parsing `aeko_get_tracked_prompts`
    markdown — that output renders `prompt_ko` on a separate row from
    the UUID, so cross-lang matches silently miss the ID column.

    Fetches the user's tracked prompts once and matches each input
    against `prompt_en`, `prompt_ko`, and `raw_prompt` after
    normalization (NFC, lowercase, strip punctuation, collapse
    whitespace). Inputs that already look like UUIDs are echoed back
    unchanged — safe to pass a mixed list straight from
    `frontmatter.prompts_to_rank_on`.

    Output is one line per input: ``"text" → `uuid` (matched_via: …)``
    or ``"text" → UNRESOLVED``. No table parsing required by callers.

    Args:
        texts: Prompt strings to resolve (raw text, UUID, or mixed).
    """
    if not texts:
        return "No input texts provided."

    data = client.get("/api/tracked-prompts")
    if not isinstance(data, list):
        return "Backend returned unexpected payload (expected a JSON list)."

    # {normalized_text: (uuid, matched_field)}. First non-empty match
    # wins so results are stable across calls; cross-row collisions on
    # the normalized form are rare.
    index: dict[str, tuple[str, str]] = {}
    no_id_count = 0
    for p in data:
        uuid = p.get("id")
        if not uuid:
            no_id_count += 1
            continue
        for field in ("prompt_en", "prompt_ko", "raw_prompt"):
            val = p.get(field)
            if not isinstance(val, str):
                continue
            key = _normalize_prompt_text(val)
            if key and key not in index:
                index[key] = (uuid, field)

    lines = ["# Prompt UUID resolution", ""]
    if no_id_count:
        lines.append(
            f"_Warning: {no_id_count} tracked-prompt row(s) returned "
            f"with no `id` field — backend issue, skipped._"
        )
        lines.append("")

    resolved = 0
    for text in texts:
        if not isinstance(text, str) or not text.strip():
            lines.append("- (empty input) → UNRESOLVED")
            continue
        stripped = text.strip()
        if _UUID_RE.match(stripped):
            lines.append(f"- `{stripped}` → already a UUID")
            resolved += 1
            continue
        key = _normalize_prompt_text(stripped)
        hit = index.get(key)
        if hit:
            uuid, field = hit
            lines.append(f'- "{stripped}" → `{uuid}` (matched_via: {field})')
            resolved += 1
        else:
            lines.append(f'- "{stripped}" → UNRESOLVED')

    lines.append("")
    lines.append(f"Resolved {resolved}/{len(texts)}.")
    return "\n".join(lines)


@mcp.tool(title="Track a prompt", annotations=WRITE)
def aeko_track_prompt(
    raw_prompt: str,
    ai_platform: str,
    prompt_en: Optional[str] = None,
    country: Optional[str] = None,
    # Search-row metadata accepted for convenience (so a caller can pass a whole
    # aeko_search_research_prompts row unchanged) but NOT persisted — the backend derives
    # classification server-side. Kept in the signature so existing callers don't error.
    prompt_ko: Optional[str] = None,
    model: Optional[str] = None,
    language: Optional[str] = None,
    industry: Optional[str] = None,
    vertical: Optional[str] = None,
    persona: Optional[str] = None,
    icp: Optional[str] = None,
    context: Optional[Any] = None,
    tags: Optional[Any] = None,
) -> str:
    """Start tracking a prompt so AEKO re-queries it across AI engines.

    Use after `aeko_search_research_prompts` to pick a research prompt to
    track — pass the same `raw_prompt` / `ai_platform` / `country` that the
    search surfaced. Creates a user-owned tracked-prompt row that AEKO's
    pipeline will re-query on cadence so you can watch how AI responses
    shift over time. Only `raw_prompt`/`ai_platform`/`prompt_en`/`country` are
    persisted; extra search-row metadata (prompt_ko, model, industry, persona,
    tags, …) is accepted for convenience but IGNORED — the backend derives
    classification server-side.

    Idempotent: tracking a prompt you already track returns HTTP 201 with
    a per-result status of `already_tracked` (NOT a 409); tracking one you
    previously untracked reactivates it (`reactivated`). Package limits
    (max tracked prompts, max markets) apply and surface as a `failed`
    result with a reason.

    Args:
        raw_prompt: The prompt text to track (required).
        ai_platform: Target AI engine — `openai`, `anthropic`, `google`, or
            `perplexity` (required).
        prompt_en: Optional pre-translated English form.
        country: ISO-3166 country code (must be in your account's
            selected_markets). Defaults to your first selected market.
    """
    body: dict[str, Any] = {
        "raw_prompt": raw_prompt,
        "ai_platform": ai_platform,
    }
    if prompt_en is not None:
        body["prompt_en"] = prompt_en
    if country is not None:
        body["country"] = country

    # POST /api/tracked-prompts returns 201 with a BulkTrackResponse:
    # {results: [{seed_index, item_id, ai_platform, country, status,
    #             tracked_prompt_id, reason}], summary: {...}}.
    # A single-prompt call yields exactly one result row.
    resp = client.post("/api/tracked-prompts", json=body)
    results = resp.get("results") or []
    summary = resp.get("summary") or {}

    if not results:
        return (
            "Track request returned no results — backend accepted the call "
            f"but reported nothing for this prompt. Summary: {summary or 'N/A'}"
        )

    result = results[0]
    status_val = result.get("status", "unknown")
    prompt_id = result.get("tracked_prompt_id") or "?"
    display = (prompt_en or raw_prompt)[:120]

    summary_bits = []
    for key in ("tracked", "reactivated", "associated", "already_tracked"):
        count = summary.get(key)
        if count:
            summary_bits.append(f"{key}={count}")
    summary_str = f" [{', '.join(summary_bits)}]" if summary_bits else ""

    if status_val in ("tracked", "reactivated", "associated"):
        return f"Tracked prompt `{prompt_id}` ({status_val}): {display}{summary_str}"
    if status_val == "already_tracked":
        return (
            f"Prompt already tracked as `{prompt_id}` — no new row created: "
            f"{display}{summary_str}"
        )
    reason = result.get("reason") or "no reason given"
    return f"Tracking failed ({status_val}): {reason} — prompt: {display}{summary_str}"


@mcp.tool(title="Untrack a prompt", annotations=WRITE)
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

        # Prefer the full response body over the snippet; fall back to the
        # snippet so we degrade gracefully when the full body is absent.
        # The skill's structural mimicry needs the surrounding text where
        # citations appear, not just a 300-char teaser.
        #
        # Canonical backend field is `full_response` (see
        # TrackedPromptResponseItem in aeko_backend api/routes/main.py),
        # alongside `response_snippet` / `response_snippet_en`.
        # `response_body_en` is kept only as a secondary alias for any
        # transitional payloads.
        body = resp.get("full_response") or resp.get("response_body_en")
        snippet = resp.get("response_snippet_en") or resp.get("response_snippet")
        display = body or snippet
        if display:
            label = "Response body" if body else "Snippet"
            cap = 2500
            trimmed = display if len(display) <= cap else display[: cap - 3] + "..."
            lines.append(f"- **{label}**: {trimmed}")

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
                    # Surface a slice of crawl.extracted_text so the skill can
                    # tone-match against the cited source body. Cap at 600
                    # chars per citation to keep the rendered payload bounded
                    # when many citations land on one prompt.
                    extracted = crawl.get("extracted_text")
                    if isinstance(extracted, str) and extracted.strip():
                        ex_cap = 600
                        ex_trim = (
                            extracted
                            if len(extracted) <= ex_cap
                            else extracted[: ex_cap - 3] + "..."
                        )
                        ex_oneline = " ".join(ex_trim.split())
                        lines.append(f"    • Extracted: {ex_oneline}")

        lines.append("")

    return "\n".join(lines)


@mcp.tool(title="Get tracked prompt details", annotations=READ_ONLY)
def aeko_get_tracked_prompt(
    prompt_id: str,
    window: Optional[str] = None,
) -> str:
    """Full citation-forensics payload for one tracked prompt.

    Returns the prompt's responses per AI platform — each response renders the
    full body (backend field `full_response`; falls back to the 300-char
    snippet when absent) plus its citations: source URL + domain + position
    + context snippet, and crawled source metadata (JSON-LD `@type` list,
    extracted body text, source-analysis citability score). This is AEKO's
    "which competitors win this prompt and which sources AI engines cite"
    primitive — core input for `/aeko-prompt-deep-dive`,
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


