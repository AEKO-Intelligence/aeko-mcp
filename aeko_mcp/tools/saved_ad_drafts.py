"""Read current, owned saved ad copy without generating or changing it."""

import json
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict

from ..server import client, mcp
from ._annotations import READ_ONLY, tool_spec
from ._paging import MAX_PAGE_CHARS
from ._structured import AekoToolError, AekoToolInputError, read_boundary, text_bytes, uuid_arg


class SavedAdDraft(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    title: str
    body: str
    saved_version: str
    source_snapshot: Optional[dict[str, Any]] = None
    source_snapshot_omitted: bool = False
    source_snapshot_json_chunk: Optional[dict[str, Any]] = None


class SavedAdDraftPage(BaseModel):
    items: list[SavedAdDraft]
    total: int
    limit: int
    offset: int
    returned_count: int
    next_offset: Optional[int]
    has_more: bool
    output_limited: bool


def _draft(value: Any) -> SavedAdDraft:
    try:
        return SavedAdDraft.model_validate(value)
    except Exception:
        raise AekoToolError("INVALID_BACKEND_RESPONSE", "AEKO returned an invalid saved ad draft.") from None


def _owned_draft(value: Any, domain_id: str) -> SavedAdDraft:
    result = _draft(value)
    if result.model_extra and "domain_id" in result.model_extra:
        try:
            backend_domain_id = uuid_arg(result.model_extra["domain_id"], "backend domain_id")
        except AekoToolInputError:
            raise AekoToolError("INVALID_BACKEND_RESPONSE", "AEKO returned an invalid saved ad draft domain.") from None
        if backend_domain_id != domain_id:
            raise AekoToolError("INVALID_BACKEND_RESPONSE", "AEKO returned a saved ad draft from another domain.")
    return result


def _snapshot_text(draft: SavedAdDraft) -> Optional[str]:
    if draft.source_snapshot is None:
        return None
    return json.dumps(draft.source_snapshot, ensure_ascii=False, separators=(",", ":"), default=str)


def _list_item(draft: SavedAdDraft) -> SavedAdDraft:
    if text_bytes(draft) <= 8000:
        return draft
    if draft.source_snapshot is None:
        return draft
    return draft.model_copy(update={"source_snapshot": None, "source_snapshot_omitted": True})


def _too_large() -> AekoToolError:
    return AekoToolError(
        "OUTPUT_TOO_LARGE",
        "The saved ad draft has oversized non-source fields; AEKO cannot return it without shortening saved copy.",
    )


@mcp.tool(**tool_spec("List current saved ad drafts", READ_ONLY, structured_output=True))
def aeko_list_saved_ad_drafts(domain_id: str, limit: int = 50, offset: int = 0) -> SavedAdDraftPage:
    """Read one page of current saved, unplaced ad drafts for a domain.

    Copy, saved_version, and accessible source provenance come from the saved
    creative, not a review preparation cache. Large source snapshots are omitted
    from list rows with source_snapshot_omitted=true; get that draft to read its
    source evidence. Continue at next_offset when
    has_more is true. A page can contain fewer than limit rows when its output
    is large; no copy within a returned row is shortened. No ad account is needed.
    """
    with read_boundary():
        domain_id = uuid_arg(domain_id, "domain_id")
        if type(limit) is not int or not 1 <= limit <= 100:
            raise AekoToolInputError("INVALID_ARGUMENT", "limit must be an integer from 1 to 100.")
        if type(offset) is not int or not 0 <= offset <= 2**31 - 1:
            raise AekoToolInputError("INVALID_ARGUMENT", "offset must be a nonnegative integer.")
        data = client.get("/api/marketing/ad-creatives/saved", params={
            "domain_id": domain_id, "limit": limit, "offset": offset,
        })
        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            raise AekoToolError("INVALID_BACKEND_RESPONSE", "AEKO returned an invalid saved ad draft page.")
        total, backend_limit, backend_offset = (data.get(key) for key in ("total", "limit", "offset"))
        if (type(total) is not int or total < 0 or type(backend_limit) is not int
                or backend_limit != limit or type(backend_offset) is not int
                or backend_offset != offset or len(data["items"]) > limit
                or (data["items"] and offset + len(data["items"]) > total)):
            raise AekoToolError("INVALID_BACKEND_RESPONSE", "AEKO returned inconsistent saved ad draft pagination.")
        items = [_list_item(_owned_draft(item, domain_id)) for item in data["items"]]
        if offset + len(items) < total and not items:
            raise AekoToolError("INVALID_BACKEND_RESPONSE", "AEKO returned an empty saved ad draft page before the end.")
        def page(count: int) -> SavedAdDraftPage:
            next_offset = offset + count if offset + count < total else None
            return SavedAdDraftPage(
                items=items[:count], total=total, limit=limit, offset=offset,
                returned_count=count, next_offset=next_offset,
                has_more=next_offset is not None, output_limited=count < len(items),
            )
        count = len(items)
        result = page(count)
        while count > 1 and text_bytes(result) > MAX_PAGE_CHARS:
            count -= 1
            result = page(count)
        if text_bytes(result) > MAX_PAGE_CHARS:
            raise _too_large()
        return result


@mcp.tool(**tool_spec("Get current saved ad draft", READ_ONLY, structured_output=True))
def aeko_get_saved_ad_draft(
    domain_id: str, creative_id: str, source_offset: int = 0, source_limit: int = 8000
) -> SavedAdDraft:
    """Read the latest saved copy, version and accessible provenance of one draft.

    This is a fresh backend read. Small source snapshots are returned whole.
    Large snapshots are returned as JSON text chunks with total_chars and
    next_offset. Pass next_offset as source_offset until it is null; keep the
    saved_version the same across calls to avoid mixing edited snapshots.
    It neither regenerates nor publishes the ad.
    """
    with read_boundary():
        domain_id = uuid_arg(domain_id, "domain_id")
        creative_id = uuid_arg(creative_id, "creative_id")
        if type(source_offset) is not int or source_offset < 0:
            raise AekoToolInputError("INVALID_ARGUMENT", "source_offset must be a nonnegative integer.")
        if type(source_limit) is not int or not 1 <= source_limit <= 8000:
            raise AekoToolInputError("INVALID_ARGUMENT", "source_limit must be an integer from 1 to 8000.")
        data = client.get(
            f"/api/marketing/ad-creatives/saved/{creative_id}", params={"domain_id": domain_id}
        )
        result = _owned_draft(data, domain_id)
        if result.id != creative_id:
            raise AekoToolError("INVALID_BACKEND_RESPONSE", "AEKO returned a different saved ad draft.")
        source_text = _snapshot_text(result)
        if source_text is None:
            if source_offset:
                raise AekoToolInputError("INVALID_ARGUMENT", "source_offset exceeds the saved source snapshot.")
        elif source_offset > len(source_text):
            raise AekoToolInputError("INVALID_ARGUMENT", "source_offset exceeds the saved source snapshot.")
        if source_text is not None and (source_offset > 0 or text_bytes(result) > MAX_PAGE_CHARS or len(source_text) > source_limit):
            original = result
            chunk_length = min(source_limit, len(source_text) - source_offset)
            while True:
                next_offset = source_offset + chunk_length
                result = original.model_copy(update={
                    "source_snapshot": None,
                    "source_snapshot_omitted": True,
                    "source_snapshot_json_chunk": {
                        "text": source_text[source_offset:next_offset],
                        "offset": source_offset,
                        "total_chars": len(source_text),
                        "next_offset": next_offset if next_offset < len(source_text) else None,
                        "saved_version": original.saved_version,
                    },
                })
                if text_bytes(result) <= MAX_PAGE_CHARS:
                    break
                if chunk_length <= 1:
                    raise _too_large()
                chunk_length = max(1, chunk_length // 2)
        if text_bytes(result) > MAX_PAGE_CHARS:
            raise _too_large()
        return result
