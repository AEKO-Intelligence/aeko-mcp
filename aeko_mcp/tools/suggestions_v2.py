"""Suggestion v2 — categorized, rich-brief suggestions.

Backs the 4-category action model:
  1. pdp_update        — Own Store · Product Detail Update
  2. own_content       — Own Store · Content (blog/article/FAQ on own domain)
  3. external_content  — Other Media · Content (partner media, Wikipedia, guest posts)
  4. store_level       — Own Store · Store-Level (llms.txt, robots.txt, sitemap, infra)

These tools consume a forward-looking backend contract (see plan). When the
backend endpoints are not yet available the tools surface a clear message so
Claude can gracefully tell the user what's missing.
"""

from ..server import mcp, client


CATEGORY_LABELS = {
    "pdp_update": "Own Store · Product Detail Update",
    "own_content": "Own Store · Content",
    "external_content": "Other Media · Content",
    "store_level": "Own Store · Store-Level",
}

CATEGORY_SKILL = {
    "pdp_update": "aeko-update-pdp",
    "own_content": "aeko-create-own-content",
    "external_content": "aeko-create-external-content",
    "store_level": "aeko-fix-store-level",
}

PRIORITY_ORDER = ["critical", "high", "medium", "low"]


def _safe_get(path: str, params: dict | None = None) -> tuple[dict | None, str | None]:
    """Call client.get and convert any error into (None, message) instead of raising.

    Catches broadly on purpose: the v2 endpoints may not exist yet, and we want
    graceful markdown fallbacks instead of stack traces. This covers
    client.get's RuntimeError, any uncaught httpx errors (timeouts, protocol
    errors), and JSON decode failures on non-JSON 200 responses.

    TODO: Once the v2 backend is live and stable, narrow this to RuntimeError
    so real 5xx failures are not masked as "endpoint missing."
    """
    try:
        return client.get(path, params=params), None
    except Exception as e:  # noqa: BLE001 — intentional broad catch, see docstring
        return None, f"{type(e).__name__}: {e}"


def _render_suggestion(s: dict, index: int | None = None) -> list[str]:
    lines: list[str] = []
    title = s.get("title") or "Suggestion"
    prefix = f"{index}. " if index is not None else ""
    lines.append(f"### {prefix}{title}")

    key = s.get("key")
    if key:
        lines.append(f"- **Key**: `{key}`")

    domain_id = s.get("domain_id")
    if domain_id:
        lines.append(f"- **Domain ID**: `{domain_id}`")

    priority = s.get("priority")
    if priority:
        lines.append(f"- **Priority**: {priority}")

    rationale = s.get("rationale") or s.get("description")
    if rationale:
        lines.append(f"- **Why**: {rationale}")

    brief = s.get("brief") or {}
    if brief:
        if brief.get("target_domain"):
            lines.append(f"- **Target domain**: {brief['target_domain']}")
        if brief.get("target_url"):
            lines.append(f"- **Target URL**: {brief['target_url']}")
        if brief.get("content_type"):
            lines.append(f"- **Content type**: {brief['content_type']}")
        if brief.get("persona"):
            lines.append(f"- **Persona**: {brief['persona']}")
        if brief.get("tone"):
            lines.append(f"- **Tone**: {brief['tone']}")
        if brief.get("word_count_target"):
            lines.append(f"- **Word count target**: {brief['word_count_target']}")
        structure = brief.get("structure") or []
        if structure:
            lines.append(f"- **Structure**: {' → '.join(structure)}")
        topics = brief.get("topics") or []
        if topics:
            lines.append(f"- **Topics**: {', '.join(topics)}")
        required_jsonld = brief.get("required_jsonld") or []
        if required_jsonld:
            lines.append(f"- **Required JSON-LD**: {', '.join(required_jsonld)}")
        must_include = brief.get("must_include") or []
        if must_include:
            lines.append(f"- **Must include**: {', '.join(must_include)}")

    prompt_ids = s.get("prompt_ids") or []
    if prompt_ids:
        lines.append(f"- **Driven by prompts**: {len(prompt_ids)}")

    group_id = s.get("group_id")
    if group_id:
        lines.append(f"- **Prompt group**: `{group_id}`")

    evidence = s.get("source_evidence") or []
    if evidence:
        lines.append(f"- **Competitor evidence** ({len(evidence)} source(s)):")
        for ev in evidence[:5]:
            url = ev.get("url", "")
            headline = ev.get("headline", "")
            structure = ev.get("structure") or []
            jsonld = ev.get("jsonld_types") or []
            bits: list[str] = []
            if structure:
                bits.append("structure=" + "/".join(structure))
            if jsonld:
                bits.append("jsonld=" + ",".join(jsonld))
            suffix = f" ({'; '.join(bits)})" if bits else ""
            if headline:
                lines.append(f"  - [{headline}]({url}){suffix}")
            else:
                lines.append(f"  - {url}{suffix}")

    skill_hint = s.get("mcp_skill_hint")
    if skill_hint:
        lines.append(f"- **Skill**: `/{skill_hint}`")

    tool_hints = s.get("mcp_tool_hints") or []
    if tool_hints:
        lines.append(f"- **Tools**: {', '.join(tool_hints)}")

    metadata = s.get("metadata") or {}
    if metadata.get("ai_readiness_score") is not None:
        lines.append(f"- **AI-readiness**: {metadata['ai_readiness_score']}/100")
    if metadata.get("expected_impact"):
        lines.append(f"- **Expected impact**: {metadata['expected_impact']}")

    lines.append("")
    return lines


