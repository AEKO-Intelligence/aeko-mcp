"""Content Recommendations MCP tools.

Persona-driven content recommendations scoped to a Campaign. The recommender
detects "this campaign's tracked prompts have a persona segment where the
brand is weak relative to top-3 competitors" and emits up to 10 active
recommendations per campaign with curated competitor source URLs the MCP
plugin should draw from when drafting.

Tier-gated to Growth+ (matches /api/personas via the same FEATURE_ACCESS
flag). Starter users get 403 from the backend.

Backend contract: Phase 3 of the Campaigns plan
  GET    /api/campaigns/{id}/content-recommendations
  POST   /api/campaigns/{id}/content-recommendations/regenerate
  GET    /api/content-recommendations/{id}
  POST   /api/content-recommendations/{id}/dismiss
  POST   /api/content-recommendations/{id}/complete
  GET    /api/sources/content?url=...
"""

from ..server import mcp, client


def _safe(method, *args, **kwargs) -> tuple[dict | None, str | None]:
    try:
        return method(*args, **kwargs), None
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


def _format_weakness(signal: dict) -> str:
    """One-line summary of a PersonaGapSignal."""
    bv = signal.get("brand_visibility", 0)
    cv = signal.get("top_3_competitor_visibility", 0)
    gap = signal.get("gap_pct", 0)
    n = signal.get("n_responses", 0)
    competitors = ", ".join(signal.get("competitors", [])[:3]) or "—"
    return (
        f"Brand visibility {bv:.1f} vs top-3 competitor avg {cv:.1f} "
        f"(gap {gap*100:.0f}%, {n} responses). Competitors: {competitors}"
    )


def _format_recommendation(rec: dict, index: int | None = None) -> list[str]:
    """Render one ContentRecommendationItem as markdown lines."""
    lines: list[str] = []
    label = rec.get("cluster_label", "Untitled cluster")
    persona = rec.get("persona_label_en") or rec.get("persona_type") or "—"
    prefix = f"{index}. " if index is not None else ""
    lines.append(f"### {prefix}{label} · {persona}")
    lines.append(f"- **Recommendation ID**: `{rec.get('id', '')}`")

    signal = rec.get("weakness_signal") or {}
    if signal:
        lines.append(f"- **Why**: {_format_weakness(signal)}")

    channels = rec.get("suggested_channels") or []
    if channels:
        lines.append(
            f"- **Suggested channels**: {channels[0]}"
            + (
                f" (alternatives: {', '.join(channels[1:])})"
                if len(channels) > 1
                else ""
            )
        )

    sources = rec.get("curated_sources") or []
    if sources:
        lines.append(f"- **Curated sources**: {len(sources)} competitor URLs")
        for s in sources[:3]:
            url = s.get("url", "")
            why = s.get("why_relevant", "")
            lines.append(f"  - {url} — {why}")
        if len(sources) > 3:
            lines.append(f"  - …and {len(sources) - 3} more")

    brief = rec.get("draft_brief") or {}
    if brief:
        if brief.get("primary_channel"):
            lines.append(f"- **Primary channel**: {brief['primary_channel']}")
        if brief.get("word_count_target"):
            lines.append(f"- **Word count target**: {brief['word_count_target']}")
        if brief.get("required_jsonld"):
            lines.append(
                f"- **Required JSON-LD**: {', '.join(brief['required_jsonld'])}"
            )
    return lines


