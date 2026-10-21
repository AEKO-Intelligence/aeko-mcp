"""Content Variation tools — backend-saved publishable drafts keyed by item_id.

Four tools wrap the AEKO backend's ``/api/content-variations*`` routes:

  - ``aeko_save_content_variation``    ← POST  /api/content-variations
  - ``aeko_update_content_variation``  ← PATCH /api/content-variations/{id}
  - ``aeko_list_content_variations``   ← GET   /api/content-variations
  - ``aeko_publish_content_variation`` ← POST  /api/content-variations/{id}/publish

These replace the local-disk artifact triple as the source of truth for
``/aeko-publish-content``. A draft saved on machine A can now be published
from machine B because the row lives in the backend, not on disk.

Lifecycle (per the v1.5 contract):
  saved → published        (publish action completed)
  saved → failed           (publish attempted and failed; ``last_error`` populated)
  failed → published       (retry succeeded)

Per-destination publish semantics:
  - ``aeko_shop``       — calls AekoShopPublisher; returns aeko.shop URL + post_id.
  - ``own_store_blog``  — inserts a row in ``aeko_content_drafts`` (no live API
                          call); returns ``draft_id`` for future push.

The publish endpoint is idempotent at the row level: re-publishing an
already-published row returns the stored handles without creating duplicates.
"""
from typing import Any, Optional

from ..client import legacy_error_name
from ..server import mcp, client
from ._annotations import (
    ADDITIVE_ONCE,
    DESTRUCTIVE_EXTERNAL,
    DESTRUCTIVE_IDEMPOTENT,
    READ_ONLY,
    tool_spec,
)


# ─── Internal helpers ─────────────────────────────────────────────────────


def _safe(method, *args, **kwargs) -> tuple[Any, Optional[str]]:
    """Wrap client errors into ``(None, message)`` for graceful tool output.

    Mirrors ``store_write._safe`` — keeps the tool surface uniform so the
    skill-side error narration is the same shape across write tools.
    """
    try:
        return method(*args, **kwargs), None
    except Exception as e:  # noqa: BLE001
        return None, f"{legacy_error_name(e)}: {e}"


def _format_meta_summary(meta_summary: Optional[dict]) -> str:
    """Render the backend's flat meta_summary dict as a compact one-liner."""
    if not meta_summary:
        return "—"
    bits: list[str] = []
    if "locale" in meta_summary:
        bits.append(f"locale={meta_summary['locale']}")
    if "has_hero_image" in meta_summary:
        bits.append(f"hero={'yes' if meta_summary['has_hero_image'] else 'no'}")
    if "featured_products_count" in meta_summary:
        bits.append(f"featured={meta_summary['featured_products_count']}")
    if "tags_count" in meta_summary:
        bits.append(f"tags={meta_summary['tags_count']}")
    return ", ".join(bits) if bits else "—"


def _format_variation_row(row: dict) -> list[str]:
    """Render a single ContentVariationResponse as markdown lines under an H3."""
    variation_id = row.get("id", "?")
    title = row.get("title", "(untitled)")
    lines: list[str] = []
    lines.append(f"### {title}")
    lines.append(f"- **variation_id**: `{variation_id}`")
    lines.append(f"- **status**: {row.get('status', '?')}")
    lines.append(f"- **created_at**: {row.get('created_at', '?')}")
    lines.append(
        f"- **bodies**: html={'yes' if row.get('has_html') else 'no'}, "
        f"markdown={'yes' if row.get('has_markdown') else 'no'}"
    )
    lines.append(f"- **meta**: {_format_meta_summary(row.get('meta_summary'))}")
    if row.get("published_at"):
        lines.append(f"- **published_at**: {row['published_at']}")
    if row.get("last_error"):
        # Truncate noisy stack-style errors; full text lives in backend logs.
        err = str(row["last_error"])
        if len(err) > 240:
            err = err[:237] + "..."
        lines.append(f"- **last_error**: {err}")
    lines.append("")
    return lines


# ─── Tools ────────────────────────────────────────────────────────────────


