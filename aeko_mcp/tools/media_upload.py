"""Media upload helper for aeko.shop syndication."""
from ..server import client, mcp
from ._annotations import WRITE


@mcp.tool(title="Request aeko.shop media upload URL", annotations=WRITE)
def aeko_request_media_upload(
    brand_kit_id: str,
    source_content_id: str,
    filename: str,
    content_type: str,
    content_sha256: str,
    content_md5: str,
    byte_length: int,
) -> dict:
    """Return a pre-signed PUT URL and public CDN URL for a local article image.

    Args:
        brand_kit_id: UUID of the AEKO Brand Kit to upload under. The backend
            syncs this Brand Kit to the corresponding aeko.shop brand before
            issuing the signed URL.
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
    """
    return client.post(
        "/api/aeko-shop/media/presign",
        json={
            "brand_kit_id": brand_kit_id,
            "source_content_id": source_content_id,
            "filename": filename,
            "content_type": content_type,
            "content_sha256": content_sha256,
            "content_md5": content_md5,
            "byte_length": byte_length,
        },
    )
