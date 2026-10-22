import json
from uuid import uuid4

import pytest

from aeko_mcp.client import AekoAPIError
from aeko_mcp.server import mcp
from aeko_mcp.tools import saved_ad_drafts as tools
from aeko_mcp.tools._structured import AekoToolError, AekoToolInputError

DOMAIN = str(uuid4())
CREATIVE = str(uuid4())


def draft(**updates):
    """A row shaped like the backend's MarketingAdCreativeResponse."""
    row = {
        "id": CREATIVE, "domain_id": DOMAIN, "ad_account_id": None,
        "title": "Edited headline", "body": "Latest saved copy for this product",
        "image_url": None, "target_language": "en", "status": "saved", "placed_ad_id": None,
        "created_at": "2026-10-20T01:02:03Z", "saved_version": "a" * 64, "origin": "review",
        "store_product_id": str(uuid4()), "product_title": "Moisture Cream",
        "source_review_id": str(uuid4()), "source_context_id": None, "placement_input": None,
        "source_snapshot": {"origin": "review", "query": "why?"},
        "ad_copy_format_snapshot": {"name": "Short", "accepted_brand_constraints": ["no hype"]},
    }
    row.update(updates)
    return row


def serve(monkeypatch, rows, calls=None):
    """Backend stub: list returns every row, detail returns the row matching the path."""
    def get(path, params):
        if calls is not None:
            calls.append((path, params))
        if path.endswith("/saved"):
            start = params["offset"]
            return {"items": rows[start:start + params["limit"]], "total": len(rows),
                    "limit": params["limit"], "offset": start}
        return next(row for row in rows if path.endswith(row["id"]))
    monkeypatch.setattr(tools.client, "get", get)


def read_all(monkeypatch_unused=None, field="source", **kwargs):
    texts, offset = [], 0
    while True:
        result = tools.aeko_get_saved_ad_draft(
            DOMAIN, CREATIVE, **{f"{'source' if field == 'source' else 'format'}_offset": offset}, **kwargs)
        chunk = getattr(result, f"{'source' if field == 'source' else 'ad_copy_format'}_snapshot_json_chunk")
        texts.append(chunk["text"])
        if chunk["next_offset"] is None:
            return "".join(texts)
        offset = chunk["next_offset"]


def code(exc):
    return json.loads(str(exc.value))["code"]


def test_registered_as_read_only():
    registered = {tool.name: tool for tool in mcp._tool_manager.list_tools()}
    for name in ("aeko_list_saved_ad_drafts", "aeko_get_saved_ad_draft"):
        assert registered[name].annotations.readOnlyHint is True
        assert registered[name].annotations.idempotentHint is True


def test_list_requests_one_backend_page_and_preserves_copy(monkeypatch):
    calls = []
    def get(path, params):
        calls.append((path, params))
        return {"items": [draft()], "total": 3, "limit": 2, "offset": 1}
    monkeypatch.setattr(tools.client, "get", get)
    result = tools.aeko_list_saved_ad_drafts(DOMAIN, limit=2, offset=1)
    assert calls == [("/api/marketing/ad-creatives/saved", {"domain_id": DOMAIN, "limit": 2, "offset": 1})]
    assert result.items[0].model_dump()["product_title"] == "Moisture Cream"
    assert result.items[0].title == "Edited headline"
    assert result.items[0].source_snapshot["query"] == "why?"
    assert result.total == 3 and result.next_offset == 2 and result.has_more


def test_get_reads_current_saved_row(monkeypatch):
    calls = []
    def get(path, params):
        calls.append((path, params))
        return draft(body="After manual edit")
    monkeypatch.setattr(tools.client, "get", get)
    result = tools.aeko_get_saved_ad_draft(DOMAIN, CREATIVE)
    assert result.body == "After manual edit"
    assert result.saved_version == "a" * 64
    assert calls == [(f"/api/marketing/ad-creatives/saved/{CREATIVE}", {"domain_id": DOMAIN})]


