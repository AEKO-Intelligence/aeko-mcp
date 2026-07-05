"""MCP tools for writing changes back to connected Cafe24 / Shopify stores.

Wraps the AEKO backend's /api/store-integrations/{id}/products/{ext_id}
endpoint (and audit + revert endpoints) so Claude Desktop can apply
pdp_update suggestions directly to a merchant's live store.

Seven tools total:
  - aeko_list_store_integrations  ← discovery (read-only, all tiers)
  - aeko_get_product_description  ← raw editable HTML (read-only)
  - aeko_update_product_description
  - aeko_update_product_tags
  - aeko_update_product_meta
  - aeko_list_store_writes
  - aeko_revert_store_write

JSON-LD lives inside the description HTML and is written via
`aeko_update_product_description` — there is no separate JSON-LD
write tool.

Post-tier-restructure (4→3 tiers, 2026-04-27): all write tools are
available on every active subscription tier (Starter / Pro / Enterprise).
Inactive or trial-expired accounts surface a 403 from the backend as a
RuntimeError with the full upgrade-pitch message. ``aeko_list_store_integrations``
remains available on every tier so users can always see what's connected.
"""
import base64
import hashlib
import json
import mimetypes
import os
import re
from pathlib import Path
from typing import Any

import httpx

from ..server import mcp, client
from ._annotations import DESTRUCTIVE, READ_ONLY, WRITE, WRITE_ONCE

INJECT_PRODUCTS_BATCH_SIZE = 200


def _safe(method, *args, **kwargs) -> tuple[dict | None, str | None]:
    """Wrap client errors into (None, message) for graceful tool output."""
    try:
        return method(*args, **kwargs), None
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


def _json_block(title: str, payload: Any) -> str:
    return f"# {title}\n\n```json\n{json.dumps(payload, ensure_ascii=False, indent=2, default=str)}\n```"


def _format_result(result: dict) -> list[str]:
    """Render a ProductUpdateResponse as markdown lines."""
    lines: list[str] = []
    lines.append(f"- **Platform**: {result.get('platform', 'unknown')}")
    lines.append(f"- **Product**: `{result.get('external_product_id', '?')}`")
    lines.append(f"- **Status**: {result.get('status', '?')}")
    if result.get("audit_id"):
        lines.append(f"- **Audit ID**: `{result['audit_id']}` — revert with `aeko_revert_store_write(audit_id=...)`")
    if result.get("http_status"):
        lines.append(f"- **HTTP**: {result['http_status']}")
    return lines


def _update_product(
    integration_id: str,
    external_product_id: str,
    body: dict[str, Any],
) -> str:
    path = f"/api/store-integrations/{integration_id}/products/{external_product_id}"
    result, err = _safe(client.post, path, json=body)
    if err:
        return f"# Write failed\n\n```\n{err}\n```"
    if not result:
        return "# Write failed\n\n(no response body)"
    lines = [f"# Store write: {result.get('status', '?').upper()}", ""] + _format_result(result)
    return "\n".join(lines)


@mcp.tool(title="Connect store", annotations=WRITE_ONCE)
def aeko_connect_store(
    domain_id: str,
    platform: str,
    store_identifier: str,
    access_token: str,
    refresh_token: str | None = None,
    token_expires_at: str | None = None,
    scopes: str | None = None,
) -> str:
    """Connect a Cafe24 or Shopify store to a domain.

    Manual/custom stores are created by `aeko_inject_products`, not this
    OAuth/token connect route.
    """
    normalized_platform = platform.strip().lower()
    if normalized_platform == "manual":
        return (
            "# Manual stores use product inject\n\n"
            "Call `aeko_inject_products(domain_id=..., products=[...])`; it "
            "creates the credential-less manual store internally."
        )
    if normalized_platform not in {"cafe24", "shopify"}:
        return "Platform must be `cafe24` or `shopify`. Use `aeko_inject_products` for manual stores."

    body = {
        "domain_id": domain_id,
        "platform": normalized_platform,
        "store_identifier": store_identifier,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_expires_at": token_expires_at,
        "scopes": scopes,
    }
    payload = {k: v for k, v in body.items() if v is not None}
    result, err = _safe(client.post, "/api/store-integrations", json=payload)
    if err:
        return f"# Failed to connect store\n\n```\n{err}\n```"
    return _json_block("Store connected", result)


@mcp.tool(title="Sync store products", annotations=WRITE)
def aeko_sync_store(integration_id: str) -> str:
    """Sync products from a connected Cafe24/Shopify store.

    Manual stores are push-only; update them with `aeko_inject_products`.
    """
    result, err = _safe(client.post, f"/api/store-integrations/{integration_id}/sync")
    if err:
        return f"# Failed to sync store\n\n```\n{err}\n```"
    return _json_block("Store products synced", result)


