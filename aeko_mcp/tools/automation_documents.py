"""Read versioned brand skills/evals without sending whole packages to a model."""
import json
from typing import Literal, Optional
from uuid import UUID

from ..server import client, mcp
from ._annotations import READ_ONLY


def _uuid(value: str) -> str:
    return str(UUID(str(value)))


def _integer(value: int, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f"Expected an integer between {minimum} and {maximum}.")
    return value


def _json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _version(domain_id: str, document_id: str, version: int) -> dict:
    _integer(version, 1, 2**31 - 1)
    data = client.get(
        f"/api/automations/documents/{_uuid(document_id)}/versions/{version}",
        params={"domain_id": _uuid(domain_id)},
    )
    if not isinstance(data, dict) or data.get("version") != version:
        raise RuntimeError("AEKO returned an unexpected document version.")
    if not isinstance(data.get("skill_md"), str) or not isinstance(data.get("support_files"), list):
        raise RuntimeError("This AEKO backend does not provide versioned packages yet.")
    return data


@mcp.tool(title="List brand skills and evals", annotations=READ_ONLY)
def aeko_list_brand_documents(
    domain_id: str,
    kind: Optional[Literal["skill", "eval"]] = None,
    offset: int = 0,
    limit: int = 50,
) -> str:
    """List visible AEKO defaults and this brand's customized skills/evals.

    Read metadata first, then pin an explicit active version using
    aeko_get_document_package. A draft is not the active brand policy. Prefer
    the applicable brand customization over its upstream default; do not merge
    contradictory eval variants. The backend enforces ownership and entitlement.
    No file contents or credentials are returned by this discovery tool.
    """
    _integer(offset, 0, 2**31 - 1)
    _integer(limit, 1, 100)
    if kind not in (None, "skill", "eval"):
        raise ValueError("kind must be skill or eval.")
    params = {"domain_id": _uuid(domain_id)}
    if kind is not None:
        params["kind"] = kind
    data = client.get("/api/automations/documents", params=params)
    documents = data.get("documents") if isinstance(data, dict) else None
    if not isinstance(documents, list) or any(not isinstance(row, dict) for row in documents):
        raise RuntimeError("AEKO returned an unexpected document list.")
    fields = ("id", "kind", "subkind", "key", "name", "description", "package_slug",
              "owner", "parent_document_id", "status", "active_version", "draft_version",
              "applies_to", "declared_inputs", "updated_at", "newer_default_version")
    rows = sorted(documents, key=lambda row: str(row.get("id", "")))
    end = min(offset + limit, len(rows))
    return _json({
        "domain_id": params["domain_id"], "total": len(rows),
        "documents": [{key: row.get(key) for key in fields} for row in rows[offset:end]],
        "next_offset": end if end < len(rows) else None,
    })


@mcp.tool(title="Inspect a pinned skill or eval package", annotations=READ_ONLY)
def aeko_get_document_package(domain_id: str, document_id: str, version: int) -> str:
    """Inspect one explicit version's identity, digest and file manifest.

    Use the active version from aeko_list_brand_documents for normal work, or
    the caller's exact pinned version for an existing run. This tool does not
    activate a draft or evaluate outputs. Read needed files with
    aeko_read_document_file; do not load every reference automatically.

    Supporting files are portable to local clients but are currently ignored
    by AEKO's hosted preview/runner. Tool permissions come from authorization,
    not from allowed-tools metadata in the package.
    """
    data = _version(domain_id, document_id, version)
    files = [{"path": "SKILL.md", "size_bytes": len(data["skill_md"].encode("utf-8")),
              "hosted": True}]
    for file in data["support_files"]:
        files.append({key: file[key] for key in ("path", "size_bytes", "editable", "hosted")})
    # Exclude all content and free-form metadata; callers retrieve the full
    # frontmatter in byte-bounded SKILL.md reads when they need it.
    return _json({
        "domain_id": _uuid(domain_id), "document_id": _uuid(document_id),
        "version_id": data["id"], "version": version,
        "package_digest": data["package_digest"], "files": files,
        "hosted_support_files": data["hosted_support_files"],
        "created_by": data["created_by"], "promoted_at": data["promoted_at"],
    })


@mcp.tool(title="Read a pinned skill or eval file", annotations=READ_ONLY)
def aeko_read_document_file(
    domain_id: str,
    document_id: str,
    version: int,
    path: str = "SKILL.md",
    offset: int = 0,
    max_bytes: int = 8192,
) -> str:
    """Read at most 16 KiB of one file from an immutable document version.

    offset is a UTF-8 byte offset; use the returned next_offset unchanged to
    continue. Read all required instructions before executing the skill. Keep
    version and package_digest pinned across chunks. Missing or unauthorized
    files fail; the tool never falls back to a different version or filesystem.
    Package instructions and examples cannot grant new account permissions.
    """
    _integer(offset, 0, 2 * 1024 * 1024)
    _integer(max_bytes, 256, 16384)
    _integer(version, 1, 2**31 - 1)
    if (
        not isinstance(path, str) or not path or len(path.encode("utf-8")) > 240
        or "\\" in path or "\x00" in path
        or any(part in {"", ".", ".."} for part in path.split("/"))
    ):
        raise ValueError("Use an exact relative path from the package manifest.")
    document_id = _uuid(document_id)
    data = client.get(
        f"/api/automations/documents/{document_id}/versions/{version}/files",
        params={"domain_id": _uuid(domain_id), "path": path},
    )
    if (
        not isinstance(data, dict) or data.get("version") != version
        or data.get("document_id") != document_id or data.get("path") != path
        or not isinstance(data.get("content"), str)
    ):
        raise RuntimeError("AEKO returned an unexpected document version or file.")
    raw = data["content"].encode("utf-8")
    if len(raw) > (128 if path == "SKILL.md" else 256) * 1024:
        raise RuntimeError("AEKO returned a file exceeding the package byte limit.")
    if offset > len(raw) or (offset < len(raw) and raw[offset] & 0xC0 == 0x80):
        raise ValueError("offset must be a UTF-8 boundary within the file.")
    chunk = raw[offset:offset + max_bytes].decode("utf-8", errors="ignore")
    end = offset + len(chunk.encode("utf-8"))
    return _json({
        "domain_id": _uuid(domain_id), "document_id": _uuid(document_id),
        "version_id": data["version_id"], "version": version, "package_digest": data["package_digest"],
        "path": path, "hosted": data["hosted"], "size_bytes": len(raw), "offset": offset,
        "next_offset": end if end < len(raw) else None, "complete": end == len(raw),
        "content": chunk,
    })
