"""Bounded reads for accepted whole-brand packages and Brand Wiki pages."""

from __future__ import annotations

import json
import re
from typing import Literal, Optional
from uuid import UUID

from ..server import client, mcp
from ._annotations import READ_ONLY

METADATA_PAGE_BYTES = 32 * 1024
MAX_PACKAGE_MEMBERS = 128
MAX_FILE_BYTES = 256 * 1024
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_PACKAGE_SLUG = re.compile(r"^[a-z0-9][a-z0-9._-]{0,159}$")


def _uuid(value: str) -> str:
    return str(UUID(str(value)))


def _integer(value: int, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"Expected an integer between {minimum} and {maximum}.")
    return value


def _json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)


def _digest(value: str, label: str = "digest") -> str:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256 digest.")
    return value


def _relative_path(path: str) -> str:
    if (
        not isinstance(path, str)
        or not path
        or len(path.encode("utf-8")) > 240
        or "\\" in path
        or "\x00" in path
        or any(part in {"", ".", ".."} for part in path.split("/"))
    ):
        raise ValueError("Use an exact relative path from the package manifest.")
    return path


def _get_capability(path: str, *, params: dict, capability: str) -> dict:
    try:
        return client.get(path, params=params)
    except RuntimeError as exc:
        message = str(exc)
        # A FastAPI router that is absent returns the plain detail "Not Found".
        # Preserve typed resource errors such as BRAND_PACKAGE_NOT_INITIALIZED.
        if message == "Not Found" or message.endswith(" — Not Found"):
            raise RuntimeError(
                f"This AEKO backend does not provide {capability} yet. "
                "Update the deployed backend before using this tool."
            ) from None
        raise


def _member(value: object) -> dict:
    if not isinstance(value, dict):
        raise RuntimeError("AEKO returned an invalid brand package member.")
    try:
        result = {
            "document_id": _uuid(value["document_id"]),
            "version_id": _uuid(value["version_id"]),
            "version": _integer(value["version"], 1, 2**31 - 1),
            "kind": value["kind"],
            "subkind": value["subkind"],
            "key": value["key"],
            "package_slug": value["package_slug"],
            "digest": _digest(value["digest"], "member digest"),
            "origin": value["origin"],
            "upstream_document_id": (
                _uuid(value["upstream_document_id"])
                if value.get("upstream_document_id") is not None
                else None
            ),
        }
    except (KeyError, TypeError, ValueError):
        raise RuntimeError("AEKO returned an invalid brand package member.") from None
    if result["kind"] not in {"skill", "eval", "wiki"}:
        raise RuntimeError("AEKO returned an invalid brand package member kind.")
    if result["origin"] not in {"aeko_default", "brand"}:
        raise RuntimeError("AEKO returned an invalid brand package member origin.")
    if (
        not isinstance(result["subkind"], str)
        or not isinstance(result["key"], str)
        or not isinstance(result["package_slug"], str)
        or _PACKAGE_SLUG.fullmatch(result["package_slug"]) is None
    ):
        raise RuntimeError("AEKO returned an invalid brand package member identity.")
    return result


def _package(domain_id: str, version: int | None = None) -> dict:
    domain_id = _uuid(domain_id)
    if version is None:
        path = "/api/automations/brand-package"
    else:
        _integer(version, 1, 2**31 - 1)
        path = f"/api/automations/brand-package/versions/{version}"
    data = _get_capability(
        path,
        params={"domain_id": domain_id},
        capability="the Brand Package read API",
    )
    if not isinstance(data, dict) or not isinstance(data.get("members"), list):
        raise RuntimeError("AEKO returned an unexpected brand package.")
    if len(data["members"]) > MAX_PACKAGE_MEMBERS:
        raise RuntimeError("AEKO returned a brand package exceeding the member limit.")
    try:
        normalized = {
            "id": _uuid(data["id"]),
            "active": data["active"],
            "version": _integer(data["version"], 1, 2**31 - 1),
            "digest": _digest(data["digest"], "package digest"),
            "base_package_id": (
                _uuid(data["base_package_id"])
                if data.get("base_package_id") is not None
                else None
            ),
            "base_version": data.get("base_version"),
            "members": [_member(value) for value in data["members"]],
            "counts": data["counts"],
            "created_by": data["created_by"],
            "note": data.get("note"),
            "created_at": data["created_at"],
            "activated_at": data.get("activated_at"),
            "pending_decisions": data["pending_decisions"],
            "export": data["export"],
        }
    except (KeyError, TypeError, ValueError):
        raise RuntimeError("AEKO returned an unexpected brand package.") from None
    if type(normalized["active"]) is not bool:
        raise RuntimeError("AEKO returned an invalid brand package state.")
    if normalized["base_version"] is not None:
        try:
            normalized["base_version"] = _integer(
                normalized["base_version"], 1, 2**31 - 1
            )
        except ValueError:
            raise RuntimeError(
                "AEKO returned an invalid base package version."
            ) from None
    if (
        not isinstance(normalized["counts"], dict)
        or any(
            type(normalized["counts"].get(kind)) is not int
            or normalized["counts"][kind] < 0
            for kind in ("skill", "eval", "wiki")
        )
        or sum(normalized["counts"][kind] for kind in ("skill", "eval", "wiki"))
        != len(normalized["members"])
    ):
        raise RuntimeError("AEKO returned invalid brand package counts.")
    if (
        type(normalized["pending_decisions"]) is not int
        or normalized["pending_decisions"] < 0
        or not isinstance(normalized["export"], dict)
    ):
        raise RuntimeError("AEKO returned invalid brand package metadata.")
    if version is not None and normalized["version"] != version:
        raise RuntimeError("AEKO returned an unexpected brand package version.")
    return normalized


