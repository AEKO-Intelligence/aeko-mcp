"""Wire and boundary contracts for the six structured /update-pdp path tools."""

import json
from uuid import uuid4

import anyio
import httpx
import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from aeko_mcp import server
from aeko_mcp.client import CONNECT_ERROR_MESSAGE, AekoAPIError, AekoClient
from aeko_mcp.tools import brand_packages, store_write
from aeko_mcp.tools._structured import AekoToolError, AekoToolInputError

DOMAIN = str(uuid4())
INTEGRATION = str(uuid4())
CLAIM = str(uuid4())
AUDIT = str(uuid4())
PLATFORM_AUDIT = str(uuid4())
PACKAGE_ID = str(uuid4())
DOCUMENT = str(uuid4())
VERSION_ID = str(uuid4())
PACKAGE_DIGEST = "a" * 64
MEMBER_DIGEST = "b" * 64
SKILL_SLUG = f"skill-content-default-{DOCUMENT.replace('-', '')}"
PRODUCT = "1234"
WRITE_PATH = f"/api/store-integrations/{INTEGRATION}/products/{PRODUCT}"
DESCRIPTION_PATH = f"{WRITE_PATH}/description"
FILE_PATH = f"/api/automations/documents/{DOCUMENT}/versions/3/files"
SECRET = "aeko_ot1_do-not-echo"

EXPECTED_OUTPUT_FIELDS = {
    "aeko_get_active_brand_package": {"id", "version", "digest", "members", "total_members", "next_offset"},
    "aeko_get_brand_package_version": {"id", "version", "digest", "members", "total_members", "next_offset"},
    "aeko_read_brand_package_file": {
        "package_id",
        "package_version",
        "package_digest",
        "member",
        "content",
        "next_offset",
        "complete",
    },
    "aeko_get_product_description": {
        "integration_id",
        "external_product_id",
        "platform",
        "description_html",
        "fetched_at",
    },
    "aeko_update_product_page": {
        "store_integration_id",
        "external_product_id",
        "audit_id",
        "status",
        "store_updated",
        "admin_url",
    },
    "aeko_list_store_writes": {"items", "total", "limit", "offset", "next_offset"},
}


class Backend:
    def __init__(self):
        self.routes = {}
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        handler = self.routes[(request.method, request.url.path)]
        return handler(request) if callable(handler) else handler

    def count(self, method, path):
        return sum(1 for r in self.requests if r.method == method and r.url.path == path)


@pytest.fixture
def backend(monkeypatch):
    fake = Backend()
    http = httpx.Client(base_url="https://backend.test", transport=httpx.MockTransport(fake))
    monkeypatch.setattr(server.client, "_client", http)
    yield fake
    http.close()


def list_tools():
    async def run():
        async with create_connected_server_and_client_session(server.mcp._mcp_server) as session:
            return {tool.name: tool for tool in (await session.list_tools()).tools}

    return anyio.run(run)


def call(name, arguments):
    async def run():
        async with create_connected_server_and_client_session(server.mcp._mcp_server) as session:
            return await session.call_tool(name, arguments)

    return anyio.run(run)


def error_payload(error):
    text = error if isinstance(error, str) else str(error)
    return json.loads(text[text.index("{") :])


def package_payload():
    return {
        "id": PACKAGE_ID,
        "active": True,
        "version": 7,
        "digest": PACKAGE_DIGEST,
        "base_package_id": None,
        "base_version": None,
        "members": [
            {
                "document_id": DOCUMENT,
                "version_id": VERSION_ID,
                "version": 3,
                "kind": "skill",
                "subkind": "content",
                "key": "default",
                "package_slug": SKILL_SLUG,
                "digest": MEMBER_DIGEST,
                "origin": "brand",
                "upstream_document_id": None,
            }
        ],
        "counts": {"skill": 1, "eval": 0, "wiki": 0},
        "created_by": "user",
        "note": None,
        "created_at": "2026-09-07T00:00:00Z",
        "activated_at": "2026-09-07T00:01:00Z",
        "pending_decisions": 0,
        "export": {"available": True},
    }


def receipt(**updates):
    value = {
        "audit_id": AUDIT,
        "platform": "cafe24",
        "external_product_id": PRODUCT,
        "status": "success",
        "http_status": 200,
        "payload_sent": {"product": {"description": "<p>new</p>"}},
    }
    value.update(updates)
    return value