def _render_category(category: str, items: list[dict]) -> list[str]:
    lines: list[str] = []
    label = CATEGORY_LABELS.get(category, category)
    skill = CATEGORY_SKILL.get(category)
    header = f"## {label}"
    if skill:
        header += f"  ·  `/{skill}`"
    lines.append(header)
    lines.append("")
    if not items:
        lines.append("_No suggestions in this category._")
        lines.append("")
        return lines

    # sort by priority
    def _p_rank(s: dict) -> int:
        p = s.get("priority")
        return PRIORITY_ORDER.index(p) if p in PRIORITY_ORDER else len(PRIORITY_ORDER)

    for i, s in enumerate(sorted(items, key=_p_rank), 1):
        lines.extend(_render_suggestion(s, i))
    return lines


@mcp.tool()
def aeko_get_suggestions_v2(
    domain_id: str,
    category: str = "",
    group_id: str = "",
    priority: str = "",
) -> str:
    """Fetch categorized, rich-brief optimization suggestions for a domain.

    Returns suggestions organized into 4 action categories:
      - pdp_update:        Own Store · Product Detail Update
      - own_content:       Own Store · Content (blog/article/FAQ)
      - external_content:  Other Media · Content (partner media, Wikipedia)
      - store_level:       Own Store · Store-Level (llms.txt, robots.txt, sitemap)

    Each suggestion includes a rich brief with target domain/URL, structure,
    topics, persona, tone, and required JSON-LD — produced by scheduled backend
    jobs that analyze tracked prompts and scrape winning source URLs.

    Args:
        domain_id: UUID of the domain.
        category:  Optional filter — one of pdp_update, own_content, external_content, store_level.
        group_id:  Optional prompt-group UUID to narrow suggestions to a specific prompt group.
        priority:  Optional filter — one of critical, high, medium, low.
    """
    params: dict = {"domain_id": domain_id}
    if category:
        params["category"] = category
    if group_id:
        params["group_id"] = group_id
    if priority:
        params["priority"] = priority

    data, err = _safe_get("/api/suggestions/v2", params=params)
    if err:
        return (
            "# Suggestions v2 unavailable\n\n"
            f"Could not reach the v2 suggestions endpoint: {err}\n\n"
            "The backend may not yet implement `/api/suggestions/v2`. "
            "Fall back to `aeko_get_suggestions(domain_id)` for the legacy flat list."
        )

    categories = (data or {}).get("categories") or {}
    # If backend returned a flat list under "suggestions" (filtered call), group it.
    if not categories and isinstance(data, dict) and data.get("suggestions"):
        bucket: dict[str, list[dict]] = {k: [] for k in CATEGORY_LABELS}
        for s in data["suggestions"]:
            c = s.get("category") or "store_level"
            bucket.setdefault(c, []).append(s)
        categories = bucket

    if not categories:
        return "No v2 suggestions returned. The backend may still be generating briefs for this domain."

    total = sum(len(v) for v in categories.values())
    lines = [
        "# AEKO Optimization Suggestions (v2)",
        "",
        f"Domain: `{domain_id}`  ·  {total} suggestion(s) across {len([k for k,v in categories.items() if v])} categories.",
        "",
    ]
    for cat in ["pdp_update", "own_content", "external_content", "store_level"]:
        lines.extend(_render_category(cat, categories.get(cat) or []))

    # Include any unknown categories at the end
    for cat, items in categories.items():
        if cat not in CATEGORY_LABELS:
            lines.extend(_render_category(cat, items))

    return "\n".join(lines)


