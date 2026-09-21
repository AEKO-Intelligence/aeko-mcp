"""MCP tools for writing changes back to connected Cafe24 / Shopify stores.

Wraps the AEKO backend's /api/store-integrations/{id}/products/{ext_id}
endpoint (and audit + revert endpoints) so Claude Desktop can apply
pdp_update suggestions directly to a merchant's live store.

Write tools include:
  - aeko_list_store_integrations  ← discovery (read-only, all tiers)
  - aeko_get_product_description  ← raw editable HTML (read-only)
  - aeko_update_product_description
  - aeko_update_product_tags
  - aeko_update_product_meta
  - aeko_update_product_page  ← one atomic PDP patch + one audit record
  - aeko_list_store_writes
  - aeko_revert_store_write

JSON-LD is stored inside the description HTML. The atomic page tool accepts it
as a separate field so the backend can merge it with the current or proposed
description in the same audited request.

Agent-initiated product writes are fenced by an ActionItem execution claim.
The caller passes the ActionItem id and the unique claim token returned by
``aeko_claim_action_item``; the backend validates the artifact tier and exact
store/product target while holding that claim through the platform mutation.
``aeko_list_store_integrations`` remains read-only and available on every tier.

``aeko_get_product_description``, ``aeko_update_product_page`` and
``aeko_list_store_writes`` return structured results and raise
``aeko.error.v1`` failures (see ``_structured``). Keep annotations in this
module as runtime types for MCP 1.11/1.12.
"""
import base64
import hashlib
import json
import mimetypes
import os
import re
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx

from ..client import AekoAPIError, legacy_error_name
from ..server import mcp, client
from ._annotations import DESTRUCTIVE, READ_ONLY, WRITE, WRITE_ONCE
from ._structured import (
    AekoToolError,
    AekoToolInputError,
    CodedRuntimeError,
    ProductDescription,
    StoreWriteHistoryItem,
    StoreWriteHistoryPage,
    StoreWriteReceipt,
    api_error,
    optional_uuid,
    path_segment_arg,
    read_boundary,
    uuid_arg,
)

INJECT_PRODUCTS_BATCH_SIZE = 200
MAX_STORE_WRITE_HISTORY_PAGE = 200
MAX_PAYLOAD_SENT_BYTES = 32 * 1024

# Backend codes raised before the write handler touches the store.
_PRE_WRITE_REJECTION_CODES = frozenset(
    {
        "ACTION_ITEM_CLAIM_REQUIRED",
        "ACTION_ITEM_STATUS_CONFLICT",
        "ACTION_ITEM_NOT_STORE_WRITABLE",
        "ACTION_ITEM_PAYLOAD_MISMATCH",
        "ACTION_ITEM_TARGET_MISMATCH",
        "SUBSCRIPTION_INACTIVE",
        "TIER_REQUIRED",
        "STORE_PRODUCT_NOT_FOUND",
        "STORE_SNAPSHOT_FAILED",
    }
)
# Codes after which this claim's store mutation may exist. The backend keeps the
# claim fence indeterminate for network/generic platform failures.
_UNKNOWN_WRITE_CODES = frozenset(
    {
        "ACTION_ITEM_WRITE_INDETERMINATE",
        "ACTION_ITEM_WRITE_PAYLOAD_CONFLICT",
        "NETWORK_ERROR",
        "PLATFORM_ERROR",
    }
)
# Untyped FastAPI rejections (auth, feature gate, ownership, validation, rate
# limit) are raised before any store request.
_PLAIN_REJECTION_STATUSES = frozenset({400, 401, 403, 404, 422, 429})