def write_args(**updates):
    value = {
        "integration_id": INTEGRATION,
        "external_product_id": PRODUCT,
        "action_item_id": "itm_pdp_1",
        "execution_claim_id": CLAIM,
        "description_html": "<p>new</p>",
        "meta_title": "Title",
        "skip_aeko_shop": True,
    }
    value.update(updates)
    return value


def audit_item(**updates):
    value = {
        "id": str(uuid4()),
        "store_integration_id": INTEGRATION,
        "platform": "shopify",
        "external_product_id": PRODUCT,
        "operation": "description+meta",
        "status": "success",
        "error_code": None,
        "error_message": None,
        "revert_of_audit_id": None,
        "created_at": "2026-09-13T00:00:00Z",
    }
    value.update(updates)
    return value


def test_structured_tools_publish_semantic_output_schemas():
    tools = list_tools()
    for name, fields in EXPECTED_OUTPUT_FIELDS.items():
        schema = tools[name].outputSchema
        assert schema is not None, name
        assert fields <= set(schema["properties"]), name
        assert set(schema["properties"]) != {"result"}, name
    receipt_schema = tools["aeko_update_product_page"].outputSchema
    assert receipt_schema["properties"]["status"]["enum"] == ["success", "dry_run"]
    assert "admin_url" not in receipt_schema["required"]
    history_item = tools["aeko_list_store_writes"].outputSchema["$defs"]["StoreWriteHistoryItem"]
    assert "store_integration_id" in history_item["required"]
    # Unmigrated tools keep FastMCP's text wrapper.
    assert set(tools["aeko_get_brand_wiki_page"].outputSchema["properties"]) == {"result"}
    assert set(tools["aeko_update_product_meta"].outputSchema["properties"]) == {"result"}


def test_package_page_structured_content_matches_text_fallback(backend):
    backend.routes[("GET", "/api/automations/brand-package")] = httpx.Response(200, json=package_payload())
    result = call("aeko_get_active_brand_package", {"domain_id": DOMAIN})

    assert result.isError is False
    structured = result.structuredContent
    assert (structured["id"], structured["version"], structured["digest"]) == (PACKAGE_ID, 7, PACKAGE_DIGEST)
    assert structured["members"][0]["package_slug"] == SKILL_SLUG
    assert structured["next_offset"] is None
    assert json.loads(result.content[0].text) == structured


def test_package_file_chunk_and_pin_error_over_the_wire(backend):
    backend.routes[("GET", "/api/automations/brand-package/versions/7")] = httpx.Response(200, json=package_payload())
    backend.routes[("GET", FILE_PATH)] = httpx.Response(
        200,
        json={
            "document_id": DOCUMENT,
            "version_id": VERSION_ID,
            "version": 3,
            "path": "SKILL.md",
            "content": "브랜드 규칙",
            "size_bytes": 16,
            "editable": True,
            "hosted": True,
            "package_digest": MEMBER_DIGEST,
        },
    )
    arguments = {
        "domain_id": DOMAIN,
        "package_version": 7,
        "package_digest": PACKAGE_DIGEST,
        "package_slug": SKILL_SLUG,
    }
    ok = call("aeko_read_brand_package_file", arguments)
    assert ok.isError is False
    assert ok.structuredContent["content"] == "브랜드 규칙"
    assert ok.structuredContent["package_digest"] == PACKAGE_DIGEST
    assert ok.structuredContent["member"]["version_id"] == VERSION_ID
    assert ok.structuredContent["complete"] is True
    assert json.loads(ok.content[0].text) == ok.structuredContent

    mismatch = call("aeko_read_brand_package_file", {**arguments, "package_digest": "d" * 64})
    assert mismatch.isError is True
    assert mismatch.structuredContent is None
    payload = error_payload(mismatch.content[0].text)
    assert payload["schema"] == "aeko.error.v1"
    assert payload["code"] == "PACKAGE_DIGEST_MISMATCH"
    assert payload["mutation_state"] == "not_attempted"
    assert backend.count("GET", FILE_PATH) == 1


