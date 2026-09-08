import json
from copy import deepcopy
from uuid import uuid4

import httpx
import pytest

from aeko_mcp.client import AekoClient
from aeko_mcp.server import mcp
from aeko_mcp.tools import automation_documents as tools

DOMAIN, DOCUMENT, VERSION = str(uuid4()), str(uuid4()), str(uuid4())


def package():
    return {
        "id": VERSION, "version": 3, "skill_md": "---\nname: example\n---\n브랜드 지침 😊\n",
        "package_digest": "a" * 64, "metadata": {"private_unused": "unused metadata"},
        "text": "raw body", "created_by": "brand", "promoted_at": "2026-09-07T00:00:00Z",
        "hosted_support_files": False,
        "support_files": [{"path": "references/rules.md", "content": "brand-only rule",
                           "size_bytes": 15, "editable": True, "hosted": False}],
    }


def file_response(data):
    def get(url, params):
        assert url == f"/api/automations/documents/{DOCUMENT}/versions/3/files"
        assert params["domain_id"] == DOMAIN
        path = params["path"]
        if path == "SKILL.md":
            content, hosted = data["skill_md"], True
        else:
            files = [file for file in data["support_files"] if file["path"] == path]
            if not files:
                raise RuntimeError("Supporting file not found")
            content, hosted = files[0]["content"], False
        return {"document_id": DOCUMENT, "version_id": data["id"], "version": data["version"],
                "path": path, "content": content, "hosted": hosted,
                "package_digest": data["package_digest"], "size_bytes": len(content.encode("utf-8"))}
    return get


def test_document_tools_are_registered_read_only():
    registered = {tool.name: tool for tool in mcp._tool_manager.list_tools()}
    for name in ("aeko_list_brand_documents", "aeko_get_document_package", "aeko_read_document_file"):
        assert registered[name].annotations.readOnlyHint is True
        assert registered[name].annotations.idempotentHint is True


def test_discovery_keeps_brand_identity_and_pages_without_bodies(monkeypatch):
    calls = []
    rows = [
        {"id": "b", "kind": "skill", "owner": "brand", "parent_document_id": "a", "active_version": 3,
         "draft_version": 4, "text": "must not emit", "versions": [package()]},
        {"id": "a", "kind": "skill", "owner": "aeko", "active_version": 1},
    ]
    def get(path, params):
        calls.append((path, params))
        return {"documents": rows}
    monkeypatch.setattr(tools.client, "get", get)
    first = json.loads(tools.aeko_list_brand_documents(DOMAIN, "skill", limit=1))
    second_text = tools.aeko_list_brand_documents(DOMAIN, "skill", offset=first["next_offset"], limit=1)
    second = json.loads(second_text)
    assert first["documents"][0]["owner"] == "aeko"
    assert second["documents"][0]["owner"] == "brand"
    assert second["documents"][0]["parent_document_id"] == "a"
    assert second["documents"][0]["active_version"] == 3
    assert second["documents"][0]["draft_version"] == 4
    assert second["next_offset"] is None
    assert "must not emit" not in second_text and "skill_md" not in second_text
    assert calls == [("/api/automations/documents", {"domain_id": DOMAIN, "kind": "skill"})] * 2


def test_manifest_fetches_one_version_without_emitting_content(monkeypatch):
    calls = []
    def get(path, params):
        calls.append((path, params))
        return package()
    monkeypatch.setattr(tools.client, "get", get)
    text = tools.aeko_get_document_package(DOMAIN, DOCUMENT, 3)
    data = json.loads(text)
    assert calls == [(f"/api/automations/documents/{DOCUMENT}/versions/3", {"domain_id": DOMAIN})]
    assert data["version_id"] == VERSION
    assert data["package_digest"] == "a" * 64
    assert [file["path"] for file in data["files"]] == ["SKILL.md", "references/rules.md"]
    assert data["files"][1]["hosted"] is False
    assert "brand-only rule" not in text and "unused metadata" not in text and "브랜드" not in text


def test_discovery_byte_pages_large_unicode_metadata_without_losing_rows(monkeypatch):
    rows = [{"id": f"{index:03}", "name": "브랜드" * 30,
             "declared_inputs": ["제품" * 30] * 20} for index in range(40)]
    monkeypatch.setattr(tools.client, "get", lambda *a, **kw: {"documents": rows})
    offset, seen = 0, []
    while True:
        output = tools.aeko_list_brand_documents(DOMAIN, offset=offset, limit=100)
        assert len(output.encode("utf-8")) <= tools.METADATA_PAGE_BYTES
        data = json.loads(output)
        seen.extend(row["id"] for row in data["documents"])
        assert data["total"] == len(rows)
        if data["next_offset"] is None:
            break
        assert data["next_offset"] > offset
        offset = data["next_offset"]
    assert seen == [row["id"] for row in rows]


