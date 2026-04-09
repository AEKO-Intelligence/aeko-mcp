"""MCP tools for writing changes back to connected Cafe24 / Shopify stores.

Wraps the AEKO backend's /api/store-integrations/{id}/products/{ext_id}
endpoint (and audit + revert endpoints) so Claude Desktop can apply
pdp_update suggestions directly to a merchant's live store.

Seven tools total:
  - aeko_list_store_integrations  ← discovery (read-only, all tiers)
  - aeko_update_product_description
  - aeko_update_product_jsonld
  - aeko_update_product_tags
  - aeko_update_product_meta
  - aeko_list_store_writes
  - aeko_revert_store_write

All write tools require a Growth+ plan at the AEKO backend — Starter
calls return a 403 from the backend which surfaces as a RuntimeError
with the full upgrade-pitch message. ``aeko_list_store_integrations``
is available on every tier so Starter users can still see what's
connected.
"""
from typing import Any

from ..server import mcp, client


def _safe(method, *args, **kwargs) -> tuple[dict | None, str | None]:
    """Same error-wrapping pattern used in tools/campaigns.py."""
    try:
        return method(*args, **kwargs), None
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


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


@mcp.tool()
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
    subscription tier (the write tools themselves are Growth+).
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


@mcp.tool()
def aeko_update_product_description(
    integration_id: str,
    external_product_id: str,
    description_html: str,
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
    """
    return _update_product(
        integration_id,
        external_product_id,
        {"description": description_html},
    )


@mcp.tool()
def aeko_update_product_jsonld(
    integration_id: str,
    external_product_id: str,
    json_ld: dict,
) -> str:
    """Replace the JSON-LD structured data embedded in a product's description HTML.

    Does NOT touch the surrounding prose — the backend fetches the current
    description, strips any existing <script type="application/ld+json">
    block, and injects the new one at the end.

    Args:
        integration_id: UUID of the store integration.
        external_product_id: Cafe24 product_no or Shopify product id.
        json_ld: The structured data object (typed as a dict).
            Example: {"@context": "https://schema.org", "@type": "Product",
            "name": "Mattress X", ...}
    """
    return _update_product(
        integration_id,
        external_product_id,
        {"json_ld": json_ld},
    )


@mcp.tool()
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


@mcp.tool()
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


@mcp.tool()
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


@mcp.tool()
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