def _package_page(data: dict, *, domain_id: str, offset: int, limit: int) -> str:
    _integer(offset, 0, 2**31 - 1)
    _integer(limit, 1, 100)
    members = data.pop("members")
    payload = {
        "domain_id": _uuid(domain_id),
        **data,
        "total_members": len(members),
        "members": [],
        "next_offset": None,
    }
    if len(_json(payload).encode("utf-8")) > METADATA_PAGE_BYTES:
        raise RuntimeError(
            "AEKO returned package metadata exceeding the page byte limit."
        )
    for index in range(offset, min(offset + limit, len(members))):
        candidate = {
            **payload,
            "members": [*payload["members"], members[index]],
            "next_offset": index + 1 if index + 1 < len(members) else None,
        }
        if len(_json(candidate).encode("utf-8")) > METADATA_PAGE_BYTES:
            if not payload["members"]:
                raise RuntimeError(
                    "AEKO returned member metadata exceeding the page byte limit."
                )
            payload["next_offset"] = index
            break
        payload = candidate
    return _json(payload)


@mcp.tool(title="Get the accepted brand package", annotations=READ_ONLY)
def aeko_get_active_brand_package(
    domain_id: str, offset: int = 0, limit: int = 50
) -> str:
    """Discover the immutable package accepted for this brand and credential.

    Normal OAuth selects the tenant's active package. A hosted run credential
    selects only that run's snapshot-pinned package, even if the current head
    has since changed. Authentication grants access but does not load any skill,
    eval, wiki page, or supporting file. Page through every member, retain the
    returned package id/version/digest, and load only the files the task needs.
    """
    return _package_page(
        _package(domain_id), domain_id=domain_id, offset=offset, limit=limit
    )


@mcp.tool(title="Get an exact brand package version", annotations=READ_ONLY)
def aeko_get_brand_package_version(
    domain_id: str, version: int, offset: int = 0, limit: int = 50
) -> str:
    """Discover one immutable package version without falling back to latest.

    Use this for a saved handoff that already pins a package version. A hosted
    run credential can read only its own pinned version. Keep the returned
    digest with the version and pass both to aeko_read_brand_package_file.
    """
    return _package_page(
        _package(domain_id, version),
        domain_id=domain_id,
        offset=offset,
        limit=limit,
    )


