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
    row = {
        "id": CREATIVE, "title": "Edited headline", "body": "Latest saved copy",
        "saved_version": "a" * 64, "source_snapshot": {"origin": "review", "query": "why?"},
        "store_product_id": str(uuid4()), "market": "US", "language": "en",
    }
    row.update(updates)
    return row


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
    assert result.items[0].model_dump()["market"] == "US"
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
    row = draft(domain_id=DOMAIN, source_snapshot=snapshot)
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
    row = draft(source_snapshot=None, extra_metadata="x" * 30000)
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