@mcp.tool()
def aeko_get_content_recommendations(campaign_id: str) -> str:
    """List active content recommendations for a campaign.

    Each recommendation is anchored to a persona segment where the brand
    is weak vs competitors, and includes curated competitor URLs the MCP
    plugin should fetch via aeko_fetch_source_content when drafting.

    Tier-gated: returns an error message if the user is on a tier that
    doesn't include Content Recommendations (Growth+ required).

    Args:
        campaign_id: UUID of the campaign

    Returns:
        Markdown list of active recommendations.
    """
    resp, err = _safe(
        client.get, f"/api/campaigns/{campaign_id}/content-recommendations"
    )
    if err:
        return (
            f"# Content Recommendations\n\nCould not load recommendations for "
            f"campaign `{campaign_id}`: {err}"
        )

    recs = (resp or {}).get("recommendations", [])
    if not recs:
        return (
            f"# Content Recommendations for campaign `{campaign_id}`\n\n"
            "No active recommendations. This usually means one of:\n"
            "- The campaign has no member prompts yet — add some via the dashboard.\n"
            "- The campaign's prompts haven't accumulated enough mention metrics yet "
            "(wait for the next AI refresh).\n"
            "- The brand is keeping up with competitors across all persona segments "
            "(no gaps detected).\n\n"
            "You can manually trigger a fresh regeneration by calling "
            "`aeko_regenerate_content_recommendations(campaign_id)` "
            "(rate-limited to 1/hour)."
        )

    lines = [f"# Content Recommendations for campaign `{campaign_id}`", ""]
    lines.append(f"**{len(recs)} active recommendation(s)**")
    lines.append("")
    for i, rec in enumerate(recs, 1):
        lines.extend(_format_recommendation(rec, index=i))
        lines.append("")

    lines.append("---")
    lines.append(
        "💡 To draft content for one of these, use the `/aeko-draft-from-campaign` "
        "skill (or call `aeko_get_content_recommendation(recommendation_id)` for the "
        "full brief, then `aeko_fetch_source_content(url)` for each curated source URL)."
    )
    return "\n".join(lines)


@mcp.tool()
def aeko_get_content_recommendation(recommendation_id: str) -> str:
    """Get full detail for one content recommendation.

    Returns the complete draft_brief, all curated source URLs with key
    excerpts, and the persona gap signal that triggered it.

    Args:
        recommendation_id: UUID of the content recommendation

    Returns:
        Markdown detail. Use the curated source URLs with
        aeko_fetch_source_content to load full page text for drafting.
    """
    resp, err = _safe(
        client.get, f"/api/content-recommendations/{recommendation_id}"
    )
    if err:
        return f"# Content Recommendation\n\nCould not load: {err}"

    if not resp:
        return f"# Content Recommendation `{recommendation_id}`\n\nNot found."

    lines = ["# Content Recommendation Detail", ""]
    lines.extend(_format_recommendation(resp))
    lines.append("")

    brief = resp.get("draft_brief") or {}
    if brief:
        lines.append("## Draft Brief")
        if brief.get("topics"):
            lines.append(f"- **Topics**: {', '.join(brief['topics'])}")
        if brief.get("structure"):
            lines.append(f"- **Structure spine**: {' → '.join(brief['structure'])}")
        if brief.get("tone"):
            lines.append(f"- **Tone**: {brief['tone']}")
        if brief.get("must_include"):
            lines.append("- **Must include**:")
            for m in brief["must_include"]:
                lines.append(f"  - {m}")
        lines.append("")

    sources = resp.get("curated_sources") or []
    if sources:
        lines.append(f"## Curated Sources ({len(sources)})")
        lines.append("")
        for i, s in enumerate(sources, 1):
            url = s.get("url", "")
            lines.append(f"### Source {i}: {url}")
            if s.get("source_type"):
                lines.append(f"- **Type**: {s['source_type']}")
            if s.get("headline"):
                lines.append(f"- **Headline**: {s['headline']}")
            if s.get("structure"):
                lines.append(f"- **Structure**: {' → '.join(s['structure'])}")
            if s.get("jsonld_types"):
                lines.append(f"- **JSON-LD**: {', '.join(s['jsonld_types'])}")
            if s.get("why_relevant"):
                lines.append(f"- **Why relevant**: {s['why_relevant']}")
            if s.get("key_excerpt"):
                excerpt = s["key_excerpt"][:300]
                lines.append(f"- **Excerpt**: {excerpt}…")
            lines.append("")

    lines.append("---")
    lines.append(
        "💡 To draft from this: call `aeko_fetch_source_content(url)` for each "
        "curated source above, then write the draft following the structure spine "
        "and must_include checklist. Mark complete with "
        f"`aeko_complete_content_recommendation('{resp.get('id', '')}')`."
    )
    return "\n".join(lines)


@mcp.tool()
def aeko_dismiss_content_recommendation(recommendation_id: str) -> str:
    """Dismiss a content recommendation.

    Frees the slot in the per-campaign cap (max 10 active) so the next
    regeneration can surface a different one.

    Args:
        recommendation_id: UUID of the content recommendation

    Returns:
        Markdown confirmation.
    """
    resp, err = _safe(
        client.post, f"/api/content-recommendations/{recommendation_id}/dismiss"
    )
    if err:
        return f"# Dismiss failed\n\n{err}"
    return (
        f"# Recommendation dismissed\n\n"
        f"`{resp.get('recommendation_id', recommendation_id)}` is now dismissed. "
        f"The slot is freed for the next regeneration."
    )