@mcp.tool(title="Read a file from an accepted brand package", annotations=READ_ONLY)
def aeko_read_brand_package_file(
    domain_id: str,
    package_version: int,
    package_digest: str,
    package_slug: str,
    path: str = "SKILL.md",
    offset: int = 0,
    max_bytes: int = 8192,
) -> str:
    """Read one UTF-8 chunk after revalidating its exact release member.

    package_slug must come from the accepted release manifest. The tool checks
    package version/digest, canonical slug, document/version IDs, and member
    digest before returning bytes. Use the next_offset unchanged. Read the full
    selected SKILL.md, required evals, and declared wiki/support references
    before execution; OAuth or a run token only authorizes these reads.
    """
    _integer(package_version, 1, 2**31 - 1)
    _integer(offset, 0, 2 * 1024 * 1024)
    _integer(max_bytes, 256, 16384)
    package_digest = _digest(package_digest, "package_digest")
    if (
        not isinstance(package_slug, str)
        or _PACKAGE_SLUG.fullmatch(package_slug) is None
    ):
        raise ValueError("Use an exact package_slug from the brand package manifest.")
    path = _relative_path(path)

    package = _package(domain_id, package_version)
    if package["digest"] != package_digest:
        raise RuntimeError(
            "Brand package digest mismatch. Rediscover the exact accepted package; "
            "do not continue with mixed release bytes."
        )
    matches = [
        member
        for member in package["members"]
        if member["package_slug"] == package_slug
    ]
    if not matches:
        raise RuntimeError("The canonical package_slug is not present in this release.")
    if len(matches) != 1:
        raise RuntimeError("AEKO returned duplicate canonical package slugs.")
    member = matches[0]
    data = _get_capability(
        (
            f"/api/automations/documents/{member['document_id']}"
            f"/versions/{member['version']}/files"
        ),
        params={"domain_id": _uuid(domain_id), "path": path},
        capability="immutable document file reads",
    )
    if (
        not isinstance(data, dict)
        or data.get("document_id") != member["document_id"]
        or data.get("version_id") != member["version_id"]
        or data.get("version") != member["version"]
        or data.get("package_digest") != member["digest"]
        or data.get("path") != path
        or not isinstance(data.get("content"), str)
    ):
        raise RuntimeError(
            "AEKO returned a file outside the accepted package member pin."
        )
    raw = data["content"].encode("utf-8")
    if len(raw) > (128 * 1024 if path == "SKILL.md" else MAX_FILE_BYTES):
        raise RuntimeError("AEKO returned a file exceeding the package byte limit.")
    if offset > len(raw) or (offset < len(raw) and raw[offset] & 0xC0 == 0x80):
        raise ValueError("offset must be a UTF-8 boundary within the file.")
    chunk = raw[offset : offset + max_bytes].decode("utf-8", errors="ignore")
    end = offset + len(chunk.encode("utf-8"))
    return _json(
        {
            "domain_id": _uuid(domain_id),
            "package_id": package["id"],
            "package_version": package["version"],
            "package_digest": package["digest"],
            "member": member,
            "path": path,
            "hosted": data.get("hosted"),
            "editable": data.get("editable"),
            "size_bytes": len(raw),
            "offset": offset,
            "next_offset": end if end < len(raw) else None,
            "complete": end == len(raw),
            "content": chunk,
        }
    )


@mcp.tool(title="List Brand Wiki chapters", annotations=READ_ONLY)
def aeko_get_brand_wiki_chapters(domain_id: str) -> str:
    """Read the server-owned six-chapter Brand Wiki navigation registry.

    This registry describes allowed topic paths; it does not load their bytes.
    Normal OAuth can read it. Hosted run credentials remain limited to their
    package and pinned wiki pages and may reject this non-snapshot registry read.
    """
    domain_id = _uuid(domain_id)
    data = _get_capability(
        "/api/automations/wiki/chapters",
        params={"domain_id": domain_id},
        capability="the Brand Wiki read API",
    )
    if (
        not isinstance(data, dict)
        or not isinstance(data.get("chapters"), list)
        or not isinstance(data.get("legacy_topic_aliases"), dict)
    ):
        raise RuntimeError("AEKO returned an unexpected Brand Wiki registry.")
    output = _json({"domain_id": domain_id, **data})
    if len(output.encode("utf-8")) > METADATA_PAGE_BYTES:
        raise RuntimeError(
            "AEKO returned a Brand Wiki registry exceeding the byte limit."
        )
    return output


@mcp.tool(title="List accepted Brand Wiki pages", annotations=READ_ONLY)
def aeko_list_brand_wiki_pages(
    domain_id: str,
    topic: Optional[
        Literal[
            "identity",
            "products",
            "audience",
            "voice",
            "markets",
            "perception",
            "examples",
        ]
    ] = None,
    q: Optional[str] = None,
    authority: Optional[
        Literal[
            "confirmed_fact",
            "brand_preference",
            "official_source",
            "external_observation",
            "proposed",
        ]
    ] = None,
    origin: Optional[Literal["default", "brand"]] = None,
    offset: int = 0,
    limit: int = 50,
) -> str:
    """List wiki metadata from the active or run-snapshot package.

    The backend resolves accepted versions before filtering. The result contains
    no wiki body. Match required knowledge by exact topic_path, then read that
    page through its package_slug in the same accepted package release.
    """
    _integer(offset, 0, 2**31 - 1)
    _integer(limit, 1, 100)
    if q is not None and (not isinstance(q, str) or len(q) > 200):
        raise ValueError("q must contain at most 200 characters.")
    params: dict[str, object] = {
        "domain_id": _uuid(domain_id),
        "offset": offset,
        "limit": limit,
    }
    for key, value in (
        ("topic", topic),
        ("q", q),
        ("authority", authority),
        ("origin", origin),
    ):
        if value is not None:
            params[key] = value
    data = _get_capability(
        "/api/automations/wiki/pages",
        params=params,
        capability="the Brand Wiki read API",
    )
    pages = data.get("pages") if isinstance(data, dict) else None
    if not isinstance(pages, list) or any(not isinstance(page, dict) for page in pages):
        raise RuntimeError("AEKO returned an unexpected Brand Wiki page list.")
    if len(pages) > limit:
        raise RuntimeError("AEKO returned more Brand Wiki pages than requested.")
    next_offset = data.get("next_offset")
    if next_offset is not None and (
        type(next_offset) is not int or next_offset <= offset
    ):
        raise RuntimeError("AEKO returned an invalid Brand Wiki continuation offset.")
    fields = (
        "id",
        "package_slug",
        "topic",
        "topic_path",
        "key",
        "name",
        "description",
        "origin",
        "authority",
        "active_version",
        "review_due",
        "applies_products",
        "applies_markets",
        "applies_languages",
        "pending_proposals",
        "updated_at",
    )
    selected = [{key: page.get(key) for key in fields} for page in pages]
    for page in selected:
        try:
            page["id"] = _uuid(page["id"])
        except (TypeError, ValueError):
            raise RuntimeError(
                "AEKO returned an invalid Brand Wiki page identity."
            ) from None
        if (
            not isinstance(page["package_slug"], str)
            or _PACKAGE_SLUG.fullmatch(page["package_slug"]) is None
            or page["active_version"] is not None
            and (type(page["active_version"]) is not int or page["active_version"] < 1)
        ):
            raise RuntimeError("AEKO returned invalid Brand Wiki page metadata.")
    output = _json(
        {
            "domain_id": params["domain_id"],
            "pages": selected,
            "next_offset": next_offset,
        }
    )
    if len(output.encode("utf-8")) > METADATA_PAGE_BYTES:
        raise RuntimeError(
            "AEKO returned Brand Wiki metadata exceeding the page byte limit."
        )
    return output


