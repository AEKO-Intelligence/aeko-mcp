"""In-store content discovery for the content-creation skill.

Surfaces a list of pages on the user's *own* domain — blog posts, PDPs,
journal/magazine entries, etc. — so a content skill can:

1. build a tone signature from existing in-house content (mimic the brand
   voice that already exists on-site);
2. flag duplication before drafting (don't write a fifth "summer cooling
   bedding guide" if four already live on the site);
3. anchor cross-channel narratives in the brand's own canon.

Different from `aeko_list_store_integrations` (which lists *connected store
platforms*, not pages) and from `aeko_get_product_description` (which
fetches one PDP's HTML by id). Different from `aeko_list_domains`, which
returns the AEKO-side domain catalog rather than the URLs *on* a domain.
"""

from typing import Any

from ..server import mcp, client
from ._annotations import READ_ONLY, tool_spec


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


@mcp.tool(**tool_spec("List own-domain content", READ_ONLY))
def aeko_list_own_content(
    domain_id: str,
    type: str = "all",
    limit: int = 20,
) -> str:
    """List the brand's existing on-site content (blog posts and/or product pages).

    Returns up to `limit` rows, each with url, title, optional summary,
    content_type and last_seen. Built from AEKO's page index for the domain
    (sitemap.xml plus pages discovered in AI answers); a new domain may return
    nothing for up to 24 hours.

    Use it to match the brand's tone, avoid duplicating existing pages, or
    reference the brand's own content. For pages that AI engines cite, use
    aeko_get_tracked_prompt instead.

    Args:
        domain_id: Domain UUID.
        type: blog (blog, journal, magazine, news and insight pages), pdp
            (product pages) or all (default).
        limit: Max rows, default 20, at most 50.
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
