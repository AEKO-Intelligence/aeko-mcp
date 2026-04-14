"""Campaign CRUD MCP tools.

Campaigns are AEKO's central organizing primitive — product-level
optimization initiatives that group tracked prompts (e.g., "Mattress
Optimize Campaign", "Curtain Optimize Campaign"). Each campaign scopes
v2 fixes via campaign_id and gets persona-driven Content Recommendations
generated per-campaign.

Backed by /api/campaigns CRUD endpoints (Phase 1 of the Campaigns plan).
"""

from ..server import mcp, client


def _safe(method, *args, **kwargs) -> tuple[dict | None, str | None]:
    """Wrap a client call. Returns (response, error_msg). Same pattern as suggestions_v2."""
    try:
        return method(*args, **kwargs), None
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


def _format_campaign(c: dict) -> list[str]:
    """Render a single campaign row as markdown lines."""
    lines: list[str] = []
    name = c.get("name", "Untitled")
    lines.append(f"### {name}")
    lines.append(f"- **ID**: `{c.get('id', '')}`")
    if c.get("product_label"):
        lines.append(f"- **Product**: {c['product_label']}")
    if c.get("status"):
        lines.append(f"- **Status**: {c['status']}")
    if c.get("description"):
        lines.append(f"- **Description**: {c['description']}")
    lines.append(f"- **Tracked prompts**: {c.get('prompt_count', 0)}")
    lines.append(
        f"- **Active content recommendations**: {c.get('content_recommendation_count', 0)}"
    )
    if c.get("created_at"):
        lines.append(f"- **Created**: {c['created_at']}")
    if c.get("completed_at"):
        lines.append(f"- **Completed**: {c['completed_at']}")
    return lines


@mcp.tool()
def aeko_list_campaigns(domain_id: str, status: str | None = None) -> str:
    """List campaigns for a domain.

    Args:
        domain_id: UUID of the AEKO domain
        status: Optional filter — one of "active", "completed", "archived"

    Returns:
        Markdown list of campaigns with prompt counts and recommendation counts.
        Each campaign has an ID you can pass to aeko_get_campaign or
        aeko_get_content_recommendations.
    """
    params: dict = {"domain_id": domain_id}
    if status:
        params["status"] = status

    resp, err = _safe(client.get, "/api/campaigns", params=params)
    if err:
        return f"# Campaigns\n\nCould not load campaigns: {err}"

    campaigns = (resp or {}).get("campaigns", [])
    if not campaigns:
        return (
            f"# Campaigns for domain `{domain_id}`\n\n"
            "No campaigns yet. Create one with `aeko_create_campaign` to start "
            "scoping tracked prompts and generating content recommendations."
        )

    lines = [f"# Campaigns for domain `{domain_id}`", ""]
    lines.append(f"**{len(campaigns)} campaign(s)**")
    lines.append("")
    for c in campaigns:
        lines.extend(_format_campaign(c))
        lines.append("")
    return "\n".join(lines)


@mcp.tool()
def aeko_get_campaign(campaign_id: str) -> str:
    """Get full detail for one campaign including its tracked prompt members.

    Args:
        campaign_id: UUID of the campaign

    Returns:
        Markdown detail of the campaign and the prompts it groups.
    """
    resp, err = _safe(client.get, f"/api/campaigns/{campaign_id}")
    if err:
        return f"# Campaign\n\nCould not load campaign `{campaign_id}`: {err}"

    if not resp:
        return f"# Campaign `{campaign_id}`\n\nCampaign not found."

    lines = ["# Campaign detail", ""]
    lines.extend(_format_campaign(resp))
    lines.append("")

    prompts = resp.get("prompts") or []
    if prompts:
        lines.append(f"## Member prompts ({len(prompts)})")
        lines.append("")
        for i, p in enumerate(prompts, 1):
            txt = p.get("raw_prompt") or "(no text)"
            persona = p.get("persona_type") or "—"
            funnel = p.get("funnel_stage") or "—"
            country = p.get("country") or "—"
            lines.append(f"{i}. {txt}")
            lines.append(
                f"   - persona: {persona} · funnel: {funnel} · country: {country}"
            )
        lines.append("")

    rec_count = resp.get("content_recommendation_count", 0)
    if rec_count > 0:
        lines.append(
            f"💡 This campaign has **{rec_count}** active content recommendations. "
            f"Run `aeko_get_content_recommendations` with this campaign_id to see them."
        )
    return "\n".join(lines)


