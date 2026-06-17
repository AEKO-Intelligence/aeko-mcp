"""MCP tools for reading classified Context Reviews from connected review platforms.

Wraps the AEKO backend's /api/review-integrations* read endpoints so the
content-creation skills can ground a draft in REAL customer narratives —
the shopper context, product experience, and felt effect — instead of
inventing copy.

A review is "contextual" when its ``context_score`` is >= 60. The backend's
review classifier extracts flexible facets from each review and scores how
rich that context is; unclassified / pending rows have no score yet and are
excluded once a ``min_context_score`` filter is applied.

Three tools total — all read-only, all Pro+ gated server-side:
  - aeko_list_review_integrations  ← discovery (resolve integration_id for a domain)
  - aeko_list_review_products      ← which products HAVE contextual reviews
  - aeko_get_product_reviews       ← the top contextual reviews for one product

The create-content use case (e.g. /aeko-create-content, aeko-update-pdp):
  1. resolve the domain's review integration with ``aeko_list_review_integrations``
  2. see which products have contextual reviews with ``aeko_list_review_products``
  3. for the product being written, pull its TOP contextual reviews with
     ``aeko_get_product_reviews`` and weave the real customer-state /
     concern / product-experience details into the draft (recording which
     reviews were used in the
     content variation's ``featured_product_reviews`` metadata).

These are read-only — they never mutate review platform data. Pro+ is
enforced server-side; an under-tier or trial-expired account surfaces the
backend's 403 message verbatim via the AekoClient error path.
"""
from typing import Any, Optional

from ..server import mcp, client
from ._annotations import READ_ONLY

# A review counts as "contextual" at or above this context_score. Mirrors the
# backend threshold; also the default floor for ``aeko_get_product_reviews``.
CONTEXTUAL_THRESHOLD = 60


def _safe(method, *args, **kwargs) -> tuple[Any, Optional[str]]:
    """Wrap client errors into ``(None, message)`` for graceful tool output.

    Mirrors ``store_write._safe`` — keeps the tool surface uniform so the
    skill-side error narration is the same shape across tools. A backend 403
    (Pro+ required) arrives here as a RuntimeError carrying the upgrade-pitch
    message, so the caller just renders it.
    """
    try:
        return method(*args, **kwargs), None
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


def _excerpt(text: Optional[str], limit: int = 280) -> str:
    """Collapse whitespace and truncate a review body into a quotable excerpt."""
    if not text:
        return ""
    flat = " ".join(str(text).split())
    if len(flat) > limit:
        return flat[: limit - 1].rstrip() + "…"
    return flat


@mcp.tool(title="List review integrations", annotations=READ_ONLY)
def aeko_list_review_integrations(domain_id: str) -> str:
    """List the Crema / Judge.me review integrations connected for a domain.

    The starting point for any context-review workflow — call this first to
    resolve the ``integration_id`` you pass to ``aeko_list_review_products``
    and ``aeko_get_product_reviews``. The create-content skills call this to
    discover whether a domain even has classified customer reviews to draw on
    before drafting.

    Each block shows the integration id, platform, store identifier, the
    backfill status (whether the initial review import has finished), and when
    it last synced — so the skill can tell a "classifier still running" empty
    result apart from a genuinely review-less store.

    Read-only. Pro+ is enforced server-side; a lower tier surfaces a 403 with
    the upgrade message.

    Args:
        domain_id: UUID of the AEKO domain whose review integrations you want.
    """
    result, err = _safe(
        client.get, "/api/review-integrations", params={"domain_id": domain_id}
    )
    if err:
        return f"# Failed to list review integrations\n\n```\n{err}\n```"

    items = result if isinstance(result, list) else []
    if not items:
        return (
            f"# No review integrations for domain `{domain_id}`\n\n"
            "Connect a Crema or Judge.me review platform from the AEKO dashboard "
            "Settings → Review Integrations tab, then call this tool again. "
            "(Context Reviews require a Pro+ subscription.)"
        )

    lines = [f"# Review integrations ({len(items)})", ""]
    for item in items:
        integration_id = item.get("id", "?")
        platform = item.get("platform", "?")
        store = item.get("store_identifier", "?")
        backfill = item.get("backfill_status") or "?"

        lines.append(f"## `{integration_id}`")
        lines.append(f"- **Platform**: {platform}")
        lines.append(f"- **Store**: `{store}`")
        lines.append(f"- **Backfill**: {backfill}")
        if item.get("last_synced_at"):
            lines.append(f"- **Last synced**: {item['last_synced_at']}")
        if item.get("last_sync_status"):
            status_line = f"- **Last sync status**: {item['last_sync_status']}"
            if item.get("last_sync_error_message"):
                status_line += f" — {item['last_sync_error_message']}"
            lines.append(status_line)
        lines.append("")

    lines.append(
        "Pass the `id` value above as `integration_id` to "
        "`aeko_list_review_products` to see which products have contextual reviews."
    )
    return "\n".join(lines)