@pytest.mark.parametrize("kwargs", [
    {"domain_id": "wrong"}, {"domain_id": DOMAIN, "limit": 0},
    {"domain_id": DOMAIN, "limit": 101}, {"domain_id": DOMAIN, "limit": True},
    {"domain_id": DOMAIN, "offset": -1}, {"domain_id": DOMAIN, "offset": 1.5},
])
def test_list_rejects_invalid_input_before_request(monkeypatch, kwargs):
    monkeypatch.setattr(tools.client, "get", lambda *a, **k: pytest.fail("backend called"))
    with pytest.raises(AekoToolInputError) as exc:
        tools.aeko_list_saved_ad_drafts(**kwargs)
    assert code(exc) == "INVALID_ARGUMENT"


def test_get_rejects_invalid_id_before_request(monkeypatch):
    monkeypatch.setattr(tools.client, "get", lambda *a, **k: pytest.fail("backend called"))
    with pytest.raises(AekoToolInputError):
        tools.aeko_get_saved_ad_draft(DOMAIN, "../x")


def test_oversize_page_keeps_whole_copy_and_reports_next_offset(monkeypatch):
    rows = [draft(id=str(uuid4()), body=f"{i}:" + "x" * 12000) for i in range(3)]
    monkeypatch.setattr(tools.client, "get", lambda *a, **k: {
        "items": rows, "total": 8, "limit": 3, "offset": 2,
    })
    result = tools.aeko_list_saved_ad_drafts(DOMAIN, limit=3, offset=2)
    assert result.returned_count == 1
    assert result.items[0].body == rows[0]["body"]
    assert result.next_offset == 3 and result.output_limited and result.has_more


def test_backend_failure_is_bounded_and_not_a_success(monkeypatch):
    def fail(*args, **kwargs):
        raise AekoAPIError("private backend details", http_status=403, code="ACCESS_DENIED")
    monkeypatch.setattr(tools.client, "get", fail)
    with pytest.raises(AekoToolError) as exc:
        tools.aeko_get_saved_ad_draft(DOMAIN, CREATIVE)
    assert code(exc) == "ACCESS_DENIED"
    assert "private backend details" not in str(exc.value)


def test_large_korean_snapshot_is_omitted_from_list_and_chunked_in_detail(monkeypatch):
    snapshot = {"evidence": "리뷰 근거" * 12000}
    row = draft(source_snapshot=snapshot)
    def get(path, params):
        if path.endswith("/saved"):
            return {"items": [row], "total": 1, "limit": 50, "offset": 0}
        return row
    monkeypatch.setattr(tools.client, "get", get)
    listing = tools.aeko_list_saved_ad_drafts(DOMAIN)
    assert listing.items[0].source_snapshot is None
    assert listing.items[0].source_snapshot_omitted is True
    assert listing.items[0].title == row["title"] and listing.items[0].body == row["body"]
    chunks = []
    offset = 0
    while True:
        result = tools.aeko_get_saved_ad_draft(DOMAIN, CREATIVE, source_offset=offset)
        chunk = result.source_snapshot_json_chunk
        assert result.source_snapshot_omitted and result.source_snapshot is None
        assert result.saved_version == chunk["saved_version"] == row["saved_version"]
        assert result.body == row["body"]
        chunks.append(chunk["text"])
        if chunk["next_offset"] is None:
            break
        offset = chunk["next_offset"]
    assert json.loads("".join(chunks)) == snapshot