@mcp.tool()
def aeko_get_suggestion(suggestion_key: str) -> str:
    """Hydrate a single v2 suggestion with its full brief and source evidence.

    Use this when a skill needs the complete content brief for one suggestion —
    including competitor source structures, prompt linkages, persona, and the
    required JSON-LD schema types.

    Args:
        suggestion_key: Unique key of the suggestion (from aeko_get_suggestions_v2).
    """
    data, err = _safe_get(f"/api/suggestions/v2/{suggestion_key}")
    if err:
        return f"Could not fetch suggestion `{suggestion_key}`: {err}"
    if not data:
        return f"Suggestion `{suggestion_key}` not found."

    category = data.get("category") or "unknown"
    lines = [
        f"# Suggestion · {CATEGORY_LABELS.get(category, category)}",
        "",
    ]
    lines.extend(_render_suggestion(data))
    return "\n".join(lines)


@mcp.tool()
def aeko_list_prompt_groups(domain_id: str) -> str:
    """List prompt groups defined for a domain.

    Prompt groups let users cluster tracked prompts by intent (e.g. "mattress
    category", "return policy questions") so suggestions can be scoped to the
    group the user cares about right now.

    Args:
        domain_id: UUID of the domain.
    """
    data, err = _safe_get("/api/prompt-groups", params={"domain_id": domain_id})
    if err:
        return (
            "# Prompt groups unavailable\n\n"
            f"Could not reach `/api/prompt-groups`: {err}\n\n"
            "Prompt groups may not yet be implemented on the backend."
        )

    groups = data if isinstance(data, list) else (data or {}).get("groups", [])
    if not groups:
        return "No prompt groups defined for this domain yet."

    lines = ["# Prompt Groups", ""]
    for g in groups:
        name = g.get("name") or "(unnamed)"
        gid = g.get("id", "")
        count = g.get("prompt_count")
        scope = g.get("scope") or ""
        line = f"- **{name}** · `{gid}`"
        if count is not None:
            line += f" · {count} prompts"
        if scope:
            line += f" · scope: {scope}"
        lines.append(line)
    return "\n".join(lines)


def _wrap_brief(suggestion_key: str, extras_renderer) -> str:
    """Shared brief helper — fetches the suggestion then appends extras."""
    data, err = _safe_get(f"/api/suggestions/v2/{suggestion_key}")
    if err:
        return f"Could not fetch suggestion `{suggestion_key}`: {err}"
    if not data:
        return f"Suggestion `{suggestion_key}` not found."

    lines = [f"# Brief · `{suggestion_key}`", ""]
    lines.extend(_render_suggestion(data))

    extras = extras_renderer(data) or []
    if extras:
        lines.append("---")
        lines.append("")
        lines.extend(extras)
    return "\n".join(lines)


