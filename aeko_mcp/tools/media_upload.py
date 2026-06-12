"""Media upload helper for aeko.shop syndication."""
from ..server import client, mcp
from ._annotations import WRITE


@mcp.tool(title="Request aeko.shop media upload URL", annotations=WRITE)
def aeko_request_media_upload(
    source_content_id: str,
    filename: str,
    content_type: str,
    content_sha256: str,
    content_md5: str,
    byte_length: int,
    brand_kit_id: str | None = None,
    item_id: str | None = None,
    domain_id: str | None = None,
) -> dict:
    """Return a pre-signed PUT URL and public CDN URL for a local article image.

    **A Brand Kit is OPTIONAL.** Supply ONE publish-identity input: a
    ``brand_kit_id`` when the brand has a kit, otherwise ``item_id`` (preferred —
    the action-item id; ties the upload to the item's verified domain) or
    ``domain_id``. The backend resolves the brand (kit- or domain-derived) and
    syncs it to aeko.shop before issuing the signed URL.

    Args:
        source_content_id: 1..240-char identifier from the executor (typically
            the action-item id). Used in the blob path and idempotency.
        filename: Basename only — no path separators. Must match the backend's
            ``filename_only`` validator.
        content_type: MIME type. Backend pattern: ``^image/(jpeg|jpg|png|webp|gif)$``.
        content_sha256: Lowercase hex SHA-256 of the file body (64 chars).
        content_md5: **Base64**-encoded raw MD5 digest of the file body (exactly
            24 chars including padding). NOT hex — the backend's Pydantic field
            is ``min_length=24, max_length=24``. Compute as
            ``base64.b64encode(hashlib.md5(data).digest()).decode()``.
        byte_length: File size in bytes. Backend caps at 10 MiB.
        brand_kit_id: Optional UUID of the AEKO Brand Kit to upload under.
        item_id: Optional action-item id — resolves the verified-domain identity
            when the brand has no kit. Preferred for kit-less uploads.
        domain_id: Optional domain UUID — alternative kit-less identity input.
    """
    payload: dict = {
        "source_content_id": source_content_id,
        "filename": filename,
        "content_type": content_type,
        "content_sha256": content_sha256,
        "content_md5": content_md5,
        "byte_length": byte_length,
    }
    # Forward only the identity input(s) the caller supplied; the backend resolves
    # a kit- or domain-derived brand and 400s if none is usable.
    if brand_kit_id:
        payload["brand_kit_id"] = brand_kit_id
    if item_id:
        payload["item_id"] = item_id
    if domain_id:
        payload["domain_id"] = domain_id
    return client.post("/api/aeko-shop/media/presign", json=payload)