@pytest.mark.parametrize(
    "response, code, status",
    [
        (httpx.Response(404, json={"detail": "Not Found"}), "CAPABILITY_UNAVAILABLE", None),
        (
            httpx.Response(
                404,
                json={"detail": {"code": "BRAND_PACKAGE_NOT_INITIALIZED", "message": f"none {SECRET}"}},
            ),
            "BRAND_PACKAGE_NOT_INITIALIZED",
            404,
        ),
        (httpx.Response(403, json={"detail": f"Run token denied {SECRET}"}), "ACCESS_DENIED", 403),
        (httpx.Response(200, json={"members": "not-a-list"}), "INVALID_BACKEND_RESPONSE", None),
    ],
)
def test_package_backend_errors_keep_stable_codes(backend, response, code, status):
    backend.routes[("GET", "/api/automations/brand-package")] = response
    with pytest.raises(AekoToolError) as caught:
        brand_packages.aeko_get_active_brand_package(DOMAIN)
    payload = error_payload(caught.value)
    assert (payload["code"], payload["http_status"], payload["mutation_state"]) == (code, status, "not_attempted")
    assert SECRET not in str(caught.value)


@pytest.mark.parametrize(
    "html",
    ['<div class="x">한국어 &amp; <!-- AEKO appended -->\n  <img src="a.jpg"></div>\r\n', "", None],
)
def test_description_is_exact_and_null_is_not_invented(backend, html):
    backend.routes[("GET", DESCRIPTION_PATH)] = httpx.Response(
        200,
        json={
            "integration_id": INTEGRATION,
            "external_product_id": PRODUCT,
            "platform": "cafe24",
            "description_html": html,
            "fetched_at": "2026-09-13T00:00:00Z",
        },
    )
    result = call(
        "aeko_get_product_description",
        {"integration_id": INTEGRATION, "external_product_id": PRODUCT},
    )
    assert result.isError is False
    assert result.structuredContent["description_html"] == html
    assert result.structuredContent["integration_id"] == INTEGRATION
    assert result.structuredContent["external_product_id"] == PRODUCT
    assert json.loads(result.content[0].text)["description_html"] == html


@pytest.mark.parametrize(
    "updates, code",
    [
        ({"external_product_id": "9999"}, "PRODUCT_IDENTITY_MISMATCH"),
        ({"integration_id": str(uuid4())}, "PRODUCT_IDENTITY_MISMATCH"),
        ({"description_html": 12}, "INVALID_BACKEND_RESPONSE"),
        ({"description_html": "missing"}, "INVALID_BACKEND_RESPONSE"),
    ],
)
def test_description_rejects_other_products_and_malformed_bodies(backend, updates, code):
    body = {
        "integration_id": INTEGRATION,
        "external_product_id": PRODUCT,
        "platform": "cafe24",
        "description_html": "<p>x</p>",
        "fetched_at": "2026-09-13T00:00:00Z",
        **updates,
    }
    if body["description_html"] == "missing":
        del body["description_html"]
    backend.routes[("GET", DESCRIPTION_PATH)] = httpx.Response(200, json=body)
    with pytest.raises(AekoToolError) as caught:
        store_write.aeko_get_product_description(INTEGRATION, PRODUCT)
    assert error_payload(caught.value)["code"] == code


def test_description_rejects_non_utf8_backend_text_with_bounded_error(backend):
    body = {
        "integration_id": INTEGRATION,
        "external_product_id": PRODUCT,
        "platform": "cafe24",
        "description_html": "\ud800",
        "fetched_at": "2026-09-13T00:00:00Z",
    }
    backend.routes[("GET", DESCRIPTION_PATH)] = httpx.Response(
        200,
        content=json.dumps(body, ensure_ascii=True).encode("ascii"),
        headers={"content-type": "application/json"},
    )

    result = call(
        "aeko_get_product_description",
        {"integration_id": INTEGRATION, "external_product_id": PRODUCT},
    )

    assert result.isError is True
    assert result.structuredContent is None
    assert error_payload(result.content[0].text)["code"] == "INVALID_BACKEND_RESPONSE"