@mcp.tool(title="Inspect one accepted Brand Wiki page", annotations=READ_ONLY)
def aeko_get_brand_wiki_page(domain_id: str, document_id: str) -> str:
    """Inspect authority, provenance, and the accepted immutable wiki version.

    The backend selects the active-package version for OAuth and the exact run
    snapshot version for a hosted run token. Content and version history are
    omitted here. Load the accepted page's SKILL.md through
    aeko_read_brand_package_file before using it as brand knowledge.
    """
    domain_id = _uuid(domain_id)
    document_id = _uuid(document_id)
    data = _get_capability(
        f"/api/automations/wiki/pages/{document_id}",
        params={"domain_id": domain_id},
        capability="the Brand Wiki read API",
    )
    if not isinstance(data, dict) or not isinstance(data.get("versions"), list):
        raise RuntimeError("AEKO returned an unexpected Brand Wiki page.")
    active_version = data.get("active_version")
    accepted = next(
        (
            value
            for value in data["versions"]
            if isinstance(value, dict) and value.get("version") == active_version
        ),
        None,
    )
    if active_version is not None and accepted is None:
        raise RuntimeError("AEKO omitted the accepted Brand Wiki version.")
    version = None
    if accepted is not None:
        try:
            support_files = accepted.get("support_files", [])
            if not isinstance(support_files, list) or len(support_files) > 64:
                raise TypeError
            if not isinstance(accepted["skill_md"], str):
                raise TypeError
            version = {
                "version_id": _uuid(accepted["id"]),
                "version": _integer(accepted["version"], 1, 2**31 - 1),
                "digest": _digest(accepted["package_digest"], "wiki version digest"),
                "created_by": accepted["created_by"],
                "created_at": accepted["created_at"],
                "promoted_at": accepted.get("promoted_at"),
                "files": [
                    {
                        "path": "SKILL.md",
                        "size_bytes": len(accepted["skill_md"].encode("utf-8")),
                        "hosted": True,
                    },
                    *[
                        {
                            key: support.get(key)
                            for key in ("path", "size_bytes", "editable", "hosted")
                        }
                        for support in support_files
                        if isinstance(support, dict)
                    ],
                ],
            }
        except (KeyError, TypeError, ValueError):
            raise RuntimeError(
                "AEKO returned an invalid accepted Brand Wiki version."
            ) from None
    fields = (
        "id",
        "package_slug",
        "topic",
        "topic_path",
        "key",
        "name",
        "description",
        "origin",
        "authority",
        "active_version",
        "review_due",
        "applies_products",
        "applies_markets",
        "applies_languages",
        "pending_proposals",
        "updated_at",
        "sources",
        "confirmed_by",
        "supersedes",
        "used_by_skills",
    )
    payload = {key: data.get(key) for key in fields}
    try:
        payload["id"] = _uuid(payload["id"])
    except (TypeError, ValueError):
        raise RuntimeError(
            "AEKO returned an invalid Brand Wiki page identity."
        ) from None
    output = _json(
        {
            "domain_id": domain_id,
            **payload,
            "accepted_version": version,
            "available_version_count": len(data["versions"]),
        }
    )
    if len(output.encode("utf-8")) > METADATA_PAGE_BYTES:
        raise RuntimeError(
            "AEKO returned Brand Wiki detail exceeding the page byte limit."
        )
    return output