@mcp.tool(title="List review products", annotations=READ_ONLY)
def aeko_list_review_products(integration_id: str) -> str:
    """List products under a review integration, with their contextual-review counts.

    Call this after ``aeko_list_review_integrations`` to see WHICH products
    actually have contextual reviews worth weaving into a draft. The
    ``contextual`` column is the count of reviews scoring >= 60 (rich
    source-backed customer context); ``reviews`` is the raw total. A
    product with ``contextual = 0`` has reviews but none classified as
    context-rich yet (or the classifier is still running).

    When picking a product to write content for, prefer ones with a non-zero
    ``contextual`` count, then call ``aeko_get_product_reviews`` with that
    product's ``external_product_ref``.

    Read-only. Pro+ enforced server-side (403 if under-tier).

    Args:
        integration_id: UUID of the review integration (from
            ``aeko_list_review_integrations``).
    """
    path = f"/api/review-integrations/{integration_id}/products"
    result, err = _safe(client.get, path)
    if err:
        return f"# Failed to list review products\n\n```\n{err}\n```"

    items = result if isinstance(result, list) else []
    if not items:
        return (
            f"# No products under integration `{integration_id}`\n\n"
            "The review import may still be running — check the **Backfill** "
            "status in `aeko_list_review_integrations`, then try again. If "
            "backfill is complete, this store simply has no reviewed products yet."
        )

    # Surface the products that have contextual reviews first — those are the
    # ones the create-content flow can actually ground a draft in.
    rows = sorted(
        items,
        key=lambda r: (r.get("contextual_count") or 0, r.get("review_count") or 0),
        reverse=True,
    )

    lines = [
        f"# Review products ({len(rows)})",
        "",
        "| external_product_ref | title | reviews | contextual |",
        "| --- | --- | ---: | ---: |",
    ]
    total_contextual = 0
    for row in rows:
        ref = row.get("external_product_ref", "?")
        title = (row.get("title") or "(untitled)").replace("|", "\\|")
        if len(title) > 60:
            title = title[:57] + "…"
        review_count = row.get("review_count") or 0
        contextual_count = row.get("contextual_count") or 0
        total_contextual += contextual_count
        lines.append(f"| `{ref}` | {title} | {review_count} | {contextual_count} |")

    lines.append("")
    if total_contextual == 0:
        lines.append(
            "No contextual reviews yet — the classifier may still be running. "
            "Re-check shortly; products gain a contextual count once their "
            "reviews are scored >= "
            f"{CONTEXTUAL_THRESHOLD}."
        )
    else:
        lines.append(
            "For a product with a non-zero **contextual** count, call "
            "`aeko_get_product_reviews(integration_id=..., external_product_ref=...)` "
            "to pull its strongest source-backed customer contexts for a draft."
        )
    return "\n".join(lines)