def test_page_write_returns_one_real_receipt(backend):
    backend.routes[("POST", WRITE_PATH)] = httpx.Response(200, json=receipt())
    result = call("aeko_update_product_page", write_args())

    assert result.isError is False
    assert result.structuredContent == {
        "store_integration_id": INTEGRATION,
        "external_product_id": PRODUCT,
        "audit_id": AUDIT,
        "platform": "cafe24",
        "status": "success",
        "store_updated": True,
        "http_status": 200,
        "payload_sent": {"product": {"description": "<p>new</p>"}},
        "payload_sent_omitted": False,
        "admin_url": None,
    }
    assert json.loads(result.content[0].text) == result.structuredContent
    posts = [request for request in backend.requests if request.method == "POST"]
    assert len(posts) == 1
    assert json.loads(posts[0].content) == {
        "skip_aeko_shop": True,
        "description": "<p>new</p>",
        "meta": {"title": "Title"},
        "action_item_id": "itm_pdp_1",
        "execution_claim_id": CLAIM,
    }


def test_dry_run_receipt_is_not_a_live_change(backend):
    backend.routes[("POST", WRITE_PATH)] = httpx.Response(
        200, json=receipt(status="dry_run", http_status=None, payload_sent=None)
    )
    result = store_write.aeko_update_product_page(**write_args())
    assert (result.status, result.store_updated, result.audit_id) == ("dry_run", False, AUDIT)


def test_oversized_payload_snapshot_is_omitted_honestly(backend):
    backend.routes[("POST", WRITE_PATH)] = httpx.Response(
        200, json=receipt(payload_sent={"product": {"description": "x" * (33 * 1024)}})
    )
    result = store_write.aeko_update_product_page(**write_args())
    assert result.payload_sent is None
    assert result.payload_sent_omitted is True


@pytest.mark.parametrize(
    "updates",
    [
        {"status": "success", "http_status": 502},
        {"status": "dry_run", "http_status": 502},
        {"payload_sent": {"description": "\ud800"}},
    ],
)
def test_malformed_success_receipts_are_unknown_and_keep_audit_id(backend, updates):
    backend.routes[("POST", WRITE_PATH)] = httpx.Response(
        200,
        content=json.dumps(receipt(**updates), ensure_ascii=True).encode("ascii"),
        headers={"content-type": "application/json"},
    )

    with pytest.raises(AekoToolError) as caught:
        store_write.aeko_update_product_page(**write_args())

    payload = error_payload(caught.value)
    assert (
        payload["code"],
        payload["mutation_state"],
        payload["audit_id"],
    ) == ("INVALID_WRITE_RECEIPT", "unknown", AUDIT)
    assert backend.count("POST", WRITE_PATH) == 1


def _typed(status, code, audit_id=None):
    detail = {"code": code, "message": f"store said {SECRET} <html>"}
    if audit_id:
        detail["audit_id"] = audit_id
    return httpx.Response(status, json={"detail": detail})


def _raise_read_timeout(request):
    raise httpx.ReadTimeout("timed out", request=request)


def _raise_connect_error(request):
    raise httpx.ConnectError("refused", request=request)


def _raise_remote_protocol_error(request):
    raise httpx.RemoteProtocolError(f"upstream closed {SECRET}", request=request)