@mcp.tool()
def aeko_get_pdp_brief(suggestion_key: str, domain_id: str = "") -> str:
    """Get a full product-detail-page rewrite brief for a suggestion.

    Combines the suggestion's brief with the current page analysis and
    citability score for `brief.target_url`, so Claude can rewrite the PDP
    with full context of what's missing and which competitor structures to
    mirror.

    Args:
        suggestion_key: Unique key of a `pdp_update` suggestion.
        domain_id:      Optional domain UUID override. Pass this if the
                        suggestion payload doesn't include `domain_id` (it is
                        needed to fetch the current page analysis). If empty,
                        the tool will try `data.domain_id` from the response.
    """
    def extras(data: dict) -> list[str]:
        out: list[str] = []
        brief = data.get("brief") or {}
        target_url = brief.get("target_url")
        domain_id_resolved = domain_id or data.get("domain_id")

        if domain_id_resolved and target_url:
            page_data, page_err = _safe_get(
                "/api/store-pages/analysis",
                params={"domain_id": domain_id_resolved, "url": target_url},
            )
            if page_err:
                out.append(f"_Current page analysis unavailable: {page_err}_")
            elif page_data:
                out.append("## Current page analysis")
                out.append("")
                pages = page_data if isinstance(page_data, list) else page_data.get("pages", [page_data])
                for p in pages[:1]:
                    score = p.get("ai_readiness_score")
                    if score is not None:
                        out.append(f"- AI-readiness score: {score}/100")
                    if p.get("has_product_jsonld") is not None:
                        out.append(f"- Has Product JSON-LD: {p['has_product_jsonld']}")
                    issues = (p.get("analysis_result") or {}).get("issues") or []
                    if issues:
                        out.append("- Top issues:")
                        for issue in issues[:5]:
                            out.append(f"  - {issue}")
                out.append("")

        source_id = (data.get("metadata") or {}).get("source_id")
        if source_id:
            cit_data, cit_err = _safe_get("/api/citability/page", params={"source_id": source_id})
            if cit_err:
                out.append(f"_Citability unavailable: {cit_err}_")
                out.append("")
            elif cit_data:
                out.append("## Citability")
                out.append(f"- Overall: {cit_data.get('overall', 'n/a')}/100")
                for imp in (cit_data.get("top_improvements") or [])[:5]:
                    out.append(f"  - {imp}")
                out.append("")
        return out

    return _wrap_brief(suggestion_key, extras)


@mcp.tool()
def aeko_get_content_brief(suggestion_key: str) -> str:
    """Get a content-creation brief for own-content or external-content suggestions.

    Returns the suggestion's brief plus supporting tracked-prompt context so
    Claude can write an article that matches how real users query AI engines.

    Args:
        suggestion_key: Unique key of an `own_content` or `external_content` suggestion.
    """
    def extras(data: dict) -> list[str]:
        out: list[str] = []
        prompt_ids = data.get("prompt_ids") or []
        if not prompt_ids:
            return out
        out.append("## Supporting tracked prompts")
        out.append("")
        out.append(f"{len(prompt_ids)} tracked prompt(s) drove this suggestion. ")
        out.append("Call `aeko_search_research_prompts` with the group scope to see the prompt text and latest AI responses for background.")
        out.append("")
        return out

    return _wrap_brief(suggestion_key, extras)


@mcp.tool()
def aeko_get_store_level_brief(suggestion_key: str) -> str:
    """Get a store-level-fix brief (llms.txt, robots.txt, sitemap, schema infra).

    Returns the suggestion's brief and reminds the caller which existing
    preparation tools to chain (`aeko_prepare_llms_txt`,
    `aeko_prepare_robots_txt_fix`, `aeko_prepare_json_ld`).

    Args:
        suggestion_key: Unique key of a `store_level` suggestion.
    """
    def extras(data: dict) -> list[str]:
        brief = data.get("brief") or {}
        raw_ct = brief.get("content_type") or ""
        content_type = raw_ct.lower().replace("-", "_").replace(".", "_")
        out = ["## Recommended chain", ""]
        if content_type == "llms_txt":
            out.append("1. `aeko_prepare_llms_txt(domain_id)` — gather domain + page data")
            out.append("2. Draft `llms.txt` following the llms.txt spec")
            out.append("3. `aeko_validate_llms_txt(url)` once deployed")
        elif content_type == "robots_txt":
            out.append("1. Read the current `robots.txt` from the target domain")
            out.append("2. `aeko_prepare_robots_txt_fix(domain_id, current_robots_txt)`")
            out.append("3. Apply the recommended snippet")
        elif content_type == "sitemap":
            out.append("1. Inspect current sitemap state via `aeko_get_domain_info(domain_id)`")
            out.append("2. Generate/repair sitemap.xml based on the brief's `structure`")
        else:
            out.append("1. `aeko_prepare_json_ld(domain_id, schema_type)` for schema-infra fixes")
        out.append("")
        out.append("Finish with `aeko_save_content(...)` then `aeko_complete_suggestion(suggestion_key)`.")
        return out

    return _wrap_brief(suggestion_key, extras)