@mcp.tool()
def aeko_complete_content_recommendation(recommendation_id: str) -> str:
    """Mark a content recommendation as completed (e.g., the user published the draft).

    Frees the slot in the per-campaign cap so the next regeneration can
    surface a different one.

    Args:
        recommendation_id: UUID of the content recommendation

    Returns:
        Markdown confirmation.
    """
    resp, err = _safe(
        client.post,
        f"/api/content-recommendations/{recommendation_id}/complete",
    )
    if err:
        return f"# Complete failed\n\n{err}"
    return (
        f"# Recommendation completed ✅\n\n"
        f"`{resp.get('recommendation_id', recommendation_id)}` is marked as completed. "
        f"The slot is freed for the next regeneration."
    )


@mcp.tool()
def aeko_regenerate_content_recommendations(campaign_id: str) -> str:
    """Manually regenerate content recommendations for a campaign.

    Rate-limited to 1 call per hour per campaign. The recommender is
    idempotent — same data → same recommendations (UPSERT-by-cluster_hash),
    so calling this when nothing has changed returns the same active list.

    Args:
        campaign_id: UUID of the campaign

    Returns:
        Markdown summary of created/updated/skipped counts + the active list.
    """
    resp, err = _safe(
        client.post,
        f"/api/campaigns/{campaign_id}/content-recommendations/regenerate",
    )
    if err:
        return f"# Regeneration failed\n\n{err}"

    if not resp:
        return f"# Regeneration\n\nNo response from backend."

    created = resp.get("created", 0)
    updated = resp.get("updated", 0)
    skipped = resp.get("skipped_cap_full", 0)

    lines = [f"# Regenerated content recommendations for `{campaign_id}`", ""]
    lines.append(f"- **Created**: {created} new recommendation(s)")
    lines.append(f"- **Updated**: {updated} existing recommendation(s)")
    if skipped > 0:
        lines.append(
            f"- **Skipped (cap full)**: {skipped} candidate(s) dropped because "
            f"the per-campaign cap of 10 is full. Dismiss or complete some "
            f"existing recommendations to free slots."
        )
    lines.append("")

    recs = resp.get("recommendations", [])
    if recs:
        lines.append(f"## Active list ({len(recs)})")
        lines.append("")
        for i, rec in enumerate(recs, 1):
            lines.extend(_format_recommendation(rec, index=i))
            lines.append("")
    return "\n".join(lines)


@mcp.tool()
def aeko_fetch_source_content(url: str) -> str:
    """Fetch the full content of a previously-crawled source URL.

    Used when drafting from a content recommendation — Claude calls this
    for each curated source URL to read the actual page text and mirror
    its structure. Capped at 12KB per source to keep the MCP payload sane.

    Returns 404 if the URL has not been crawled (no on-demand fetch). Growth+
    tier-gated like the rest of the Content Recommendations surface.

    Args:
        url: Canonical URL of the source (from curated_sources[].url)

    Returns:
        Markdown with the page's title, headings, JSON-LD types, and
        extracted text (capped at 12KB).
    """
    resp, err = _safe(client.get, "/api/sources/content", params={"url": url})
    if err:
        return f"# Source content\n\nCould not fetch `{url}`: {err}"

    if not resp:
        return f"# Source content\n\nNot found: `{url}`"

    lines = [f"# Source: {resp.get('title') or url}", ""]
    lines.append(f"- **URL**: {resp.get('url', url)}")
    if resp.get("meta_description"):
        lines.append(f"- **Description**: {resp['meta_description']}")
    if resp.get("crawled_at"):
        lines.append(f"- **Crawled at**: {resp['crawled_at']}")
    if resp.get("jsonld_types"):
        lines.append(f"- **JSON-LD types**: {', '.join(resp['jsonld_types'])}")
    if resp.get("truncated"):
        lines.append(
            "- **Note**: Content was truncated to 12KB. Full page is longer."
        )
    lines.append("")

    headings = resp.get("headings") or []
    if headings:
        lines.append("## Structure")
        for h in headings[:30]:
            lines.append(f"- {h}")
        lines.append("")

    text = resp.get("extracted_text") or ""
    if text:
        lines.append("## Extracted text")
        lines.append("```")
        lines.append(text)
        lines.append("```")
    return "\n".join(lines)