WRITE_FAILURES = [
    pytest.param(_typed(409, "ACTION_ITEM_CLAIM_REQUIRED"), "ACTION_ITEM_CLAIM_REQUIRED", "rejected", 409, None, id="claim-required"),
    pytest.param(_typed(409, "ACTION_ITEM_TARGET_MISMATCH"), "ACTION_ITEM_TARGET_MISMATCH", "rejected", 409, None, id="target-mismatch"),
    pytest.param(_typed(403, "TIER_REQUIRED"), "TIER_REQUIRED", "rejected", 403, None, id="tier"),
    pytest.param(_typed(403, "SUBSCRIPTION_INACTIVE"), "SUBSCRIPTION_INACTIVE", "rejected", 403, None, id="subscription"),
    pytest.param(_typed(502, "STORE_SNAPSHOT_FAILED"), "STORE_SNAPSHOT_FAILED", "rejected", 502, None, id="snapshot-before-write"),
    pytest.param(_typed(409, "ACTION_ITEM_WRITE_INDETERMINATE"), "ACTION_ITEM_WRITE_INDETERMINATE", "unknown", 409, None, id="indeterminate"),
    pytest.param(_typed(409, "ACTION_ITEM_WRITE_PAYLOAD_CONFLICT"), "ACTION_ITEM_WRITE_PAYLOAD_CONFLICT", "unknown", 409, None, id="payload-conflict"),
    pytest.param(_typed(422, "VALIDATION_ERROR", PLATFORM_AUDIT), "VALIDATION_ERROR", "rejected", 422, PLATFORM_AUDIT, id="platform-4xx"),
    pytest.param(_typed(429, "RATE_LIMIT", PLATFORM_AUDIT), "RATE_LIMIT", "rejected", 429, PLATFORM_AUDIT, id="platform-rate-limit"),
    pytest.param(_typed(502, "PLATFORM_ERROR", PLATFORM_AUDIT), "PLATFORM_ERROR", "unknown", 502, PLATFORM_AUDIT, id="platform-error"),
    pytest.param(_typed(502, "REAUTH", PLATFORM_AUDIT), "REAUTH", "unknown", 502, PLATFORM_AUDIT, id="platform-translated-502"),
    pytest.param(_typed(404, "NETWORK_ERROR", PLATFORM_AUDIT), "NETWORK_ERROR", "unknown", 404, PLATFORM_AUDIT, id="network-error-any-status"),
    pytest.param(_typed(422, "VALIDATION", "not-a-uuid"), "VALIDATION", "unknown", 422, None, id="malformed-audit-cannot-prove-rejection"),
    pytest.param(httpx.Response(500, json={"detail": f"boom {SECRET}"}), "BACKEND_ERROR", "unknown", 500, None, id="plain-500"),
    pytest.param(httpx.Response(409, json={"detail": "conflict"}), "CONFLICT", "unknown", 409, None, id="plain-409"),
    pytest.param(httpx.Response(422, json={"detail": [{"msg": SECRET}]}), "VALIDATION_FAILED", "rejected", 422, None, id="fastapi-validation"),
    pytest.param(httpx.Response(401, json={"detail": "Not authenticated"}), "AUTHENTICATION_FAILED", "rejected", 401, None, id="auth"),
    pytest.param(httpx.Response(200), "INVALID_WRITE_RECEIPT", "unknown", None, None, id="empty-success"),
    pytest.param(httpx.Response(200, json={}), "INVALID_WRITE_RECEIPT", "unknown", None, None, id="empty-object"),
    pytest.param(httpx.Response(200, content=f"<html>{SECRET}</html>".encode()), "INVALID_WRITE_RECEIPT", "unknown", None, None, id="non-json-success"),
    pytest.param(httpx.Response(200, json=receipt(audit_id=None)), "INVALID_WRITE_RECEIPT", "unknown", None, None, id="missing-audit"),
    pytest.param(httpx.Response(200, json=receipt(status="failed")), "INVALID_WRITE_RECEIPT", "unknown", None, AUDIT, id="failed-status"),
    pytest.param(httpx.Response(200, json=receipt(external_product_id="5678")), "INVALID_WRITE_RECEIPT", "unknown", None, AUDIT, id="other-product"),
    pytest.param(httpx.Response(200, json=receipt(http_status="200")), "INVALID_WRITE_RECEIPT", "unknown", None, AUDIT, id="malformed-http-status"),
    pytest.param(_raise_read_timeout, "WRITE_RESULT_UNKNOWN", "unknown", None, None, id="read-timeout"),
    pytest.param(_raise_connect_error, "BACKEND_UNREACHABLE", "not_attempted", None, None, id="connect-error"),
    pytest.param(_raise_remote_protocol_error, "WRITE_RESULT_UNKNOWN", "unknown", None, None, id="remote-protocol-error"),
]


@pytest.mark.parametrize("response, code, state, status, audit_id", WRITE_FAILURES)
def test_page_write_failures_report_truthful_mutation_state(backend, response, code, state, status, audit_id):
    backend.routes[("POST", WRITE_PATH)] = response
    with pytest.raises(AekoToolError) as caught:
        store_write.aeko_update_product_page(**write_args())

    payload = error_payload(caught.value)
    assert payload["schema"] == "aeko.error.v1"
    assert (payload["code"], payload["mutation_state"], payload["http_status"], payload["audit_id"]) == (
        code,
        state,
        status,
        audit_id,
    )
    assert backend.count("POST", WRITE_PATH) == 1
    text = str(caught.value)
    assert SECRET not in text
    assert "<html>" not in text
    assert len(text.encode("utf-8")) <= 1024