@mcp.tool(title="Inject manual products", annotations=WRITE_ONCE)
def aeko_inject_products(domain_id: str, products: list[dict]) -> str:
    """Inject products for a custom/manual store.

    The backend get-or-creates a credential-less manual store for `domain_id`
    and upserts by `external_product_id`. Each product needs stable
    `external_product_id`, `title`, `product_url`, and `public_url`.
    """
    if not products:
        return "# No products to inject — pass a non-empty `products` list."

    if len(products) <= INJECT_PRODUCTS_BATCH_SIZE:
        result, err = _safe(
            client.post,
            "/api/store-integrations/products/inject",
            json={"domain_id": domain_id, "products": products},
        )
        if err:
            return f"# Failed to inject products\n\n```\n{err}\n```"
        return _json_block("Products injected", result)

    batches = [
        products[i : i + INJECT_PRODUCTS_BATCH_SIZE]
        for i in range(0, len(products), INJECT_PRODUCTS_BATCH_SIZE)
    ]
    combined: dict[str, Any] = {
        "domain_id": domain_id,
        "requested": len(products),
        "batches": len(batches),
        "batches_completed": 0,
        "synced": 0,
        "skipped": 0,
        "integration_id": None,
    }
    errors: list[str] = []
    for batch in batches:
        result, err = _safe(
            client.post,
            "/api/store-integrations/products/inject",
            json={"domain_id": domain_id, "products": batch},
        )
        if err:
            errors.append(err)
            continue
        combined["batches_completed"] += 1
        if isinstance(result, dict):
            combined["synced"] += int(result.get("synced") or 0)
            combined["skipped"] += int(result.get("skipped") or 0)
            combined["integration_id"] = combined["integration_id"] or result.get("integration_id")
    if errors:
        combined["errors"] = errors
    return _json_block("Products injected", combined)


@mcp.tool(title="List store products", annotations=READ_ONLY)
def aeko_list_store_products(
    store_integration_id: str | None = None,
    domain_id: str | None = None,
    include_citability: bool = False,
    limit: int = 50,
    offset: int = 0,
    sort: str = "synced_desc",
    aeo_status: str | None = None,
) -> str:
    """List synced/manual store products with stable external product IDs."""
    params: dict[str, Any] = {
        "include_citability": include_citability,
        "limit": max(1, min(int(limit), 500)),
        "offset": max(0, int(offset)),
        "sort": sort,
    }
    if store_integration_id:
        params["store_integration_id"] = store_integration_id
    if domain_id:
        params["domain_id"] = domain_id
    if aeo_status:
        params["aeo_status"] = aeo_status
    result, err = _safe(client.get, "/api/store-products", params=params)
    if err:
        return f"# Failed to list store products\n\n```\n{err}\n```"
    return _json_block("Store products", result)


def _upload_local_images_for_aeko_shop(
    source_content_id: str,
    html: str,
    domain_id: str | None = None,
) -> str:
    pattern = re.compile(r'(<img\b[^>]*\bsrc=["\'])(file://[^"\']+|\./[^"\']+|\.\./[^"\']+)(["\'])', re.IGNORECASE)

    def repl(match: re.Match[str]) -> str:
        if not domain_id:
            raise RuntimeError(
                "Local <img src> requires domain_id (the AEKO domain UUID for media presign). "
                "Either pass domain_id to aeko_update_product_description, or set skip_aeko_shop=True "
                "to leave local image references untouched."
            )
        prefix, src, suffix = match.groups()
        path = Path(src[7:]) if src.startswith("file://") else Path.cwd() / src
        data = path.read_bytes()
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        sha256 = hashlib.sha256(data).hexdigest()
        content_md5 = base64.b64encode(hashlib.md5(data).digest()).decode()
        presign = client.post(
            "/api/aeko-shop/media/presign",
            json={
                "domain_id": domain_id,
                "source_content_id": source_content_id,
                "filename": path.name,
                "content_type": content_type,
                "content_sha256": sha256,
                "content_md5": content_md5,
                "byte_length": len(data),
            },
        )
        upload_url = presign["upload_url"]
        with httpx.Client(timeout=60.0) as http:
            resp = http.put(
                upload_url,
                content=data,
                headers={
                    "x-ms-blob-type": "BlockBlob",
                    "Content-Type": content_type,
                    "Content-MD5": content_md5,
                },
            )
            resp.raise_for_status()
        return f"{prefix}{presign['public_url']}{suffix}"

    return pattern.sub(repl, html)


