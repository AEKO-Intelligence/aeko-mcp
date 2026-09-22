import json
from copy import deepcopy
from uuid import uuid4

import httpx
import pydantic_core
import pytest

from aeko_mcp.client import AekoClient
from aeko_mcp.server import mcp
from aeko_mcp.tools import brand_packages as tools
from aeko_mcp.tools._structured import AekoToolError, AekoToolInputError, text_bytes

DOMAIN = str(uuid4())
PACKAGE_ID = str(uuid4())
DOCUMENT = str(uuid4())
VERSION_ID = str(uuid4())
WIKI_DOCUMENT = str(uuid4())
WIKI_VERSION_ID = str(uuid4())
PACKAGE_DIGEST = "a" * 64
MEMBER_DIGEST = "b" * 64
WIKI_DIGEST = "c" * 64
SKILL_SLUG = f"skill-content-default-{DOCUMENT.replace('-', '')}"
WIKI_SLUG = f"wiki-voice-brand-voice-{WIKI_DOCUMENT.replace('-', '')}"


def member(**updates):
    value = {
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
    value.update(updates)
    return value


def package(members=None, **updates):
    members = [member()] if members is None else members
    value = {
        "id": PACKAGE_ID,
        "active": True,
        "version": 7,
        "digest": PACKAGE_DIGEST,
        "base_package_id": None,
        "base_version": None,
        "members": members,
        "counts": {
            kind: sum(row["kind"] == kind for row in members)
            for kind in ("skill", "eval", "wiki")
        },
        "created_by": "user",
        "note": "accepted",
        "created_at": "2026-09-07T00:00:00Z",
        "activated_at": "2026-09-07T00:01:00Z",
        "pending_decisions": 0,
        "export": {"available": True, "formats": ["zip"]},
    }
    value.update(updates)
    return value


def wiki_page():
    return {
        "id": WIKI_DOCUMENT,
        "package_slug": WIKI_SLUG,
        "topic": "voice",
        "topic_path": "voice/brand-voice",
        "key": "brand-voice",
        "name": "Brand voice",
        "description": "Accepted voice guidance",
        "origin": "brand",
        "authority": "brand_preference",
        "active_version": 4,
        "review_due": None,
        "applies_products": [],
        "applies_markets": ["US"],
        "applies_languages": ["en"],
        "pending_proposals": 1,
        "updated_at": "2026-09-07T00:00:00Z",
        "sources": [{"url": "https://brand.example/voice", "title": "Voice guide"}],
        "confirmed_by": "user",
        "supersedes": [],
        "used_by_skills": [
            {
                "document_id": DOCUMENT,
                "package_slug": SKILL_SLUG,
                "name": "Content",
                "version": 3,
            }
        ],
        "versions": [
            {
                "id": WIKI_VERSION_ID,
                "version": 4,
                "text": "private body must not appear",
                "metadata": {"private": "must not appear"},
                "skill_md": "---\nauthority: brand_preference\n---\nvoice",
                "package_digest": WIKI_DIGEST,
                "hosted_support_files": False,
                "support_files": [
                    {
                        "path": "references/example.md",
                        "content": "private example",
                        "editable": True,
                        "size_bytes": 15,
                        "hosted": False,
                    }
                ],
                "created_by": "brand",
                "note": "accepted",
                "created_at": "2026-09-07T00:00:00Z",
                "promoted_at": "2026-09-07T00:01:00Z",
            }
        ],
    }


def error_code(error):
    return json.loads(str(error))["code"]


def test_tools_are_registered_read_only():
    registered = {tool.name: tool for tool in mcp._tool_manager.list_tools()}
    names = {
        "aeko_get_active_brand_package",
        "aeko_get_brand_package_version",
        "aeko_read_brand_package_file",
        "aeko_get_brand_wiki_chapters",
        "aeko_list_brand_wiki_pages",
        "aeko_get_brand_wiki_page",
    }
    assert names <= registered.keys()
    for name in names:
        assert registered[name].annotations.readOnlyHint is True
        assert registered[name].annotations.idempotentHint is True


def test_active_and_exact_package_forward_tenant_and_preserve_identity(monkeypatch):
    calls = []

    def get(path, params):
        calls.append((path, params))
        return package(active=False)

    monkeypatch.setattr(tools.client, "get", get)
    active = tools.aeko_get_active_brand_package(DOMAIN).model_dump()
    exact = tools.aeko_get_brand_package_version(DOMAIN, 7).model_dump()

    assert calls == [
        ("/api/automations/brand-package", {"domain_id": DOMAIN}),
        ("/api/automations/brand-package/versions/7", {"domain_id": DOMAIN}),
    ]
    for data in (active, exact):
        assert data["domain_id"] == DOMAIN
        assert data["id"] == PACKAGE_ID
        assert data["version"] == 7
        assert data["digest"] == PACKAGE_DIGEST
        assert data["members"][0]["version_id"] == VERSION_ID
        # A run snapshot may no longer be the current head; false is still a valid pin.
        assert data["active"] is False


def test_package_metadata_pages_are_utf8_bounded_without_losing_members(monkeypatch):
    members = [
        member(
            document_id=str(uuid4()),
            version_id=str(uuid4()),
            package_slug=f"skill-content-{index:03}-{'a' * 80}",
            key=f"규칙-{index}-{'가' * 80}",
        )
        for index in range(128)
    ]
    monkeypatch.setattr(tools.client, "get", lambda *args, **kwargs: package(members))
    offset, seen = 0, []
    while True:
        result = tools.aeko_get_active_brand_package(DOMAIN, offset=offset, limit=100)
        # The bound applies to FastMCP's JSON text rendering of the result.
        assert text_bytes(result) <= tools.METADATA_PAGE_BYTES
        data = result.model_dump()
        seen.extend(row["document_id"] for row in data["members"])
        if data["next_offset"] is None:
            break
        assert data["next_offset"] > offset
        offset = data["next_offset"]
    assert seen == [row["document_id"] for row in members]


def test_member_file_read_uses_canonical_slug_and_exact_release_pin(monkeypatch):
    expected = "브랜드 원칙 😊\n" * 80
    calls = []

    def get(path, params):
        calls.append((path, params))
        if path == "/api/automations/brand-package/versions/7":
            return package(
                [
                    member(),
                    member(
                        document_id=str(uuid4()),
                        version_id=str(uuid4()),
                        kind="eval",
                        subkind="quality",
                        key="default",
                        package_slug="eval-quality-default-regression",
                    ),
                ]
            )
        assert path == f"/api/automations/documents/{DOCUMENT}/versions/3/files"
        assert params == {"domain_id": DOMAIN, "path": "SKILL.md"}
        return {
            "document_id": DOCUMENT,
            "version_id": VERSION_ID,
            "version": 3,
            "path": "SKILL.md",
            "content": expected,
            "size_bytes": len(expected.encode("utf-8")),
            "editable": True,
            "hosted": True,
            "package_digest": MEMBER_DIGEST,
        }

    monkeypatch.setattr(tools.client, "get", get)
    offset, chunks = 0, []
    while True:
        data = tools.aeko_read_brand_package_file(
            DOMAIN, 7, PACKAGE_DIGEST, SKILL_SLUG, offset=offset, max_bytes=256
        ).model_dump()
        assert data["package_id"] == PACKAGE_ID
        assert data["member"]["version_id"] == VERSION_ID
        assert data["member"]["digest"] == MEMBER_DIGEST
        assert len(data["content"].encode("utf-8")) <= 256
        chunks.append(data["content"])
        if data["complete"]:
            break
        offset = data["next_offset"]
    assert "".join(chunks) == expected
    assert all(call[1]["domain_id"] == DOMAIN for call in calls)


def test_release_digest_or_slug_mismatch_never_reads_a_document(monkeypatch):
    calls = []

    def get(path, params):
        calls.append(path)
        return package()

    monkeypatch.setattr(tools.client, "get", get)
    with pytest.raises(RuntimeError, match="digest mismatch") as mismatch:
        tools.aeko_read_brand_package_file(DOMAIN, 7, "d" * 64, SKILL_SLUG)
    with pytest.raises(RuntimeError, match="not present") as missing:
        tools.aeko_read_brand_package_file(DOMAIN, 7, PACKAGE_DIGEST, "aeko-missing")
    assert error_code(mismatch.value) == "PACKAGE_DIGEST_MISMATCH"
    assert error_code(missing.value) == "PACKAGE_MEMBER_NOT_FOUND"
    assert calls == [
        "/api/automations/brand-package/versions/7",
        "/api/automations/brand-package/versions/7",
    ]


def test_duplicate_canonical_slug_is_rejected(monkeypatch):
    duplicate = member(document_id=str(uuid4()), version_id=str(uuid4()))
    monkeypatch.setattr(
        tools.client, "get", lambda *args, **kwargs: package([member(), duplicate])
    )
    with pytest.raises(RuntimeError, match="duplicate canonical") as caught:
        tools.aeko_read_brand_package_file(DOMAIN, 7, PACKAGE_DIGEST, SKILL_SLUG)
    assert error_code(caught.value) == "PACKAGE_MEMBER_DUPLICATE"


@pytest.mark.parametrize(
    "payload",
    [
        package([member(kind="unknown")]),
        package([member(version_id="not-a-uuid")]),
        package(counts={"skill": 2, "eval": 0, "wiki": 0}),
        package(created_at=1),
    ],
)
def test_malformed_release_manifest_is_rejected(monkeypatch, payload):
    monkeypatch.setattr(tools.client, "get", lambda *args, **kwargs: payload)
    with pytest.raises(RuntimeError, match="invalid|unexpected") as caught:
        tools.aeko_get_active_brand_package(DOMAIN)
    assert error_code(caught.value) == "INVALID_BACKEND_RESPONSE"


def test_member_version_drift_is_rejected(monkeypatch):
    def get(path, params):
        if path == "/api/automations/brand-package/versions/7":
            return package()
        return {
            "document_id": DOCUMENT,
            "version_id": str(uuid4()),
            "version": 3,
            "path": "SKILL.md",
            "content": "wrong version",
            "editable": True,
            "hosted": True,
            "package_digest": MEMBER_DIGEST,
        }

    monkeypatch.setattr(tools.client, "get", get)
    with pytest.raises(RuntimeError, match="outside the accepted package member pin") as caught:
        tools.aeko_read_brand_package_file(DOMAIN, 7, PACKAGE_DIGEST, SKILL_SLUG)
    assert error_code(caught.value) == "PACKAGE_MEMBER_PIN_MISMATCH"


def test_required_wiki_is_loaded_from_the_same_pinned_package(monkeypatch):
    wiki_member = member(
        document_id=WIKI_DOCUMENT,
        version_id=WIKI_VERSION_ID,
        version=4,
        kind="wiki",
        subkind="voice",
        key="brand-voice",
        package_slug=WIKI_SLUG,
        digest=WIKI_DIGEST,
        origin="brand",
    )
    release = package([member(), wiki_member])
    contents = {
        DOCUMENT: (
            VERSION_ID,
            3,
            MEMBER_DIGEST,
            "---\nrequires_knowledge:\n  - voice/brand-voice\n---\nDraft with the accepted voice.\n",
        ),
        WIKI_DOCUMENT: (
            WIKI_VERSION_ID,
            4,
            WIKI_DIGEST,
            "---\nauthority: brand_preference\nsources:\n  - url: https://brand.example/voice\n---\nUse a calm tone.\n",
        ),
    }

    def get(path, params):
        if path == "/api/automations/brand-package/versions/7":
            return release
        document_id = path.split("/")[4]
        version_id, version, digest, content = contents[document_id]
        return {
            "document_id": document_id,
            "version_id": version_id,
            "version": version,
            "path": params["path"],
            "content": content,
            "editable": True,
            "hosted": True,
            "package_digest": digest,
        }

    monkeypatch.setattr(tools.client, "get", get)
    skill = tools.aeko_read_brand_package_file(
        DOMAIN, 7, PACKAGE_DIGEST, SKILL_SLUG
    ).model_dump()
    wiki = tools.aeko_read_brand_package_file(
        DOMAIN, 7, PACKAGE_DIGEST, WIKI_SLUG
    ).model_dump()
    assert skill["package_id"] == wiki["package_id"] == PACKAGE_ID
    assert skill["package_digest"] == wiki["package_digest"] == PACKAGE_DIGEST
    assert "voice/brand-voice" in skill["content"]
    assert "authority: brand_preference" in wiki["content"]
    assert "https://brand.example/voice" in wiki["content"]


def test_wiki_list_forwards_filters_and_omits_bodies(monkeypatch):
    calls = []
    page = wiki_page()
    page["text"] = "must not appear"

    def get(path, params):
        calls.append((path, params))
        return {"pages": [page], "next_offset": 4}

    monkeypatch.setattr(tools.client, "get", get)
    output = tools.aeko_list_brand_wiki_pages(
        DOMAIN,
        topic="voice",
        q="tone",
        authority="brand_preference",
        origin="brand",
        offset=3,
        limit=1,
    )
    data = json.loads(output)
    assert calls == [
        (
            "/api/automations/wiki/pages",
            {
                "domain_id": DOMAIN,
                "offset": 3,
                "limit": 1,
                "topic": "voice",
                "q": "tone",
                "authority": "brand_preference",
                "origin": "brand",
            },
        )
    ]
    assert data["pages"][0]["topic_path"] == "voice/brand-voice"
    assert data["pages"][0]["active_version"] == 4
    assert "must not appear" not in output


def test_wiki_detail_returns_only_accepted_version_manifest(monkeypatch):
    page = wiki_page()
    old = deepcopy(page["versions"][0])
    old.update(id=str(uuid4()), version=2, text="old private body")
    page["versions"].insert(0, old)
    monkeypatch.setattr(tools.client, "get", lambda *args, **kwargs: page)
    output = tools.aeko_get_brand_wiki_page(DOMAIN, WIKI_DOCUMENT)
    data = json.loads(output)
    assert data["authority"] == "brand_preference"
    assert data["sources"][0]["url"] == "https://brand.example/voice"
    assert data["accepted_version"]["version_id"] == WIKI_VERSION_ID
    assert data["accepted_version"]["digest"] == WIKI_DIGEST
    assert data["available_version_count"] == 2
    assert "private body" not in output
    assert "private example" not in output
    assert '"private"' not in output


def test_wiki_registry_is_bounded_and_forwards_domain(monkeypatch):
    calls = []

    def get(path, params):
        calls.append((path, params))
        return {
            "chapters": [
                {
                    "id": "voice",
                    "order": 4,
                    "label_ko": "보이스",
                    "label_en": "Voice",
                    "sections": [],
                }
            ],
            "legacy_topic_aliases": {
                "examples/approved-examples": "voice/approved-examples"
            },
        }

    monkeypatch.setattr(tools.client, "get", get)
    output = tools.aeko_get_brand_wiki_chapters(DOMAIN)
    assert len(output.encode("utf-8")) <= tools.METADATA_PAGE_BYTES
    assert calls == [("/api/automations/wiki/chapters", {"domain_id": DOMAIN})]


@pytest.mark.parametrize(
    "path",
    [
        "/api/automations/brand-package",
        "/api/automations/wiki/pages",
    ],
)
def test_missing_backend_capability_is_actionable(monkeypatch, path):
    def respond(request):
        return httpx.Response(404, json={"detail": "Not Found"})

    client = AekoClient()
    client.close()
    client._client = httpx.Client(
        base_url="https://backend.test", transport=httpx.MockTransport(respond)
    )
    monkeypatch.setattr(tools, "client", client)
    try:
        if path.endswith("brand-package"):
            message = "Brand Package read API"
        else:
            message = "Brand Wiki read API"
        with pytest.raises(RuntimeError, match=message) as caught:
            if path.endswith("brand-package"):
                tools.aeko_get_active_brand_package(DOMAIN)
            else:
                tools.aeko_list_brand_wiki_pages(DOMAIN)
        if path.endswith("brand-package"):
            assert error_code(caught.value) == "CAPABILITY_UNAVAILABLE"
        else:
            assert not isinstance(caught.value, AekoToolError)
    finally:
        client.close()


def test_oauth_or_run_bearer_is_forwarded_but_never_returned(monkeypatch):
    token = "aeko_rt1_synthetic"
    seen = []

    def respond(request):
        seen.append(request)
        return httpx.Response(200, json=package())

    client = AekoClient()
    client.close()
    client._client = httpx.Client(
        base_url="https://backend.test", transport=httpx.MockTransport(respond)
    )
    monkeypatch.setattr(tools, "client", client)
    context = client.set_request_auth_token(token)
    try:
        output = pydantic_core.to_json(tools.aeko_get_active_brand_package(DOMAIN)).decode()
    finally:
        client.reset_request_auth_token(context)
        client.close()
    assert seen[0].headers["Authorization"] == f"Bearer {token}"
    assert seen[0].url.params["domain_id"] == DOMAIN
    assert token not in output


def test_invalid_ids_versions_digests_paths_and_budgets_fail_before_io(monkeypatch):
    monkeypatch.setattr(
        tools.client,
        "get",
        lambda *args, **kwargs: pytest.fail("invalid input reached backend"),
    )
    invalid_calls = [
        lambda: tools.aeko_get_active_brand_package("not-a-uuid"),
        lambda: tools.aeko_get_active_brand_package(DOMAIN, limit=0),
        lambda: tools.aeko_get_brand_package_version(DOMAIN, 0),
        lambda: tools.aeko_read_brand_package_file(DOMAIN, 7, "bad", SKILL_SLUG),
        lambda: tools.aeko_read_brand_package_file(DOMAIN, 7, PACKAGE_DIGEST, "../slug"),
        lambda: tools.aeko_read_brand_package_file(
            DOMAIN, 7, PACKAGE_DIGEST, SKILL_SLUG, path="../rules.md"
        ),
        lambda: tools.aeko_read_brand_package_file(
            DOMAIN, 7, PACKAGE_DIGEST, SKILL_SLUG, max_bytes=16385
        ),
    ]
    for invalid in invalid_calls:
        with pytest.raises(ValueError) as caught:
            invalid()
        assert isinstance(caught.value, AekoToolInputError)
        payload = json.loads(str(caught.value))
        assert (payload["code"], payload["mutation_state"]) == ("INVALID_ARGUMENT", "not_attempted")