def test_invalid_source_offset_and_domain_mismatch(monkeypatch):
    monkeypatch.setattr(tools.client, "get", lambda *a, **k: pytest.fail("backend called"))
    with pytest.raises(AekoToolInputError):
        tools.aeko_get_saved_ad_draft(DOMAIN, CREATIVE, source_offset=-1)
    with pytest.raises(AekoToolInputError):
        tools.aeko_get_saved_ad_draft(DOMAIN, CREATIVE, source_limit=8001)
    monkeypatch.setattr(tools.client, "get", lambda *a, **k: draft(domain_id=str(uuid4())))
    with pytest.raises(AekoToolError) as exc:
        tools.aeko_get_saved_ad_draft(DOMAIN, CREATIVE)
    assert code(exc) == "INVALID_BACKEND_RESPONSE"


def test_inconsistent_total_is_rejected(monkeypatch):
    monkeypatch.setattr(tools.client, "get", lambda *a, **k: {
        "items": [draft()], "total": 0, "limit": 50, "offset": 0,
    })
    with pytest.raises(AekoToolError) as exc:
        tools.aeko_list_saved_ad_drafts(DOMAIN)
    assert code(exc) == "INVALID_BACKEND_RESPONSE"


def test_empty_page_beyond_end_is_valid(monkeypatch):
    monkeypatch.setattr(tools.client, "get", lambda *a, **k: {
        "items": [], "total": 2, "limit": 10, "offset": 10,
    })
    result = tools.aeko_list_saved_ad_drafts(DOMAIN, limit=10, offset=10)
    assert result.items == []
    assert result.total == 2 and result.returned_count == 0
    assert result.has_more is False and result.next_offset is None


def test_large_nonsnapshot_field_fails_without_copy_truncation(monkeypatch):
    row = draft(source_snapshot=None, ad_copy_format_snapshot=None, extra_metadata="x" * 30000)
    def get(path, params):
        if path.endswith("/saved"):
            return {"items": [row], "total": 1, "limit": 50, "offset": 0}
        return row
    monkeypatch.setattr(tools.client, "get", get)
    with pytest.raises(AekoToolError) as listing:
        tools.aeko_list_saved_ad_drafts(DOMAIN)
    assert code(listing) == "OUTPUT_TOO_LARGE"
    with pytest.raises(AekoToolError) as detail:
        tools.aeko_get_saved_ad_draft(DOMAIN, CREATIVE)
    assert code(detail) == "OUTPUT_TOO_LARGE"


BIG_RULES = {"name": "Brand", "accepted_brand_constraints": ["규칙 " + "가나다라마바사" * 3000 + str(i) for i in range(2)]}


def test_list_omits_large_format_snapshot_and_paging_continues(monkeypatch):
    big = draft(id=str(uuid4()), ad_copy_format_snapshot=BIG_RULES)
    rows = [draft(id=str(uuid4())), big, draft(id=str(uuid4()))]
    serve(monkeypatch, rows)
    result = tools.aeko_list_saved_ad_drafts(DOMAIN, limit=3)
    flagged = result.items[1]
    assert flagged.ad_copy_format_snapshot is None and flagged.ad_copy_format_snapshot_omitted
    assert flagged.title == big["title"] and flagged.body == big["body"]
    assert result.items[0].ad_copy_format_snapshot_omitted is False
    assert result.returned_count == 3 and not result.has_more
    page = tools.aeko_list_saved_ad_drafts(DOMAIN, limit=1, offset=1)
    assert page.returned_count == 1 and page.items[0].ad_copy_format_snapshot_omitted


def test_get_chunks_large_format_snapshot_exactly(monkeypatch):
    serve(monkeypatch, [draft(ad_copy_format_snapshot=BIG_RULES)])
    first = tools.aeko_get_saved_ad_draft(DOMAIN, CREATIVE)
    assert first.ad_copy_format_snapshot is None and first.ad_copy_format_snapshot_omitted
    assert first.source_snapshot == {"origin": "review", "query": "why?"}
    assert json.loads(read_all(field="format")) == BIG_RULES