@mcp.tool(title="List connected stores", annotations=READ_ONLY)
def aeko_list_store_integrations() -> str:
    """List every Cafe24 / Shopify store connected to the current user's AEKO account.

    This is the starting point for any write-back workflow — call this
    first to discover the ``integration_id`` you need for
    ``aeko_update_product_*``. Each row also shows whether the granted
    OAuth scopes include write access (Cafe24: ``mall.write_product``,
    Shopify: ``write_products``). If the integration doesn't have write
    scopes yet, the user needs to reconnect from the AEKO dashboard
    Settings → Store Integrations tab.

    Returns markdown with one block per integration. Available on every
    subscription tier (and post-2026-04-27 the write tools themselves are
    also available on every active tier — Starter / Pro / Enterprise).
    """
    result, err = _safe(client.get, "/api/store-integrations")
    if err:
        return f"# Failed to list store integrations\n\n```\n{err}\n```"
    # The backend returns a JSON array at the top level.
    items = result if isinstance(result, list) else []
    if not items:
        return (
            "# No connected stores\n\n"
            "Connect a Cafe24 or Shopify store from the AEKO dashboard "
            "Settings → Store Integrations tab, then call this tool again."
        )

    lines = [f"# Connected stores ({len(items)})", ""]
    for item in items:
        integration_id = item.get("id", "?")
        platform = item.get("platform", "?")
        store = item.get("store_identifier", "?")
        scopes = item.get("scopes") or ""

        if platform == "manual":
            # A credential-less custom source has no live storefront API to push to —
            # its catalog is maintained via aeko_inject_products, not store write-back.
            write_badge = "📦 Manual catalog — update via `aeko_inject_products` (no live-store write-back)"
        else:
            if platform == "cafe24":
                write_enabled = "mall.write_product" in scopes
            elif platform == "shopify":
                write_enabled = "write_products" in scopes
            else:
                write_enabled = False

            write_badge = "✅ Write enabled" if write_enabled else "⚠️ Read-only (reconnect in Settings to enable writes)"

        lines.append(f"## `{integration_id}`")
        lines.append(f"- **Platform**: {platform}")
        lines.append(f"- **Store**: `{store}`")
        lines.append(f"- **Write-back**: {write_badge}")
        if item.get("last_synced_at"):
            lines.append(f"- **Last synced**: {item['last_synced_at']}")
        lines.append("")

    lines.append(
        "Pass the `id` value above as `integration_id` to "
        "`aeko_update_product_description`, `aeko_update_product_tags`, etc."
    )
    return "\n".join(lines)


@mcp.tool(title="Get product description HTML", annotations=READ_ONLY)
def aeko_get_product_description(
    integration_id: str,
    external_product_id: str,
) -> str:
    """Fetch the raw editable product description HTML from the connected store.

    Returns the source-of-truth description as stored in Cafe24 (`description`
    field) or Shopify (`body_html`) — distinct from what a live-page
    WebFetch would return. Use this to read → patch → write back via
    `aeko_update_product_description`, e.g. for a JSON-LD refresh that
    updates `AggregateRating.ratingValue` without touching the rest of the
    HTML.

    Args:
        integration_id: UUID of the store integration. Call
            `aeko_list_store_integrations` first to discover it.
        external_product_id: The product's platform-native id — Cafe24
            product_no or Shopify product id.
    """
    path = (
        f"/api/store-integrations/{integration_id}/products/"
        f"{external_product_id}/description"
    )
    data = client.get(path)
    platform = data.get("platform", "unknown")
    description_html = data.get("description_html") or ""
    fetched_at = data.get("fetched_at", "")
    lines = [
        f"# Product description ({platform})",
        "",
        f"- **Integration**: `{integration_id}`",
        f"- **External product ID**: `{external_product_id}`",
        f"- **Fetched at**: {fetched_at}",
        f"- **Length**: {len(description_html)} chars",
        "",
        "## description_html",
        "",
        "```html",
        description_html,
        "```",
    ]
    return "\n".join(lines)


@mcp.tool(title="Update product description", annotations=WRITE)
def aeko_update_product_description(
    integration_id: str,
    external_product_id: str,
    description_html: str,
    skip_aeko_shop: bool = False,
    domain_id: str | None = None,
) -> str:
    """Replace the full description HTML for a product on a connected store.

    Args:
        integration_id: UUID of the store integration. Call
            ``aeko_list_store_integrations`` first to discover it. One
            integration per user/domain pair.
        external_product_id: The product's platform-native id — Cafe24
            product_no or Shopify product id.
        description_html: The new description HTML. May include a
            <script type="application/ld+json"> block; if it does, any
            existing JSON-LD block in the store's current description is
            replaced.
        skip_aeko_shop: When True, leave local ``<img src>`` references
            untouched (no upload to aeko.shop CDN). Use this for stores
            whose domain doesn't have an aeko.shop tenant.
        domain_id: AEKO domain UUID — required when
            ``skip_aeko_shop=False`` AND the description contains local
            image references (file://, ./, ../). Maps to backend
            ``MediaPresignRequest.domain_id``. Pass the domain UUID, NOT the
            store integration_id. Pass-through to
            ``_upload_local_images_for_aeko_shop``.
    """
    source_content_id = f"store-product:{integration_id}:{external_product_id}"
    clean_html = (
        description_html
        if skip_aeko_shop
        else _upload_local_images_for_aeko_shop(source_content_id, description_html, domain_id)
    )
    return _update_product(
        integration_id,
        external_product_id,
        {"description": clean_html, "skip_aeko_shop": skip_aeko_shop},
    )