@mcp.tool(**tool_spec("Save content variation", ADDITIVE_ONCE))
def aeko_save_content_variation(
    item_id: str,
    destination: str,
    title: str,
    body_html: Optional[str] = None,
    body_markdown: Optional[str] = None,
    metadata: Optional[dict] = None,
    artifact_paths: Optional[list[str]] = None,
) -> str:
    """Save a publishable content draft to AEKO for an action item. Nothing is published.

    aeko_publish_content_variation later publishes this saved copy, from any device.

    Args:
        item_id: The user's action item.
        destination: "aeko_shop" or "own_store_blog".
        title: Up to 300 characters.
        body_html, body_markdown: At least one; HTML may include JSON-LD.
        metadata: aeko_shop requires og_description and featured_product_source_ids; optional
            hero_image_url (https), locale, featured_products (product snapshots: source_id, name,
            slug, outbound_url, image_url, short_description; publish adds missing aeko.shop
            products from them) and featured_product_reviews (reviews quoted in the draft:
            review_id, product_source_id, context_score, facets, excerpt). own_store_blog:
            optional og_description, tags, locale, featured_product_reviews.
        artifact_paths: Optional local file names, for the record.
    """
    # Mirror backend Pydantic ``_validate_body_and_metadata`` check at the
    # tool layer so we fail fast with a friendly message instead of a 422.
    has_html = bool((body_html or "").strip())
    has_markdown = bool((body_markdown or "").strip())
    if not has_html and not has_markdown:
        return "# Save failed\n\nMust provide at least one of body_html or body_markdown"

    payload: dict[str, Any] = {
        "item_id": item_id,
        "destination": destination,
        "title": title,
    }
    if body_html is not None:
        payload["body_html"] = body_html
    if body_markdown is not None:
        payload["body_markdown"] = body_markdown
    if metadata is not None:
        payload["metadata"] = metadata
    if artifact_paths is not None:
        payload["artifact_paths"] = artifact_paths

    result, err = _safe(client.post, "/api/content-variations", json=payload)
    if err:
        return f"# Save failed\n\n```\n{err}\n```"
    if not result:
        return "# Save failed\n\n(no response body)"

    lines = [
        "# Variation saved",
        "",
        f"- **variation_id**: `{result.get('id', '?')}`",
        f"- **item_id**: `{result.get('item_id', item_id)}`",
        f"- **destination**: {result.get('destination', destination)}",
        f"- **status**: {result.get('status', 'saved')}",
        f"- **created_at**: {result.get('created_at', '?')}",
        "",
        "Publish later with "
        f"`aeko_publish_content_variation(item_id='{result.get('item_id', item_id)}', "
        f"variation_id='{result.get('id', '?')}')`.",
    ]
    return "\n".join(lines)