def test_get_with_both_snapshots_large_fits_page(monkeypatch):
    source = {"evidence": "리뷰 근거" * 6000}
    serve(monkeypatch, [draft(source_snapshot=source, ad_copy_format_snapshot=BIG_RULES)])
    result = tools.aeko_get_saved_ad_draft(DOMAIN, CREATIVE)
    assert tools.text_bytes(result) <= tools.MAX_PAGE_CHARS
    assert result.source_snapshot_json_chunk and result.ad_copy_format_snapshot_json_chunk
    assert json.loads(read_all(field="source")) == source
    assert json.loads(read_all(field="format")) == BIG_RULES


def test_saved_version_match_mismatch_and_format(monkeypatch):
    serve(monkeypatch, [draft()])
    assert tools.aeko_get_saved_ad_draft(DOMAIN, CREATIVE, saved_version="a" * 64).id == CREATIVE
    with pytest.raises(AekoToolError) as exc:
        tools.aeko_get_saved_ad_draft(DOMAIN, CREATIVE, saved_version="b" * 64)
    assert code(exc) == "SAVED_AD_CHANGED" and "a" * 64 in str(exc.value)
    monkeypatch.setattr(tools.client, "get", lambda *a, **k: pytest.fail("backend called"))
    for bad in ("A" * 64, "a" * 63, "xyz", 5):
        with pytest.raises(AekoToolInputError) as exc:
            tools.aeko_get_saved_ad_draft(DOMAIN, CREATIVE, saved_version=bad)
        assert code(exc) == "INVALID_ARGUMENT"


def test_row_missing_domain_id_is_invalid_backend_response(monkeypatch):
    row = draft()
    del row["domain_id"]
    serve(monkeypatch, [row])
    for call in (lambda: tools.aeko_list_saved_ad_drafts(DOMAIN), lambda: tools.aeko_get_saved_ad_draft(DOMAIN, CREATIVE)):
        with pytest.raises(AekoToolError) as exc:
            call()
        assert code(exc) == "INVALID_BACKEND_RESPONSE"


@pytest.mark.parametrize("detail,status,expected", [
    ("Saved ad not found", 404, "SAVED_AD_NOT_FOUND"),
    ("Saved ad source unavailable", 404, "SAVED_AD_SOURCE_UNAVAILABLE"),
])
def test_not_found_variants_are_distinguishable(monkeypatch, detail, status, expected):
    def fail(*args, **kwargs):
        raise AekoAPIError(detail, http_status=status)
    monkeypatch.setattr(tools.client, "get", fail)
    with pytest.raises(AekoToolError) as exc:
        tools.aeko_get_saved_ad_draft(DOMAIN, CREATIVE)
    assert code(exc) == expected


@pytest.mark.parametrize("backend_code,status", [("AD_SOURCE_UNAVAILABLE", 400), ("FEATURE_LOCKED", 403)])
def test_backend_codes_have_authored_messages(monkeypatch, backend_code, status):
    def fail(*args, **kwargs):
        raise AekoAPIError("raw backend text", http_status=status, code=backend_code)
    monkeypatch.setattr(tools.client, "get", fail)
    with pytest.raises(AekoToolError) as exc:
        tools.aeko_get_saved_ad_draft(DOMAIN, CREATIVE)
    assert code(exc) == backend_code and "raw backend text" not in str(exc.value)


def test_medium_inline_rules_do_not_shrink_source_reads_to_tiny_chunks(monkeypatch):
    # 6,000 Korean characters of rules fit format_limit, so they start inline; resending
    # them whole on every call used to squeeze the source chunk to ~500 characters.
    rules = {"name": "브랜드 규칙", "accepted_brand_constraints": ["과장 금지 " * 1000]}
    source = {"evidence": "리뷰 근거 문장" * 5000}
    calls = []
    serve(monkeypatch, [draft(source_snapshot=source, ad_copy_format_snapshot=rules)], calls)
    assert json.loads(read_all(field="source")) == source
    source_chars = len(json.dumps(source, ensure_ascii=False, separators=(",", ":")))
    assert len(calls) <= source_chars // 2000 + 1