@mcp.tool()
def aeko_create_campaign(
    domain_id: str,
    name: str,
    product_label: str | None = None,
    description: str | None = None,
    prompt_ids: list[str] | None = None,
) -> str:
    """Create a new campaign, optionally seeded with tracked prompts.

    On creation, the backend immediately runs the persona-gap content
    recommender for the campaign (Growth+ tier only). The response includes
    the active recommendation count so the user can decide whether to
    fetch them via aeko_get_content_recommendations.

    Args:
        domain_id: UUID of the AEKO domain
        name: Campaign name (e.g., "Mattress Optimize Campaign"). Must be
            unique within the domain.
        product_label: Optional short product name (e.g., "Mattress")
        description: Optional longer description
        prompt_ids: Optional list of tracked prompt UUIDs to add as
            initial members. Must already be tracked by the user.

    Returns:
        Markdown confirmation of the new campaign.
    """
    payload: dict = {"domain_id": domain_id, "name": name}
    if product_label:
        payload["product_label"] = product_label
    if description:
        payload["description"] = description
    if prompt_ids:
        payload["prompt_ids"] = prompt_ids

    resp, err = _safe(client.post, "/api/campaigns", json=payload)
    if err:
        return f"# Campaign creation failed\n\n{err}"

    if not resp:
        return "# Campaign creation\n\nNo response from backend."

    lines = [f"# Campaign created: {resp.get('name', name)}", ""]
    lines.extend(_format_campaign(resp))
    lines.append("")

    rec_count = resp.get("content_recommendation_count", 0)
    if rec_count > 0:
        lines.append(
            f"✅ Generated **{rec_count}** initial content recommendations. "
            f"Run `aeko_get_content_recommendations(campaign_id='{resp.get('id', '')}')` "
            f"to see them."
        )
    elif resp.get("prompt_count", 0) > 0:
        lines.append(
            "ℹ️ Campaign created with prompts but no content recommendations were "
            "generated. This usually means the user is on a tier that doesn't "
            "include Content Recommendations (Growth+ required) OR the underlying "
            "prompts don't have enough mention metrics yet to detect persona gaps."
        )
    else:
        lines.append(
            "ℹ️ Campaign created with no member prompts. Add prompts via "
            "`aeko_add_prompts_to_campaign` to start generating recommendations."
        )
    return "\n".join(lines)


@mcp.tool()
def aeko_delete_campaign(campaign_id: str, untrack_prompts: bool = False) -> str:
    """Delete a campaign.

    Cascades to delete the campaign's prompt memberships AND its content
    recommendations. The underlying tracked prompts (UserPrompts rows)
    are NOT deleted unless `untrack_prompts=True`, in which case the
    matching UserPrompts.status is flipped to "untracked" so they stop
    receiving fresh AI responses.

    The frontend modal asks the user to choose. If unsure, default to
    untrack_prompts=False — the user can always untrack individual
    prompts later.

    Args:
        campaign_id: UUID of the campaign to delete
        untrack_prompts: If True, also untracks every prompt that belonged
            to this campaign. Use when the user is "done" with this product
            and won't be coming back to it.

    Returns:
        Markdown confirmation reporting the actual counts.
    """
    params = {"untrack_prompts": "true" if untrack_prompts else "false"}
    resp, err = _safe(
        client.delete, f"/api/campaigns/{campaign_id}", params=params
    )
    if err:
        return f"# Campaign deletion failed\n\n{err}"

    if not resp:
        return f"# Campaign deletion\n\nDeleted `{campaign_id}` (no response body)."

    lines = ["# Campaign deleted", ""]
    lines.append(f"- **Campaign**: `{resp.get('campaign_id', campaign_id)}`")
    lines.append(
        f"- **Cascade-deleted recommendations**: {resp.get('deleted_recommendation_count', 0)}"
    )
    lines.append(
        f"- **Cascade-deleted prompt memberships**: {resp.get('deleted_membership_count', 0)}"
    )
    if resp.get("untracked_prompt_count", 0) > 0:
        lines.append(
            f"- **Untracked prompts**: {resp['untracked_prompt_count']} "
            f"(matching UserPrompts.status flipped to 'untracked')"
        )
    elif untrack_prompts:
        lines.append(
            "- **Untracked prompts**: 0 (no prompts were tracked at the user level)"
        )
    return "\n".join(lines)