@mcp.tool(title="Update product tags", annotations=WRITE)
def aeko_update_product_tags(
    integration_id: str,
    external_product_id: str,
    tags: list[str],
) -> str:
    """Replace the tag list for a product on a connected store.

    Args:
        integration_id: UUID of the store integration.
        external_product_id: Cafe24 product_no or Shopify product id.
        tags: Full replacement list (not append). Cafe24 joins with ","
            and Shopify joins with ", " — the backend handles the format
            difference.
    """
    return _update_product(
        integration_id,
        external_product_id,
        {"tags": tags},
    )


@mcp.tool(title="Update product SEO meta", annotations=WRITE)
def aeko_update_product_meta(
    integration_id: str,
    external_product_id: str,
    title: str | None = None,
    description: str | None = None,
) -> str:
    """Update SEO meta fields (title tag and meta description) for a product.

    Args:
        integration_id: UUID of the store integration.
        external_product_id: Cafe24 product_no or Shopify product id.
        title: New SEO title (max 255 chars). Cafe24: seo_title. Shopify:
            metafields[global/title_tag].
        description: New meta description (max 1024 chars). Cafe24:
            seo_description. Shopify: metafields[global/description_tag].
    """
    meta: dict[str, str] = {}
    if title is not None:
        meta["title"] = title
    if description is not None:
        meta["description"] = description
    if not meta:
        return "# Nothing to update\n\nSet at least one of `title` or `description`."
    return _update_product(
        integration_id,
        external_product_id,
        {"meta": meta},
    )


@mcp.tool(title="List store write history", annotations=READ_ONLY)
def aeko_list_store_writes(limit: int = 20, offset: int = 0) -> str:
    """List recent store writes for the current user, newest first.

    Each row includes the audit id (which `aeko_revert_store_write`
    accepts), the platform, the product id, the operation type, and
    the status.
    """
    result, err = _safe(
        client.get,
        "/api/store-write-audit",
        params={"limit": limit, "offset": offset},
    )
    if err:
        return f"# Failed to list store writes\n\n```\n{err}\n```"
    if not result:
        return "# No store writes recorded yet"

    items = result.get("items", [])
    total = result.get("total", 0)
    if not items:
        return "# No store writes recorded yet"

    lines = [f"# Store writes (showing {len(items)} of {total})", ""]
    for item in items:
        lines.append(f"## `{item.get('id', '?')}`")
        lines.append(f"- **When**: {item.get('created_at', '?')}")
        lines.append(f"- **Platform**: {item.get('platform', '?')}")
        lines.append(f"- **Product**: `{item.get('external_product_id', '?')}`")
        lines.append(f"- **Operation**: {item.get('operation', '?')}")
        lines.append(f"- **Status**: {item.get('status', '?')}")
        if item.get("error_code"):
            lines.append(f"- **Error**: {item['error_code']} — {item.get('error_message', '')}")
        if item.get("revert_of_audit_id"):
            lines.append(f"- **Reverts**: `{item['revert_of_audit_id']}`")
        lines.append("")
    return "\n".join(lines)


@mcp.tool(title="Revert store write", annotations=DESTRUCTIVE)
def aeko_revert_store_write(audit_id: str) -> str:
    """Revert a past store write by pushing the 'before' snapshot back.

    Args:
        audit_id: The audit row id from `aeko_list_store_writes` or from
            the response of a prior update tool. Only rows with
            status='success' can be reverted.
    """
    path = f"/api/store-write-audit/{audit_id}/revert"
    result, err = _safe(client.post, path)
    if err:
        return f"# Revert failed\n\n```\n{err}\n```"
    if not result:
        return "# Revert failed\n\n(no response body)"

    lines = [
        f"# Revert: {result.get('status', '?').upper()}",
        "",
        f"- **Original audit**: `{result.get('original_audit_id', '?')}`",
        f"- **Revert audit**: `{result.get('revert_audit_id', '?')}`",
    ]
    return "\n".join(lines)
