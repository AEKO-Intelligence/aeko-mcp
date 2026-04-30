"""In-store content discovery for the content-creation skill.

Surfaces a list of pages on the user's *own* domain — blog posts, PDPs,
journal/magazine entries, etc. — so a content skill can:

1. build a tone signature from existing in-house content (mimic the brand
   voice that already exists on-site, not just the brand kit's stated voice);
2. flag duplication before drafting (don't write a fifth "summer cooling
   bedding guide" if four already live on the site);
3. anchor cross-channel narratives in the brand's own canon.

Different from `aeko_list_store_integrations` (which lists *connected store
platforms*, not pages) and from `aeko_get_product_description` (which
fetches one PDP's HTML by id). Different from `aeko_list_domains`, which
returns the AEKO-side domain catalog rather than the URLs *on* a domain.
"""

from __future__ import annotations

from typing import Any

from ..server import mcp, client
from ._annotations import READ_ONLY


_ALLOWED_TYPES: set[str] = {"blog", "pdp", "all"}


def _format_own_content(items: list[dict], domain_id: str, content_type: str) -> str:
    if not items:
        type_label = "blog posts or PDPs" if content_type == "all" else f"{content_type} pages"
        return (
            f"# No in-store content found for `{domain_id}`\n\n"
            f"AEKO doesn't yet have any {type_label} indexed for this domain. "
            "This is normal for a new domain — AEKO populates this list from "
            "the domain's sitemap.xml plus any pages discovered during AI "
            "engine response collection. For brand-new domains the index can "
            "take up to 24h to populate after the domain is connected."
        )

    lines = [f"# In-store content for `{domain_id}` ({len(items)})", ""]
    if content_type != "all":
        lines.append(f"_Filtered to type: **{content_type}**_")
        lines.append("")

    for item in items:
        url = item.get("url") or "(unknown url)"
        title = item.get("title") or "(untitled)"
        ct = item.get("content_type") or "?"
        last_seen = item.get("last_seen") or ""
        lines.append(f"## {title}")
        lines.append(f"- **URL**: {url}")
        lines.append(f"- **Type**: {ct}")
        if last_seen:
            lines.append(f"- **Last seen**: {last_seen}")
        summary = item.get("summary")
        if summary:
            trimmed = summary if len(summary) <= 240 else summary[:237] + "..."
            lines.append(f"- **Summary**: {trimmed}")
        lines.append("")

    lines.append(
        "Use this list to (a) check whether a planned draft duplicates an "
        "existing page, (b) sample 2-3 entries to derive an in-house tone "
        "signature before drafting, (c) anchor cross-channel narratives in "
        "the brand's own canon."
    )
    return "\n".join(lines)


@mcp.tool(title="List own-domain content", annotations=READ_ONLY)
def aeko_list_own_content(
    domain_id: str,
    type: str = "all",
    limit: int = 20,
) -> str:
    """List the brand's existing on-site content (blog posts and/or PDPs).

    Returns up to `limit` rows, each with `url`, `title`, optional summary,
    `content_type`, and `last_seen` timestamp. Backed by AEKO's per-domain
    page index (sitemap.xml + AI-response page discovery). New domains may
    return zero rows for up to 24h after connecting until the index
    populates.

    Use this whenever a content skill needs to mimic in-house tone, dedupe
    against existing pages, or reference the brand's own canon — it's the
    counterpart to `aeko_get_tracked_prompt` (which surfaces *cited*
    sources) for the brand's own-domain side.

    Args:
        domain_id: UUID of the AEKO-connected domain.
        type: `blog` (blog/journal/magazine/news/insight pages), `pdp`
            (product detail pages), or `all` (default — both buckets).
        limit: Max rows to return. Default 20, hard cap 50.
    """
    if type not in _ALLOWED_TYPES:
        allowed = ", ".join(sorted(_ALLOWED_TYPES))
        return f"Invalid `type`: {type}. Allowed: {allowed}."

    capped_limit = max(1, min(int(limit), 50))
    params: dict[str, Any] = {"type": type, "limit": capped_limit}
    data = client.get(f"/api/domains/{domain_id}/own-content", params=params)

    # Backend returns a bare list (List[OwnContentRow]) — same convention as
    # `aeko_list_domains` and `aeko_list_store_integrations`. Keep this
    # aligned across list endpoints; if the backend ever switches to a
    # paginated envelope, update here in lockstep.
    items = data if isinstance(data, list) else []
    return _format_own_content(items, domain_id, type)
