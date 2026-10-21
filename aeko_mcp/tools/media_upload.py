"""Media upload helper for aeko.shop syndication."""
from ..server import client, mcp
from ._annotations import DESTRUCTIVE_IDEMPOTENT_EXTERNAL, tool_spec


@mcp.tool(**tool_spec("Request aeko.shop media upload URL", DESTRUCTIVE_IDEMPOTENT_EXTERNAL))
def aeko_request_media_upload(
    source_content_id: str,
    filename: str,
    content_type: str,
    content_sha256: str,
    content_md5: str,
    byte_length: int,
    item_id: str | None = None,
    domain_id: str | None = None,
) -> dict:
    """Get a pre-signed upload URL and the public aeko.shop CDN URL for one image.

    Use it for local images before putting them in content or product HTML:
    PUT the file bytes to upload_url (headers x-ms-blob-type: BlockBlob,
    Content-Type, Content-MD5), then use public_url in <img src>. The image is
    public once uploaded. AEKO first makes sure the brand exists on aeko.shop,
    which can create or reactivate its public brand page. Pass item_id
    (preferred) or domain_id to identify the brand.

    Args:
        source_content_id: 1-240 character ID, usually the action item ID.
        filename: File name only, no path.
        content_type: image/jpeg, image/png, image/webp or image/gif.
        content_sha256: Lowercase hex SHA-256 of the file (64 characters).
        content_md5: Base64 of the raw MD5 digest (24 characters), not hex.
        byte_length: File size in bytes, at most 10 MiB.
        item_id: Optional action item ID.
        domain_id: Optional domain UUID.
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
    # the domain-derived identity and 400s if none is usable.
    if item_id:
        payload["item_id"] = item_id
    if domain_id:
        payload["domain_id"] = domain_id
    return client.post("/api/aeko-shop/media/presign", json=payload)