@mcp.tool(title="Get product context reviews", annotations=READ_ONLY)
def aeko_get_product_reviews(
    integration_id: str,
    external_product_ref: str,
    min_context_score: int = CONTEXTUAL_THRESHOLD,
    limit: int = 10,
) -> str:
    """Fetch a product's TOP contextual reviews — source-backed customer memories.

    This is the tool the create-content skills call to ground a draft in
    genuine customer narratives. It returns ONLY contextual reviews — those
    scoring at or above ``min_context_score`` (default 60) — sorted
    strongest-context-first (``sort=context``). Pending / unclassified reviews
    have no score and are excluded once a ``min_context_score`` is applied, so
    everything returned here is a vetted, context-rich story.

    For each review you get: the ``context_score``, extracted ``문제``
    (legacy grounding), ``고객 상태``, ``최근 고민``, ``제품 경험``, and
    ``느낀 효과`` (falling back to legacy outcome/solution when needed), the
    star rating, author, date, and a quotable excerpt of the body. Weave these
    into the draft as concrete "who this customer was, what they were dealing
    with, what the product felt like, and what improved" evidence, and record
    which reviews you used in the content variation's
    ``featured_product_reviews`` metadata.

    Read-only. Pro+ enforced server-side (403 if under-tier).

    Args:
        integration_id: UUID of the review integration (from
            ``aeko_list_review_integrations``).
        external_product_ref: The product's review-platform ref (from
            ``aeko_list_review_products`` — the ``external_product_ref`` column).
        min_context_score: Minimum ``context_score`` (0–100) a review must have
            to be returned. Default 60 (the contextual threshold). Raise it to
            tighten to only the very richest stories; rows below it — and all
            unclassified/pending rows — are excluded.
        limit: Max reviews to return (1–200). Default 10.
    """
    capped_limit = max(1, min(int(limit), 200))
    capped_score = max(0, min(int(min_context_score), 100))
    path = (
        f"/api/review-integrations/{integration_id}/products/"
        f"{external_product_ref}/reviews"
    )
    result, err = _safe(
        client.get,
        path,
        params={
            "min_context_score": capped_score,
            "sort": "context",
            "limit": capped_limit,
        },
    )
    if err:
        return f"# Failed to fetch product reviews\n\n```\n{err}\n```"

    items = result if isinstance(result, list) else []
    if not items:
        return (
            f"# No contextual reviews for product `{external_product_ref}`\n\n"
            "No reviews scored at or above the context threshold "
            f"(min_context_score={capped_score}) yet — the classifier may still "
            "be running, or this product's reviews aren't context-rich. "
            "Pending/unclassified reviews are excluded. Try again later, or lower "
            "`min_context_score` slightly if you want borderline stories."
        )

    lines = [
        f"# Contextual reviews for `{external_product_ref}` "
        f"({len(items)}, context ≥ {capped_score}, strongest first)",
        "",
    ]
    for idx, review in enumerate(items, start=1):
        rating = review.get("rating")
        rating_str = f"{'★' * int(rating)}{'☆' * (5 - int(rating))}" if isinstance(rating, int) else "?"
        score = review.get("context_score", "?")
        author = review.get("author_name") or "Anonymous"
        date = review.get("review_created_at") or "?"
        lang = review.get("lang") or ""
        ctype = review.get("context_type")
        title = review.get("title") or ""

        header = f"## {idx}. {rating_str} — context {score}/100"
        if ctype:
            header += f" · {ctype}"
        lines.append(header)
        meta = f"_{author} · {date}"
        if lang:
            meta += f" · {lang}"
        meta += "_"
        lines.append(meta)
        if title:
            lines.append(f"**{title}**")
        lines.append("")

        # Flexible review-memory facets, original-language, only when present.
        problem = review.get("extracted_problem")
        customer_state = review.get("customer_state")
        recent_concern = review.get("recent_concern")
        product_experience = review.get("product_experience")
        felt_effect = (
            review.get("felt_effect")
            or review.get("extracted_outcome")
            or review.get("extracted_solution")
        )
        if problem:
            lines.append(f"- **문제**: {problem}")
        if customer_state:
            lines.append(f"- **고객 상태**: {customer_state}")
        if recent_concern:
            lines.append(f"- **최근 고민**: {recent_concern}")
        if product_experience:
            lines.append(f"- **제품 경험**: {product_experience}")
        if felt_effect:
            lines.append(f"- **느낀 효과**: {felt_effect}")
        if problem or customer_state or recent_concern or product_experience or felt_effect:
            lines.append("")

        excerpt = _excerpt(review.get("body"))
        if excerpt:
            lines.append(f"> {excerpt}")
        review_id = review.get("id")
        if review_id is not None:
            lines.append(f"\n_review_id: `{review_id}`_")
        lines.append("")

    lines.append(
        "Weave these source-backed customer contexts into the draft, and "
        "record the ones you used under the content variation's "
        "`featured_product_reviews` metadata (review_id, context_score, "
        "customer_state, recent_concern, product_experience, felt_effect, excerpt)."
    )
    return "\n".join(lines)