def test_oversized_backend_metadata_never_reaches_model(monkeypatch):
    monkeypatch.setattr(tools.client, "get", lambda *a, **kw: {
        "documents": [{"id": DOCUMENT, "name": "x" * tools.METADATA_PAGE_BYTES}],
    })
    with pytest.raises(RuntimeError, match="metadata exceeding"):
        tools.aeko_list_brand_documents(DOMAIN)
    data = package()
    data["support_files"] = [{"path": "x" * tools.METADATA_PAGE_BYTES,
                              "size_bytes": 1, "editable": True, "hosted": False}]
    monkeypatch.setattr(tools.client, "get", lambda *a, **kw: data)
    with pytest.raises(RuntimeError, match="manifest exceeding"):
        tools.aeko_get_document_package(DOMAIN, DOCUMENT, 3)


def test_utf8_chunks_round_trip_without_loss_or_version_drift(monkeypatch):
    data = package()
    expected = "가을 컬렉션 😊.\n" * 100
    data["skill_md"] = expected
    monkeypatch.setattr(tools.client, "get", file_response(deepcopy(data)))
    offset = 0
    chunks = []
    while True:
        chunk = json.loads(tools.aeko_read_document_file(DOMAIN, DOCUMENT, 3, offset=offset, max_bytes=256))
        assert chunk["version_id"] == VERSION and chunk["package_digest"] == "a" * 64
        assert len(chunk["content"].encode("utf-8")) <= 256
        assert chunk["offset"] == offset
        chunks.append(chunk["content"])
        if chunk["complete"]:
            assert chunk["next_offset"] is None
            break
        assert chunk["next_offset"] > offset
        offset = chunk["next_offset"]
    assert "".join(chunks) == expected


def test_file_read_preserves_export_only_scope_and_requires_exact_path(monkeypatch):
    monkeypatch.setattr(tools.client, "get", file_response(package()))
    result = json.loads(tools.aeko_read_document_file(DOMAIN, DOCUMENT, 3, "references/rules.md"))
    assert result["content"] == "brand-only rule"
    assert result["hosted"] is False
    for path in ("../rules.md", "/etc/passwd"):
        with pytest.raises(ValueError, match="exact relative path"):
            tools.aeko_read_document_file(DOMAIN, DOCUMENT, 3, path)
    for path in ("references/missing.md", "skill.md"):
        with pytest.raises(RuntimeError, match="Supporting file not found"):
            tools.aeko_read_document_file(DOMAIN, DOCUMENT, 3, path)


def test_invalid_utf8_offset_is_not_silently_rounded(monkeypatch):
    data = package()
    data["skill_md"] = "한글"
    monkeypatch.setattr(tools.client, "get", file_response(data))
    for offset in (1, 2, 4, 99):
        with pytest.raises(ValueError, match="UTF-8 boundary"):
            tools.aeko_read_document_file(DOMAIN, DOCUMENT, 3, offset=offset)


@pytest.mark.parametrize("token", ["aeko_ot1_test", "aeko_rt1_test"])
def test_request_credential_is_forwarded_but_never_returned(monkeypatch, token):
    seen = []
    def respond(request):
        seen.append(request)
        return httpx.Response(200, json=package())
    client = AekoClient()
    client.close()
    client._client = httpx.Client(base_url="https://backend.test", transport=httpx.MockTransport(respond))
    monkeypatch.setattr(tools, "client", client)
    context = client.set_request_auth_token(token)
    try:
        output = tools.aeko_get_document_package(DOMAIN, DOCUMENT, 3)
    finally:
        client.reset_request_auth_token(context)
        client.close()
    assert seen[0].headers["Authorization"] == f"Bearer {token}"
    assert seen[0].url.params["domain_id"] == DOMAIN
    assert token not in output
    assert client._headers() == {}


def test_authorization_failure_has_no_fallback_or_retry(monkeypatch):
    calls = []
    def denied(path, params):
        calls.append(path)
        raise RuntimeError("Access denied")
    monkeypatch.setattr(tools.client, "get", denied)
    with pytest.raises(RuntimeError, match="Access denied"):
        tools.aeko_get_document_package(DOMAIN, DOCUMENT, 3)
    assert calls == [f"/api/automations/documents/{DOCUMENT}/versions/3"]


def test_inputs_cannot_redirect_requests_or_expand_chunk_budget(monkeypatch):
    def unexpected(*args, **kwargs):
        pytest.fail("Invalid input must fail before a backend request")
    monkeypatch.setattr(tools.client, "get", unexpected)
    for document_id in ("../account", "https://elsewhere.test", "bad-id"):
        with pytest.raises(ValueError):
            tools.aeko_get_document_package(DOMAIN, document_id, 3)
    for version in (0, -1, True, 2**31):
        with pytest.raises(ValueError):
            tools.aeko_get_document_package(DOMAIN, DOCUMENT, version)
    for maximum in (0, 255, 16385, True):
        with pytest.raises(ValueError):
            tools.aeko_read_document_file(DOMAIN, DOCUMENT, 3, max_bytes=maximum)


def test_wrong_version_response_is_rejected(monkeypatch):
    data = package()
    data["version"] = 4
    monkeypatch.setattr(tools.client, "get", file_response(data))
    with pytest.raises(RuntimeError, match="unexpected document version"):
        tools.aeko_read_document_file(DOMAIN, DOCUMENT, 3)
