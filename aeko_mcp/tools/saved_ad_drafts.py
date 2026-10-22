"""Read current, owned saved ad copy without generating or changing it."""

import json
import re
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict

from ..server import client, mcp
from ._annotations import READ_ONLY, tool_spec
from ._paging import MAX_PAGE_CHARS
from ._structured import AekoToolError, AekoToolInputError, read_boundary, text_bytes, uuid_arg


class SavedAdDraft(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    domain_id: str
    title: str
    body: str
    saved_version: str
    source_snapshot: Optional[dict[str, Any]] = None
    source_snapshot_omitted: bool = False
    source_snapshot_json_chunk: Optional[dict[str, Any]] = None
    ad_copy_format_snapshot: Optional[dict[str, Any]] = None
    ad_copy_format_snapshot_omitted: bool = False
    ad_copy_format_snapshot_json_chunk: Optional[dict[str, Any]] = None


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
    try:
        backend_domain_id = uuid_arg(result.domain_id, "backend domain_id")
    except AekoToolInputError:
        raise AekoToolError("INVALID_BACKEND_RESPONSE", "AEKO returned an invalid saved ad draft domain.") from None
    if backend_domain_id != domain_id:
        raise AekoToolError("INVALID_BACKEND_RESPONSE", "AEKO returned a saved ad draft from another domain.")
    return result


def _json_text(value: Optional[dict[str, Any]]) -> Optional[str]:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _list_item(draft: SavedAdDraft) -> SavedAdDraft:
    """Drop both snapshots from a large row so one row can never fail a page."""
    if text_bytes(draft) <= 8000:
        return draft
    update: dict[str, Any] = {}
    if draft.source_snapshot is not None:
        update.update(source_snapshot=None, source_snapshot_omitted=True)
    if draft.ad_copy_format_snapshot is not None:
        update.update(ad_copy_format_snapshot=None, ad_copy_format_snapshot_omitted=True)
    return draft.model_copy(update=update) if update else draft


def _chunk(text: str, offset: int, length: int, version: str) -> dict[str, Any]:
    next_offset = offset + length
    return {
        "text": text[offset:next_offset], "offset": offset, "total_chars": len(text),
        "next_offset": next_offset if next_offset < len(text) else None, "saved_version": version,
    }


def _too_large() -> AekoToolError:
    return AekoToolError(
        "OUTPUT_TOO_LARGE",
        "The saved ad draft has oversized non-source fields; AEKO cannot return it without shortening saved copy.",
    )


@mcp.tool(**tool_spec("List current saved ad drafts", READ_ONLY, structured_output=True))
def aeko_list_saved_ad_drafts(domain_id: str, limit: int = 50, offset: int = 0) -> SavedAdDraftPage:
    """Read one page of current saved, unplaced ad drafts for a domain.

    Copy, saved_version, and accessible source provenance come from the saved
    creative, not a review preparation cache. Large rows omit source_snapshot and
    ad_copy_format_snapshot (source_snapshot_omitted /
    ad_copy_format_snapshot_omitted = true); get that draft to read them.
    Continue at next_offset when has_more is true. A page can contain fewer than limit rows when its output
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
    domain_id: str, creative_id: str, source_offset: int = 0, source_limit: int = 8000,
    format_offset: int = 0, format_limit: int = 8000, saved_version: Optional[str] = None,
) -> SavedAdDraft:
    """Read the latest saved copy, version and accessible provenance of one draft.

    This is a fresh backend read. Small source_snapshot and ad_copy_format_snapshot
    (which holds the accepted brand constraints) are returned whole. A large one
    is returned as source_snapshot_json_chunk / ad_copy_format_snapshot_json_chunk
    ({text, offset, total_chars, next_offset, saved_version}); when both are large
    the chunks shrink so the response fits. Read each snapshot separately: pass its
    next_offset as source_offset / format_offset until it is null, and join the
    chunk texts to get the JSON. Pass the first read's saved_version on later reads;
    if the draft changed, the call fails with SAVED_AD_CHANGED and you restart from
    offset 0 with the new version. saved_version also changes when the product's
    catalog title changes, for example after a store sync. It neither regenerates
    nor publishes the ad.
    """
    with read_boundary():
        domain_id = uuid_arg(domain_id, "domain_id")
        creative_id = uuid_arg(creative_id, "creative_id")
        for name, value in (("source_offset", source_offset), ("format_offset", format_offset)):
            if type(value) is not int or value < 0:
                raise AekoToolInputError("INVALID_ARGUMENT", f"{name} must be a nonnegative integer.")
        for name, value in (("source_limit", source_limit), ("format_limit", format_limit)):
            if type(value) is not int or not 1 <= value <= 8000:
                raise AekoToolInputError("INVALID_ARGUMENT", f"{name} must be an integer from 1 to 8000.")
        if saved_version is not None and (
            not isinstance(saved_version, str) or not re.fullmatch(r"[0-9a-f]{64}", saved_version)
        ):
            raise AekoToolInputError("INVALID_ARGUMENT", "saved_version must be 64 lowercase hex characters.")
        data = client.get(
            f"/api/marketing/ad-creatives/saved/{creative_id}", params={"domain_id": domain_id}
        )
        original = _owned_draft(data, domain_id)
        if original.id != creative_id:
            raise AekoToolError("INVALID_BACKEND_RESPONSE", "AEKO returned a different saved ad draft.")
        if saved_version is not None and saved_version != original.saved_version:
            raise AekoToolError(
                "SAVED_AD_CHANGED",
                "The saved ad changed since you started reading it. Restart from offset 0 with the "
                f"new saved_version {original.saved_version}.",
            )
        # name -> (text, offset, limit); None text means the snapshot is absent.
        parts = {
            "source": (_json_text(original.source_snapshot), source_offset, source_limit),
            "ad_copy_format": (_json_text(original.ad_copy_format_snapshot), format_offset, format_limit),
        }
        for arg, (text, offset, _) in zip(("source_offset", "format_offset"), parts.values()):
            if offset > (0 if text is None else len(text)):
                raise AekoToolInputError("INVALID_ARGUMENT", f"{arg} exceeds the saved snapshot.")
        chunked = {
            name: text is not None and (offset > 0 or len(text) > limit)
            for name, (text, offset, limit) in parts.items()
        }
        lengths = {
            name: min(limit, len(text) - offset) for name, (text, offset, limit) in parts.items()
            if text is not None
        }

        def build() -> SavedAdDraft:
            update: dict[str, Any] = {}
            for name, (text, offset, _) in parts.items():
                if chunked[name]:
                    update.update({
                        f"{name}_snapshot": None, f"{name}_snapshot_omitted": True,
                        f"{name}_snapshot_json_chunk": _chunk(text, offset, lengths[name], original.saved_version),
                    })
            return original.model_copy(update=update)

        result = build()
        while text_bytes(result) > MAX_PAGE_CHARS:
            inline = [name for name, (text, _, _) in parts.items() if text is not None and not chunked[name]]
            shrinkable = [name for name in lengths if chunked[name] and lengths[name] > 1]
            if shrinkable:  # shrink existing chunks before chunking a snapshot that fits whole
                widest = max(shrinkable, key=lambda name: lengths[name])
                lengths[widest] = max(1, lengths[widest] // 2)
            elif inline:
                chunked[max(inline, key=lambda name: len(parts[name][0]))] = True
            else:
                raise _too_large()
            result = build()
        return result
