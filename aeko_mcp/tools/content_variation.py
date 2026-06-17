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

from ..server import mcp, client
from ._annotations import READ_ONLY, WRITE, WRITE_ONCE


# ─── Internal helpers ─────────────────────────────────────────────────────


def _safe(method, *args, **kwargs) -> tuple[Any, Optional[str]]:
    """Wrap client errors into ``(None, message)`` for graceful tool output.

    Mirrors ``store_write._safe`` — keeps the tool surface uniform so the
    skill-side error narration is the same shape across write tools.
    """
    try:
        return method(*args, **kwargs), None
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


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


@mcp.tool(title="Save content variation", annotations=WRITE_ONCE)
def aeko_save_content_variation(
    item_id: str,
    destination: str,
    title: str,
    body_html: Optional[str] = None,
    body_markdown: Optional[str] = None,
    metadata: Optional[dict] = None,
    artifact_paths: Optional[list[str]] = None,
) -> str:
    """Save a publishable content variation to the AEKO backend, keyed by item_id.

    Use this from ``/aeko-create-content`` Step 7.5 after drafting an
    artifact triple locally, so the same draft can later be shipped via
    ``/aeko-publish-content`` from any machine (the publish source-of-truth
    is the backend row, not the local files).

    This tool does NOT carry ``brand_id``. For ``destination='aeko_shop'``,
    ``metadata`` must include ``og_description`` and
    ``featured_product_source_ids``. When Plan.md includes products, also pass
    ``featured_products`` snapshots (source_id/product_source_id, name, slug,
    outbound_url, image_url, short_description, etc.). Publish uses those
    snapshots to upsert missing aeko.shop products before creating the post's
    post_products mappings. ``hero_image_url`` is optional; text-only aeko.shop
    posts are valid.

    When the draft quotes Context Reviews (from ``aeko_get_product_reviews``),
    also record them in ``metadata`` under the OPTIONAL ``featured_product_reviews``
    array — a provenance trail of which real customer narratives grounded the
    copy, parallel to ``featured_products``. Each entry is
    ``{review_id, product_source_id, context_score, problem, solution, outcome,
    excerpt}``. Metadata is free-form JSONB passed straight through to the
    backend (no server-side validation of this key), so it's safe to attach.

    Args:
        item_id: Action-item id this variation belongs to. Tenancy is
            enforced server-side (must be owned by the current user).
        destination: One of ``"aeko_shop"`` or ``"own_store_blog"``. Other
            channels (naver_blog, tistory, social, editorial) are
            local-only and should NOT be saved via this tool.
        title: Variation title. Required, max 300 chars.
        body_html: Full HTML body (with optional inline JSON-LD). At least
            one of ``body_html``/``body_markdown`` must be non-empty.
        body_markdown: Markdown body. At least one of
            ``body_html``/``body_markdown`` must be non-empty.
        metadata: Destination-specific metadata dict. For ``aeko_shop``:
            ``{og_description, featured_product_source_ids[, hero_image_url,
            locale, content_format_version, featured_products,
            featured_product_reviews]}``.
            ``featured_products[]`` entries should mirror Plan.md product refs
            and should include ``source_id``/``product_source_id`` + ``name``
            when the product may not already exist in aeko.shop.
            ``featured_product_reviews[]`` is OPTIONAL — when the draft quoted
            Context Reviews, list the ones used, each
            ``{review_id, product_source_id, context_score, problem, solution,
            outcome, excerpt}``. Free-form JSONB, passed through as-is.
            For ``own_store_blog``: optional ``{og_description, tags, locale,
            featured_product_reviews}``.
        artifact_paths: Optional list of local-disk paths to the artifact
            triple (audit trail; not used by publish).
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
        f"variation_id='{result.get('id', '?')}')` "
        "or via the `/aeko-publish-content` skill.",
    ]
    return "\n".join(lines)


@mcp.tool(title="Update content variation", annotations=WRITE)
def aeko_update_content_variation(
    variation_id: str,
    title: Optional[str] = None,
    body_html: Optional[str] = None,
    body_markdown: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> str:
    """Edit a SAVED (not-yet-published) content variation in place.

    The "edit a draft" path: tweak a saved draft before publishing without
    creating a whole new variation. Only the fields you pass change; the rest
    are kept. A previously ``failed`` variation is reset to ``saved`` on a
    successful edit so you can retry publish cleanly.

    **Published variations are immutable here** (backend returns 409). To
    change a post that is already live on aeko.shop, re-publish the variation —
    aeko.shop upserts by ``source_content_id`` and overwrites the post in place
    (then re-renders + redirects on slug change). See ``/aeko-publish-content``.

    For an ``aeko_shop`` variation the merged result must still satisfy the
    contract (non-empty ``body_html``; ``metadata`` with ``og_description`` and,
    when present, an absolute-https ``hero_image_url``) or the backend returns
    422. ``metadata`` REPLACES the stored metadata object, so include the full
    aeko_shop metadata (og_description, hero_image_url, featured_products, …)
    when you pass it.

    Args:
        variation_id: Row id to edit (from ``aeko_list_content_variations``).
        title: New title (optional).
        body_html: Replacement HTML body (optional).
        body_markdown: Replacement markdown body (optional).
        metadata: Replacement destination metadata dict (optional; replaces,
            not merges).
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


@mcp.tool(title="List content variations", annotations=READ_ONLY)
def aeko_list_content_variations(
    item_id: str,
    destination: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 20,
) -> str:
    """List saved content variations for an action item, grouped by destination.

    Used by ``/aeko-publish-content`` Step 1 to discover what's
    publishable under a given ``item_id``. Newest-first within each
    destination group.

    Args:
        item_id: Action-item id to list variations for.
        destination: Optional filter — ``"aeko_shop"`` or ``"own_store_blog"``.
            Omit to get both buckets.
        status: Optional filter — ``"saved"``, ``"published"``, or ``"failed"``.
        limit: Max rows to return. Default 20, hard cap 50 (mirrors
            ``aeko_list_own_content``).
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


@mcp.tool(title="Publish content variation", annotations=WRITE_ONCE)
def aeko_publish_content_variation(item_id: str, variation_id: str) -> str:
    """Publish a saved content variation. Branches on destination server-side.

    For ``destination='aeko_shop'``: calls the live ``AekoShopPublisher``
    (Pro+ tier gate + 10/hour rate limit enforced server-side). Returns
    the aeko.shop URL and ``post_id`` on success.

    For ``destination='own_store_blog'``: inserts a draft row in
    ``aeko_content_drafts`` (no Cafe24/Shopify live API call). Returns the
    ``draft_id``; the user pushes via the dashboard or a future connector.

    Backend response codes the skill should be prepared to surface:
      - 403 tier gate (Starter trying to publish to aeko_shop)
      - 409 ``aeko_shop_disabled=true`` (per-brand opt-out)
      - 429 publisher rate-limited (10/hour per brand)
      - 502 aeko-shop upstream error
      - 422 publish-adapter validation (should have been caught at save)

    Args:
        item_id: Action-item id the variation belongs to. Carried so the
            skill can complete the ``aeko_complete_action_item`` write_result
            handoff after publish.
        variation_id: UUID of the ``content_variations`` row to publish.
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