def test_page_write_error_is_an_mcp_error_without_structured_content(backend):
    backend.routes[("POST", WRITE_PATH)] = _typed(409, "ACTION_ITEM_WRITE_INDETERMINATE")
    result = call("aeko_update_product_page", write_args())

    assert result.isError is True
    assert result.structuredContent is None
    payload = error_payload(result.content[0].text)
    assert payload["code"] == "ACTION_ITEM_WRITE_INDETERMINATE"
    assert payload["mutation_state"] == "unknown"
    assert payload["http_status"] == 409
    assert SECRET not in result.content[0].text
    assert backend.count("POST", WRITE_PATH) == 1


@pytest.mark.parametrize(
    "updates",
    [
        {"description_html": None, "meta_title": None},
        {"integration_id": "store-1"},
        {"execution_claim_id": "claim-1"},
        {"external_product_id": "gid://shopify/Product/1"},
        {"external_product_id": "\ud800"},
        {"description_html": "\ud800"},
        {"json_ld": {"score": float("nan")}},
        {"action_item_id": ""},
        {"description_html": '<img src="./local.png">', "skip_aeko_shop": False},
    ],
)
def test_invalid_write_input_is_not_attempted_and_sends_nothing(backend, updates):
    with pytest.raises(AekoToolInputError) as caught:
        store_write.aeko_update_product_page(**write_args(**updates))
    assert isinstance(caught.value, ValueError)
    payload = error_payload(caught.value)
    assert (payload["code"], payload["mutation_state"]) == ("INVALID_ARGUMENT", "not_attempted")
    assert backend.requests == []


def test_invalid_write_input_is_an_mcp_error_over_the_wire(backend):
    result = call("aeko_update_product_page", write_args(integration_id="store-1"))
    assert result.isError is True
    assert error_payload(result.content[0].text)["mutation_state"] == "not_attempted"
    assert backend.requests == []


def test_image_upload_failure_never_submits_the_store_write(backend, tmp_path):
    image = tmp_path / "local.png"
    image.write_bytes(b"png")
    backend.routes[("POST", "/api/aeko-shop/media/presign")] = httpx.Response(500, json={"detail": SECRET})
    with pytest.raises(AekoToolError) as caught:
        store_write.aeko_update_product_page(
            **write_args(
                description_html=f'<img src="file://{image}">',
                skip_aeko_shop=False,
                domain_id=DOMAIN,
            )
        )
    payload = error_payload(caught.value)
    assert (payload["code"], payload["mutation_state"], payload["http_status"]) == (
        "IMAGE_UPLOAD_FAILED",
        "not_attempted",
        500,
    )
    assert backend.count("POST", WRITE_PATH) == 0
    assert SECRET not in str(caught.value)


def test_history_preserves_integration_identity_and_pagination(backend):
    rows = [
        audit_item(id=AUDIT),
        audit_item(status="failed", error_code="PLATFORM_ERROR", error_message="store failed"),
        audit_item(revert_of_audit_id=AUDIT),
    ]

    def respond(request):
        offset = int(request.url.params["offset"])
        limit = int(request.url.params["limit"])
        return httpx.Response(200, json={"items": rows[offset : offset + limit], "total": len(rows)})

    backend.routes[("GET", "/api/store-write-audit")] = respond
    first = call("aeko_list_store_writes", {"limit": 2, "offset": 0})
    assert first.isError is False
    page = first.structuredContent
    assert [item["id"] for item in page["items"]] == [AUDIT, rows[1]["id"]]
    assert all(item["store_integration_id"] == INTEGRATION for item in page["items"])
    assert (page["total"], page["limit"], page["offset"], page["next_offset"]) == (3, 2, 0, 2)
    assert json.loads(first.content[0].text) == page

    last = store_write.aeko_list_store_writes(limit=2, offset=2)
    assert last.items[0].revert_of_audit_id == AUDIT
    assert last.next_offset is None
    assert dict(backend.requests[-1].url.params) == {"limit": "2", "offset": "2"}