_UNKNOWN_RECEIPT_MESSAGE = (
    "AEKO did not return a valid write receipt. The write may have happened; reconcile the "
    "product and store write history before recovery and do not resubmit."
)
_IMAGE_UPLOAD_FAILED_MESSAGE = (
    "A local image could not be uploaded, so the store write was not sent."
)
_SAFE_HISTORY_ERROR_CODE = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")
_HISTORY_ERROR_MESSAGES = {
    "INSUFFICIENT_SCOPE": "The connected store credential lacks permission to update products.",
    "NETWORK_ERROR": "The connection between AEKO and the store failed during the write.",
    "PLATFORM_ERROR": "The connected store returned an error during the write.",
    "PRODUCT_NOT_FOUND": "The product was not found on the connected store.",
    "RATE_LIMIT": "The connected store rate-limited the write.",
    "REAUTH": "The connected store rejected its credential. Reconnect the store.",
    "VALIDATION": "The connected store rejected the product update as invalid.",
}
_GENERIC_HISTORY_ERROR_MESSAGE = (
    "The store write failed. Use the error code and audit ID for reconciliation."
)


def _is_utf8_text(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        value.encode("utf-8")
    except UnicodeError:
        return False
    return True


class _MissingImageDomain(RuntimeError):
    """Local image references need a domain for the aeko.shop media presign."""


def _safe(method, *args, **kwargs) -> tuple[dict | None, str | None]:
    """Wrap client errors into (None, message) for graceful tool output."""
    try:
        return method(*args, **kwargs), None
    except Exception as e:  # noqa: BLE001
        return None, f"{legacy_error_name(e)}: {e}"


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
    action_item_id: str | None = None,
    execution_claim_id: str | None = None,
) -> str:
    if action_item_id is not None:
        body["action_item_id"] = action_item_id
    if execution_claim_id is not None:
        body["execution_claim_id"] = execution_claim_id
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