@mcp.tool(**tool_spec("Update content variation", DESTRUCTIVE_IDEMPOTENT))
def aeko_update_content_variation(
    variation_id: str,
    title: Optional[str] = None,
    body_html: Optional[str] = None,
    body_markdown: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> str:
    """Edit a saved, not yet published content draft in place.

    Only the fields you pass change. A draft whose publish failed returns to
    saved after an edit, so publishing can be retried. Published drafts cannot
    be edited here (409); publishing a variation again overwrites its live
    aeko.shop post in place.

    For aeko_shop drafts the merged result must keep a non-empty body_html and
    metadata with og_description (and an https hero_image_url if set), or AEKO
    returns 422. metadata replaces the stored object instead of merging, so
    send the full metadata (og_description, hero_image_url, featured_products,
    ...) when you change it.

    Args:
        variation_id: Draft ID from aeko_list_content_variations.
        title: New title (optional).
        body_html: Replacement HTML body (optional).
        body_markdown: Replacement markdown body (optional).
        metadata: Replacement metadata object (optional).
    """
    if title is None and body_html is None and body_markdown is None and metadata is None:
        return (
            "# Update failed\n\nProvide at least one field to change "
            "(title, body_html, body_markdown, metadata)."
        )

    payload: dict[str, Any] = {}
    if title is not None:
        payload["title"] = title
    if body_html is not None:
        payload["body_html"] = body_html
    if body_markdown is not None:
        payload["body_markdown"] = body_markdown
    if metadata is not None:
        payload["metadata"] = metadata

    result, err = _safe(
        client.patch, f"/api/content-variations/{variation_id}", json=payload
    )
    if err:
        return f"# Update failed\n\n```\n{err}\n```"
    if not result:
        return "# Update failed\n\n(no response body)"

    lines = [
        "# Variation updated",
        "",
        f"- **variation_id**: `{result.get('id', variation_id)}`",
        f"- **item_id**: `{result.get('item_id', '?')}`",
        f"- **destination**: {result.get('destination', '?')}",
        f"- **status**: {result.get('status', 'saved')}",
        f"- **updated_at**: {result.get('updated_at', '?')}",
        "",
        "Publish with "
        f"`aeko_publish_content_variation(item_id='{result.get('item_id', '?')}', "
        f"variation_id='{result.get('id', variation_id)}')`.",
    ]
    return "\n".join(lines)


@mcp.tool(**tool_spec("List content variations", READ_ONLY))
def aeko_list_content_variations(
    item_id: str,
    destination: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 20,
) -> str:
    """List saved content drafts for an action item, grouped by destination, newest first.

    Use it to find drafts that are ready to publish.

    Args:
        item_id: Action item ID.
        destination: Optional "aeko_shop" or "own_store_blog"; omit for both.
        status: Optional "saved", "published" or "failed".
        limit: Max rows, default 20, at most 50.
    """
    capped_limit = max(1, min(int(limit), 50))
    params: dict[str, Any] = {"item_id": item_id, "limit": capped_limit}
    if destination is not None:
        params["destination"] = destination
    if status is not None:
        params["status"] = status

    result, err = _safe(client.get, "/api/content-variations", params=params)
    if err:
        return f"# Failed to list content variations\n\n```\n{err}\n```"

    items = result.get("items", []) if isinstance(result, dict) else []
    if not items:
        return f"No saved variations for item `{item_id}`."

    # Group by destination — backend returns newest-first overall; preserve
    # ordering within each bucket.
    buckets: dict[str, list[dict]] = {}
    for row in items:
        dest = row.get("destination") or "unknown"
        buckets.setdefault(dest, []).append(row)

    lines = [f"# Content variations for item `{item_id}` ({len(items)})", ""]
    # Stable display order: aeko_shop first (canonical destination), then
    # own_store_blog, then anything else lexically.
    preferred_order = ["aeko_shop", "own_store_blog"]
    ordered_destinations = [d for d in preferred_order if d in buckets] + sorted(
        d for d in buckets if d not in preferred_order
    )
    for dest in ordered_destinations:
        rows = buckets[dest]
        lines.append(f"## {dest} ({len(rows)})")
        lines.append("")
        for row in rows:
            lines.extend(_format_variation_row(row))

    lines.append(
        "Publish a row with "
        f"`aeko_publish_content_variation(item_id='{item_id}', variation_id=...)`."
    )
    return "\n".join(lines)


@mcp.tool(**tool_spec("Publish content variation", DESTRUCTIVE_EXTERNAL))
def aeko_publish_content_variation(item_id: str, variation_id: str) -> str:
    """Publish a saved content draft. The effect depends on its destination.

    - aeko_shop: publishes the post publicly on aeko.shop and returns its URL
      and post_id. Each action item has one post, so publishing again, or
      publishing another draft of the same item, replaces the live post.
      Pro+ only; up to 10 publishes per hour per brand.
    - own_store_blog: saves a draft in the user's AEKO content drafts and
      returns draft_id. Nothing is sent to Cafe24 or Shopify.

    Confirm with the user before publishing to aeko.shop. Expected errors: 403
    (plan), 409 (aeko.shop turned off for the brand), 429 (rate limit), 502
    (aeko.shop error), 422 (invalid draft).

    Args:
        item_id: Action item the draft belongs to; pass it to
            aeko_complete_action_item afterwards.
        variation_id: Draft ID to publish.
    """
    # Backend identifies the variation by URL path and verifies the item_id
    # body as a defense-in-depth guard against mismatched item/variation calls.
    path = f"/api/content-variations/{variation_id}/publish"
    result, err = _safe(client.post, path, json={"item_id": item_id})
    if err:
        return (
            f"# Publish failed\n\n"
            f"- **item_id**: `{item_id}`\n"
            f"- **variation_id**: `{variation_id}`\n\n"
            f"```\n{err}\n```"
        )
    if not result:
        return "# Publish failed\n\n(no response body)"

    destination = result.get("destination", "?")
    lines = [
        f"# Variation published ({destination})",
        "",
        f"- **item_id**: `{item_id}`",
        f"- **variation_id**: `{result.get('variation_id', variation_id)}`",
        f"- **status**: {result.get('status', 'published')}",
    ]
    if destination == "aeko_shop":
        if result.get("aeko_shop_url"):
            lines.append(f"- **URL**: {result['aeko_shop_url']}")
        else:
            # Published to aeko.shop but no canonical URL came back. Don't claim
            # a clickable link the user doesn't have — surface the gap so they
            # can check the deployment (AEKO_SHOP_PUBLIC_URL) / backend logs.
            lines.append(
                "- **URL**: ⚠️ could not be generated — the post published but no "
                "canonical aeko.shop URL was returned. Check that the backend's "
                "`AEKO_SHOP_PUBLIC_URL` is configured, then re-run publish "
                "(idempotent — it won't duplicate the post)."
            )
        if result.get("post_id"):
            lines.append(f"- **post_id**: `{result['post_id']}`")
    elif destination == "own_store_blog":
        if result.get("draft_id"):
            lines.append(f"- **draft_id**: `{result['draft_id']}`")
        lines.append("")
        lines.append(
            "Draft saved in your AEKO content drafts. Push to your connected "
            "store via the dashboard or future connector."
        )
    return "\n".join(lines)


@mcp.tool(**tool_spec("Unpublish aeko.shop content", DESTRUCTIVE_EXTERNAL))
def aeko_unpublish_content(
    source_content_id: str,
    item_id: Optional[str] = None,
    domain_id: Optional[str] = None,
) -> str:
    """Unpublish a post from aeko.shop by source content id.

    Supply `item_id` when the post came from an AEKO action item. Use
    `domain_id` only for kitless posts where no item exists.
    """
    body = {
        "item_id": item_id,
        "domain_id": domain_id,
    }
    payload = {k: v for k, v in body.items() if v is not None}
    result, err = _safe(
        client.post,
        f"/api/aeko-shop/posts/{source_content_id}/unpublish",
        json=payload,
    )
    if err:
        return f"# Unpublish failed\n\n```\n{err}\n```"
    if not result:
        return "# Unpublish requested"
    lines = [
        "# Content unpublished",
        "",
        f"- **source_content_id**: `{source_content_id}`",
        f"- **status**: {result.get('status', 'unpublished')}",
    ]
    if result.get("id"):
        lines.append(f"- **post_id**: `{result['id']}`")
    if result.get("slug"):
        lines.append(f"- **slug**: {result['slug']}")
    return "\n".join(lines)