def test_history_replaces_raw_platform_error_message_with_authored_text(backend):
    raw_error = f"Cafe24 returned 422: <html>{SECRET}</html> https://store.test/private"
    backend.routes[("GET", "/api/store-write-audit")] = httpx.Response(
        200,
        json={
            "items": [
                audit_item(
                    status="failed",
                    error_code="VALIDATION",
                    error_message=raw_error,
                )
            ],
            "total": 1,
        },
    )

    result = call("aeko_list_store_writes", {})

    assert result.isError is False
    item = result.structuredContent["items"][0]
    assert item["error_code"] == "VALIDATION"
    assert item["error_message"] == "The connected store rejected the product update as invalid."
    assert SECRET not in result.content[0].text
    assert raw_error not in result.content[0].text


def test_history_allows_an_empty_page_past_the_reported_total(backend):
    backend.routes[("GET", "/api/store-write-audit")] = httpx.Response(
        200, json={"items": [], "total": 3}
    )

    page = store_write.aeko_list_store_writes(limit=20, offset=100)

    assert page.items == []
    assert (page.total, page.offset, page.next_offset) == (3, 100, None)


@pytest.mark.parametrize(
    "body",
    [
        {"items": [audit_item(store_integration_id=None)], "total": 1},
        {"items": [], "total": "1"},
        {"items": [audit_item(), audit_item(), audit_item()], "total": 3},
        {"items": [], "total": 10},
        {"items": [audit_item(error_code="secret-token")], "total": 1},
    ],
)
def test_history_rejects_malformed_pages(backend, body):
    backend.routes[("GET", "/api/store-write-audit")] = httpx.Response(200, json=body)
    with pytest.raises(AekoToolError) as caught:
        store_write.aeko_list_store_writes(limit=2)
    payload = error_payload(caught.value)
    assert (payload["code"], payload["mutation_state"]) == ("INVALID_BACKEND_RESPONSE", "not_attempted")


def _client(respond):
    client = AekoClient()
    client.close()
    client._client = httpx.Client(base_url="https://backend.test", transport=httpx.MockTransport(respond))
    return client


def test_client_error_keeps_legacy_message_and_retains_details():
    client = _client(
        lambda request: httpx.Response(
            502, json={"detail": {"code": "PLATFORM_ERROR", "message": "store failed", "audit_id": AUDIT}}
        )
    )
    try:
        with pytest.raises(RuntimeError) as caught:
            client.post("/x", json={})
    finally:
        client.close()
    error = caught.value
    assert isinstance(error, AekoAPIError)
    assert str(error) == "Upstream service failed (HTTP 502). — [PLATFORM_ERROR] store failed"
    assert (error.http_status, error.code, error.audit_id, error.request_sent) == (502, "PLATFORM_ERROR", AUDIT, True)


def test_connect_failure_keeps_legacy_message_and_marks_request_unsent():
    client = _client(_raise_connect_error)
    try:
        with pytest.raises(RuntimeError) as caught:
            client.get("/x")
    finally:
        client.close()
    assert str(caught.value) == CONNECT_ERROR_MESSAGE
    assert caught.value.request_sent is False
    assert caught.value.http_status is None


def test_unmigrated_store_tools_keep_legacy_error_text(monkeypatch):
    def fail(*args, **kwargs):
        raise AekoAPIError(
            "API error 409 (conflict). — [ACTION_ITEM_CLAIM_REQUIRED] claim first",
            http_status=409,
            code="ACTION_ITEM_CLAIM_REQUIRED",
        )

    monkeypatch.setattr(store_write.client, "post", fail)
    output = store_write.aeko_update_product_meta("store-1", "7", title="SEO")
    assert output == (
        "# Write failed\n\n```\n"
        "RuntimeError: API error 409 (conflict). — [ACTION_ITEM_CLAIM_REQUIRED] claim first\n```"
    )


def test_unmigrated_wiki_tools_keep_legacy_error_text(backend):
    backend.routes[("GET", "/api/automations/wiki/pages")] = httpx.Response(404, json={"detail": "Not Found"})
    with pytest.raises(RuntimeError) as caught:
        brand_packages.aeko_list_brand_wiki_pages(DOMAIN)
    assert str(caught.value) == (
        "This AEKO backend does not provide the Brand Wiki read API yet. "
        "Update the deployed backend before using this tool."
    )
    assert not isinstance(caught.value, AekoToolError)