@mcp.tool(title="Sync store products", annotations=DESTRUCTIVE)
def aeko_sync_store(integration_id: str) -> str:
    """Sync products/reviews and replace the public aeko.shop catalog snapshot.

    This can remove public products that are absent from a partial upstream
    response, so callers must confirm the public effect and inspect the
    integration's post-sync status. Manual stores are push-only; update them
    with `aeko_inject_products`.
    """
    result, err = _safe(client.post, f"/api/store-integrations/{integration_id}/sync")
    if err:
        return f"# Failed to sync store\n\n```\n{err}\n```"
    return _json_block("Public store catalog and reviews synced", result)


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
            raise _MissingImageDomain(
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

    Returns markdown with one block per integration, including its AEKO
    ``domain_id``. Discovery is available on every subscription tier; an
    agent write is authorized by the claimed artifact's current tier.
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
        lines.append(f"- **Domain ID**: `{item.get('domain_id', '?')}`")
        lines.append(f"- **Platform**: {platform}")
        lines.append(f"- **Store**: `{store}`")
        lines.append(f"- **Write-back**: {write_badge}")
        if item.get("last_synced_at"):
            lines.append(f"- **Last synced**: {item['last_synced_at']}")
        if item.get("last_sync_status"):
            lines.append(f"- **Last sync status**: {item['last_sync_status']}")
        if item.get("last_sync_error_message"):
            lines.append(
                f"- **Last sync error**: {item['last_sync_error_message']}"
            )
        lines.append("")

    lines.append(
        "Pass the `id` value above as `integration_id` to "
        "`aeko_update_product_description`, `aeko_update_product_tags`, etc."
    )
    return "\n".join(lines)


@mcp.tool(
    title="Get product description HTML",
    annotations=READ_ONLY,
    structured_output=True,
)
def aeko_get_product_description(
    integration_id: str,
    external_product_id: str,
) -> ProductDescription:
    """Fetch the raw editable product description HTML from the connected store.

    Returns the source-of-truth description as stored in Cafe24 (`description`
    field) or Shopify (`body_html`) — distinct from what a live-page
    WebFetch would return. ``description_html`` is the exact store value, or
    null when the store has none; use it byte for byte as the base for
    `aeko_update_product_page`. A failure is an MCP error carrying one
    aeko.error.v1 JSON object.

    Args:
        integration_id: UUID of the store integration. Call
            `aeko_list_store_integrations` first to discover it.
        external_product_id: The product's platform-native id — Cafe24
            product_no or Shopify product id.
    """
    with read_boundary():
        integration_id = uuid_arg(integration_id, "integration_id")
        external_product_id = path_segment_arg(external_product_id, "external_product_id")
        data = client.get(
            f"/api/store-integrations/{integration_id}/products/"
            f"{external_product_id}/description"
        )
        return _product_description(data, integration_id, external_product_id)


def _product_description(
    data: Any, integration_id: str, external_product_id: str
) -> ProductDescription:
    if not isinstance(data, dict):
        raise CodedRuntimeError(
            "INVALID_BACKEND_RESPONSE", "AEKO returned an unexpected product description."
        )
    returned_integration = optional_uuid(data.get("integration_id"))
    if (
        returned_integration is None
        or str(UUID(returned_integration)) != integration_id
        or data.get("external_product_id") != external_product_id
    ):
        raise CodedRuntimeError(
            "PRODUCT_IDENTITY_MISMATCH",
            "AEKO returned a description for a different store product.",
        )
    description_html = data.get("description_html")
    if (
        "description_html" not in data
        or not (description_html is None or _is_utf8_text(description_html))
        or not _is_utf8_text(data.get("platform"))
        or not data["platform"]
        or not _is_utf8_text(data.get("fetched_at"))
    ):
        raise CodedRuntimeError(
            "INVALID_BACKEND_RESPONSE", "AEKO returned an unexpected product description."
        )
    return ProductDescription(
        integration_id=integration_id,
        external_product_id=external_product_id,
        platform=data["platform"],
        description_html=description_html,
        fetched_at=data["fetched_at"],
    )


@mcp.tool(title="Update product description", annotations=WRITE)
def aeko_update_product_description(
    integration_id: str,
    external_product_id: str,
    description_html: str,
    skip_aeko_shop: bool = False,
    domain_id: str | None = None,
    action_item_id: str | None = None,
    execution_claim_id: str | None = None,
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
        action_item_id: Claimed ActionItem that authorizes this agent write.
        execution_claim_id: Unique token returned by
            ``aeko_claim_action_item`` for that item.
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
        action_item_id,
        execution_claim_id,
    )


@mcp.tool(title="Update product tags", annotations=WRITE)
def aeko_update_product_tags(
    integration_id: str,
    external_product_id: str,
    tags: list[str],
    action_item_id: str | None = None,
    execution_claim_id: str | None = None,
) -> str:
    """Replace the tag list for a product on a connected store.

    Args:
        integration_id: UUID of the store integration.
        external_product_id: Cafe24 product_no or Shopify product id.
        tags: Full replacement list (not append). Cafe24 joins with ","
            and Shopify joins with ", " — the backend handles the format
            difference.
        action_item_id: Claimed ActionItem that authorizes this agent write.
        execution_claim_id: Matching execution-claim token.
    """
    return _update_product(
        integration_id,
        external_product_id,
        {"tags": tags},
        action_item_id,
        execution_claim_id,
    )


@mcp.tool(title="Update product SEO meta", annotations=WRITE)
def aeko_update_product_meta(
    integration_id: str,
    external_product_id: str,
    title: str | None = None,
    description: str | None = None,
    action_item_id: str | None = None,
    execution_claim_id: str | None = None,
) -> str:
    """Update SEO meta fields (title tag and meta description) for a product.

    Args:
        integration_id: UUID of the store integration.
        external_product_id: Cafe24 product_no or Shopify product id.
        title: New SEO title (max 255 chars). Cafe24: seo_title. Shopify:
            metafields[global/title_tag].
        description: New meta description (max 1024 chars). Cafe24:
            seo_description. Shopify: metafields[global/description_tag].
        action_item_id: Claimed ActionItem that authorizes this agent write.
        execution_claim_id: Matching execution-claim token.
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
        action_item_id,
        execution_claim_id,
    )


def _write_failure_state(exc: AekoAPIError) -> str:
    """Classify what a failed store-write POST means for the live store."""
    if not exc.request_sent:
        return "not_attempted"
    if exc.code in _UNKNOWN_WRITE_CODES:
        return "unknown"
    if exc.code in _PRE_WRITE_REJECTION_CODES:
        return "rejected"
    status = exc.http_status
    if type(status) is not int:
        return "unknown"
    if optional_uuid(exc.audit_id) is not None:
        # The store call ran and failed. The backend releases the claim fence
        # only for a definite platform 4xx; anything else may follow a mutation.
        return "rejected" if 400 <= status < 500 else "unknown"
    if exc.code is None and status in _PLAIN_REJECTION_STATUSES:
        return "rejected"
    return "unknown"


def _write_receipt(
    result: Any, *, integration_id: str, external_product_id: str
) -> StoreWriteReceipt:
    audit_id = optional_uuid(result.get("audit_id")) if isinstance(result, dict) else None

    def invalid_receipt() -> AekoToolError:
        return AekoToolError(
            "INVALID_WRITE_RECEIPT",
            _UNKNOWN_RECEIPT_MESSAGE,
            mutation_state="unknown",
            audit_id=audit_id,
        )

    if not isinstance(result, dict):
        raise invalid_receipt()
    status = result.get("status")
    http_status = result.get("http_status")
    payload_sent = result.get("payload_sent")
    if (
        audit_id is None
        or status not in ("success", "dry_run")
        or result.get("external_product_id") != external_product_id
        or not isinstance(result.get("platform"), str)
        or not result["platform"]
        or (http_status is not None and type(http_status) is not int)
        or (http_status is not None and not 200 <= http_status < 300)
        or (payload_sent is not None and not isinstance(payload_sent, dict))
    ):
        raise invalid_receipt()
    try:
        payload_bytes = (
            json.dumps(
                payload_sent,
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
            if payload_sent is not None
            else b""
        )
        result["platform"].encode("utf-8")
    except (TypeError, ValueError, UnicodeError):
        raise invalid_receipt() from None
    omitted = len(payload_bytes) > MAX_PAYLOAD_SENT_BYTES
    admin_url = result.get("admin_url")
    if isinstance(admin_url, str) and admin_url.startswith("https://"):
        try:
            admin_url.encode("utf-8")
        except UnicodeError:
            admin_url = None
    else:
        admin_url = None
    try:
        return StoreWriteReceipt(
            store_integration_id=integration_id,
            external_product_id=external_product_id,
            audit_id=audit_id,
            platform=result["platform"],
            status=status,
            store_updated=status == "success",
            http_status=http_status,
            payload_sent=None if omitted else payload_sent,
            payload_sent_omitted=omitted,
            admin_url=admin_url,
        )
    except Exception:  # noqa: BLE001 - malformed data after a submitted write
        raise invalid_receipt() from None


@mcp.tool(
    title="Update product page atomically",
    annotations=WRITE_ONCE,
    structured_output=True,
)
def aeko_update_product_page(
    integration_id: str,
    external_product_id: str,
    action_item_id: str,
    execution_claim_id: str,
    description_html: str | None = None,
    json_ld: dict[str, Any] | None = None,
    tags: list[str] | None = None,
    meta_title: str | None = None,
    meta_description: str | None = None,
    skip_aeko_shop: bool = False,
    domain_id: str | None = None,
) -> StoreWriteReceipt:
    """Apply one confirmed PDP patch in one store request and audit record.

    Use this tool after the user has reviewed the local preview and explicitly
    confirmed the localized Before / After / Risk / Undo summary. Description,
    JSON-LD, tags, and SEO meta are submitted together, so the platform update
    and AEKO audit/revert boundary are a single operation. The backend records
    a request hash on the execution claim: an identical retry replays the
    recorded result, while an indeterminate write is never submitted twice.

    Returns one receipt with the real ``audit_id``. ``status`` is ``success``
    or ``dry_run``; only ``success`` changed the live store. A failure is an
    MCP error whose aeko.error.v1 JSON carries ``mutation_state``:
    ``not_attempted`` or ``rejected`` mean this request changed nothing, and
    ``unknown`` means the write may have happened — reconcile the product and
    `aeko_list_store_writes`, and never resubmit it.

    Args:
        integration_id: UUID of the exact connected store.
        external_product_id: Exact platform-native product id.
        action_item_id: Claimed ``pdp_html`` (or compatible) ActionItem.
        execution_claim_id: Unique token returned by
            ``aeko_claim_action_item``.
        description_html: Final description HTML, if the visible body changes.
            For metadata-only runs this can be omitted; the backend uses the
            current store description as the JSON-LD base.
        json_ld: One structured-data object, normally an ``@graph`` containing
            Product and any evidence-backed FAQPage/Review nodes.
        tags: Optional full replacement tag list.
        meta_title: Optional SEO title.
        meta_description: Optional SEO description.
        skip_aeko_shop: Leave local image references untouched when true.
        domain_id: AEKO domain UUID used only when local images must be uploaded
            to aeko.shop before the store patch.
    """
    integration_id = uuid_arg(integration_id, "integration_id")
    external_product_id = path_segment_arg(external_product_id, "external_product_id")
    if not isinstance(action_item_id, str) or not action_item_id or len(action_item_id) > 200:
        raise AekoToolInputError(
            "INVALID_ARGUMENT", "action_item_id must be the claimed action item ID."
        )
    execution_claim_id = uuid_arg(execution_claim_id, "execution_claim_id")
    if all(
        value is None
        for value in (description_html, json_ld, tags, meta_title, meta_description)
    ):
        raise AekoToolInputError("INVALID_ARGUMENT", "Set at least one PDP field.")

    clean_html = description_html
    if description_html is not None and not skip_aeko_shop:
        source_content_id = f"store-product:{integration_id}:{external_product_id}"
        try:
            clean_html = _upload_local_images_for_aeko_shop(
                source_content_id,
                description_html,
                domain_id,
            )
        except _MissingImageDomain:
            raise AekoToolInputError(
                "INVALID_ARGUMENT",
                "Local <img src> references require domain_id, or set skip_aeko_shop=true.",
            ) from None
        except AekoAPIError as exc:
            raise api_error(
                exc,
                mutation_state="not_attempted",
                code="IMAGE_UPLOAD_FAILED",
                message=_IMAGE_UPLOAD_FAILED_MESSAGE,
            ) from None
        except Exception:  # noqa: BLE001 - local file or blob upload failure
            raise AekoToolError("IMAGE_UPLOAD_FAILED", _IMAGE_UPLOAD_FAILED_MESSAGE) from None

    body: dict[str, Any] = {"skip_aeko_shop": skip_aeko_shop}
    if clean_html is not None:
        body["description"] = clean_html
    if json_ld is not None:
        body["json_ld"] = json_ld
    if tags is not None:
        body["tags"] = tags
    if meta_title is not None or meta_description is not None:
        body["meta"] = {
            key: value
            for key, value in {
                "title": meta_title,
                "description": meta_description,
            }.items()
            if value is not None
        }
    body["action_item_id"] = action_item_id
    body["execution_claim_id"] = execution_claim_id

    try:
        json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError):
        raise AekoToolInputError(
            "INVALID_ARGUMENT", "PDP fields must contain valid JSON values and UTF-8 text."
        ) from None

    path = f"/api/store-integrations/{integration_id}/products/{external_product_id}"
    # Submit exactly once. Nothing below retries, whatever the failure.
    try:
        result = client.post(path, json=body)
    except AekoAPIError as exc:
        raise api_error(exc, mutation_state=_write_failure_state(exc)) from None
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout):
        raise AekoToolError(
            "BACKEND_UNREACHABLE", "AEKO could not be reached, so the store write was not sent."
        ) from None
    except httpx.TimeoutException:
        raise AekoToolError(
            "WRITE_RESULT_UNKNOWN",
            "AEKO did not respond before the timeout. The write may have happened; reconcile "
            "before recovery and do not resubmit.",
            mutation_state="unknown",
        ) from None
    except json.JSONDecodeError:
        raise AekoToolError(
            "INVALID_WRITE_RECEIPT", _UNKNOWN_RECEIPT_MESSAGE, mutation_state="unknown"
        ) from None
    except Exception:  # noqa: BLE001 - any other failure after submission
        raise AekoToolError(
            "WRITE_RESULT_UNKNOWN",
            "The write request failed after it may have reached AEKO. Reconcile before "
            "recovery and do not resubmit.",
            mutation_state="unknown",
        ) from None
    return _write_receipt(
        result, integration_id=integration_id, external_product_id=external_product_id
    )


_HISTORY_TEXT_FIELDS = ("platform", "external_product_id", "operation", "status", "created_at")


def _history_page(data: Any, *, limit: int, offset: int) -> StoreWriteHistoryPage:
    items = data.get("items") if isinstance(data, dict) else None
    total = data.get("total") if isinstance(data, dict) else None
    if (
        not isinstance(items, list)
        or type(total) is not int
        or total < 0
        or len(items) > limit
        or (bool(items) and offset + len(items) > total)
        or (offset < total and not items)
    ):
        raise CodedRuntimeError(
            "INVALID_BACKEND_RESPONSE", "AEKO returned an unexpected store write history page."
        )
    parsed = []
    for item in items:
        if (
            not isinstance(item, dict)
            or optional_uuid(item.get("id")) is None
            or optional_uuid(item.get("store_integration_id")) is None
            or any(not _is_utf8_text(item.get(field)) for field in _HISTORY_TEXT_FIELDS)
            or (
                item.get("error_code") is not None
                and (
                    not isinstance(item.get("error_code"), str)
                    or _SAFE_HISTORY_ERROR_CODE.fullmatch(item["error_code"]) is None
                )
            )
            or (
                item.get("error_message") is not None
                and not isinstance(item.get("error_message"), str)
            )
            or (
                item.get("revert_of_audit_id") is not None
                and optional_uuid(item.get("revert_of_audit_id")) is None
            )
        ):
            raise CodedRuntimeError(
                "INVALID_BACKEND_RESPONSE", "AEKO returned an invalid store write history item."
            )
        fields = {field: item.get(field) for field in StoreWriteHistoryItem.model_fields}
        if fields["error_message"] is not None:
            fields["error_message"] = _HISTORY_ERROR_MESSAGES.get(
                fields["error_code"], _GENERIC_HISTORY_ERROR_MESSAGE
            )
        parsed.append(StoreWriteHistoryItem(**fields))
    end = offset + len(parsed)
    return StoreWriteHistoryPage(
        items=parsed,
        total=total,
        limit=limit,
        offset=offset,
        next_offset=end if parsed and end < total else None,
    )


@mcp.tool(
    title="List store write history",
    annotations=READ_ONLY,
    structured_output=True,
)
def aeko_list_store_writes(limit: int = 20, offset: int = 0) -> StoreWriteHistoryPage:
    """List recent store writes for the current user, newest first.

    Each item keeps the audit ``id`` (which `aeko_revert_store_write`
    accepts), its exact ``store_integration_id`` and product, the operation,
    status, and any recorded error. Continue with ``next_offset`` until it is
    null. A failure is an MCP error carrying one aeko.error.v1 JSON object.
    """
    with read_boundary():
        if type(limit) is not int or not 1 <= limit <= MAX_STORE_WRITE_HISTORY_PAGE:
            raise AekoToolInputError(
                "INVALID_ARGUMENT",
                f"limit must be an integer between 1 and {MAX_STORE_WRITE_HISTORY_PAGE}.",
            )
        if type(offset) is not int or offset < 0:
            raise AekoToolInputError("INVALID_ARGUMENT", "offset must be a non-negative integer.")
        result = client.get(
            "/api/store-write-audit",
            params={"limit": limit, "offset": offset},
        )
        return _history_page(result, limit=limit, offset=offset)


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
