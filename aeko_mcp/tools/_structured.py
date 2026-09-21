"""Structured results and truthful errors for the migrated PDP-path tools.

Six tools return these Pydantic models with ``structured_output=True``:
FastMCP then publishes a field-level ``outputSchema`` and sends
``structuredContent`` together with its JSON text rendering.

A migrated tool reports failure by raising ``AekoToolError``. FastMCP 1.11–1.15
turns a raised exception into ``isError=true`` text, whereas a returned
error-shaped object would be reported as a successful call. The exception text
is one bounded ``aeko.error.v1`` JSON object and never includes backend bodies,
credentials, or arbitrary exception text.

Keep annotations as runtime types in this module and in the tool modules that
import it: MCP 1.11/1.12 cannot register postponed annotations.
"""

import json
import re
from contextlib import contextmanager
from typing import Any, Literal, Optional
from uuid import UUID

import httpx
import pydantic
import pydantic_core
from pydantic import BaseModel, ConfigDict, Field

from ..client import AekoAPIError

ERROR_SCHEMA = "aeko.error.v1"
MAX_ERROR_MESSAGE_CHARS = 300
_SAFE_CODE = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")
_UNSAFE_PATH_SEGMENT = re.compile(r"[/?#%\\\s\x00-\x1f\x7f]")

MutationState = Literal["not_attempted", "rejected", "unknown"]


class AekoToolError(RuntimeError):
    """A migrated tool failure rendered as one ``aeko.error.v1`` JSON object."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        mutation_state: str = "not_attempted",
        http_status: Optional[int] = None,
        audit_id: Optional[str] = None,
    ):
        self.code = code
        self.error_message = message[:MAX_ERROR_MESSAGE_CHARS]
        self.mutation_state = mutation_state
        self.http_status = http_status
        self.audit_id = audit_id
        super().__init__(json.dumps(self.payload, ensure_ascii=False, separators=(",", ":")))

    @property
    def payload(self) -> dict:
        return {
            "schema": ERROR_SCHEMA,
            "code": self.code,
            "message": self.error_message,
            "http_status": self.http_status,
            "audit_id": self.audit_id,
            "mutation_state": self.mutation_state,
        }


class AekoToolInputError(AekoToolError, ValueError):
    """A local argument failure; no backend request was sent."""


class CodedValueError(ValueError):
    """An authored argument error that keeps its legacy text for unmigrated tools."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class CodedRuntimeError(RuntimeError):
    """An authored backend/pin error that keeps its legacy text for unmigrated tools."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


_STATUS_ERRORS = {
    400: ("BAD_REQUEST", "AEKO rejected the request."),
    401: ("AUTHENTICATION_FAILED", "AEKO authentication failed. Reconnect the MCP client."),
    402: ("PAYMENT_REQUIRED", "The AEKO plan does not allow this request."),
    403: ("ACCESS_DENIED", "This AEKO account or credential cannot perform the request."),
    404: ("NOT_FOUND", "The requested AEKO resource was not found."),
    409: ("CONFLICT", "AEKO reported a conflicting state."),
    422: ("VALIDATION_FAILED", "AEKO rejected the request as invalid."),
    429: ("RATE_LIMITED", "AEKO rate-limited the request."),
}

# Authored explanations for backend codes on the migrated path. Backend detail
# messages are not forwarded because some embed upstream platform bodies.
_BACKEND_CODE_MESSAGES = {
    "ACTION_ITEM_CLAIM_REQUIRED": "The write needs the active execution claim for an owned action item.",
    "ACTION_ITEM_STATUS_CONFLICT": "The action item is not ready for a store write.",
    "ACTION_ITEM_NOT_STORE_WRITABLE": "The action item does not authorize a product-page write.",
    "ACTION_ITEM_PAYLOAD_MISMATCH": "The action item does not allow one or more requested fields.",
    "ACTION_ITEM_TARGET_MISMATCH": "The action item targets a different store integration or product.",
    "ACTION_ITEM_WRITE_PAYLOAD_CONFLICT": (
        "This execution claim already started a different store payload. Its result is unknown; "
        "reconcile the store and audit history before recovery."
    ),
    "ACTION_ITEM_WRITE_INDETERMINATE": (
        "This exact write started earlier without a recorded result. Reconcile the store and "
        "audit history; do not retry."
    ),
    "TIER_REQUIRED": "This artifact requires a higher AEKO plan.",
    "STORE_PRODUCT_NOT_FOUND": "The product was not found on the connected store.",
    "STORE_SNAPSHOT_FAILED": (
        "AEKO could not read the product's current state before writing, so the store write "
        "was not submitted."
    ),
    "SUBSCRIPTION_INACTIVE": "The AEKO subscription is inactive.",
    "REAUTH": "The connected store rejected its credential. Reconnect the store.",
    "RATE_LIMIT": "The connected store rate-limited the write.",
    "NETWORK_ERROR": "The connection between AEKO and the store failed during the write.",
    "PLATFORM_ERROR": "The connected store returned an error during the write.",
    "BRAND_PACKAGE_NOT_INITIALIZED": "This brand has no accepted package yet.",
}


def optional_uuid(value: Any) -> Optional[str]:
    """Return a UUID string unchanged when it parses, otherwise None."""
    if not isinstance(value, str):
        return None
    try:
        UUID(value)
    except ValueError:
        return None
    return value


def api_error(
    exc: AekoAPIError,
    *,
    mutation_state: str,
    code: Optional[str] = None,
    message: Optional[str] = None,
) -> AekoToolError:
    """Translate a client error without forwarding its backend message."""
    status = exc.http_status if type(exc.http_status) is int else None
    backend_code = exc.code if isinstance(exc.code, str) and _SAFE_CODE.fullmatch(exc.code) else None
    if status is None:
        fallback_code, fallback_message = (
            ("BACKEND_UNREACHABLE", "AEKO could not be reached.")
            if not exc.request_sent
            else ("BACKEND_UNAVAILABLE", "The request to AEKO failed.")
        )
    elif status >= 500:
        fallback_code, fallback_message = ("BACKEND_ERROR", "AEKO or its upstream service failed.")
    else:
        fallback_code, fallback_message = _STATUS_ERRORS.get(
            status, ("HTTP_ERROR", "AEKO returned an unexpected HTTP error.")
        )
    return AekoToolError(
        code or backend_code or fallback_code,
        message or _BACKEND_CODE_MESSAGES.get(backend_code or "", fallback_message),
        mutation_state=mutation_state,
        http_status=status,
        audit_id=optional_uuid(exc.audit_id),
    )


def read_failure(exc: BaseException) -> AekoToolError:
    """Translate any failure of a read-only migrated tool; nothing was mutated."""
    if isinstance(exc, AekoToolError):
        return exc
    if isinstance(exc, CodedValueError):
        return AekoToolInputError(exc.code, str(exc))
    if isinstance(exc, CodedRuntimeError):
        return AekoToolError(exc.code, str(exc))
    if isinstance(exc, AekoAPIError):
        return api_error(exc, mutation_state="not_attempted")
    if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)):
        return AekoToolError("BACKEND_UNREACHABLE", "AEKO could not be reached.")
    if isinstance(exc, httpx.TimeoutException):
        return AekoToolError("BACKEND_TIMEOUT", "AEKO did not respond before the timeout.")
    if isinstance(exc, httpx.TransportError):
        return AekoToolError("BACKEND_UNAVAILABLE", "The request to AEKO failed.")
    if isinstance(exc, json.JSONDecodeError):
        return AekoToolError("INVALID_BACKEND_RESPONSE", "AEKO returned a response that is not valid JSON.")
    if isinstance(exc, pydantic.ValidationError):
        return AekoToolError(
            "INVALID_BACKEND_RESPONSE", "AEKO returned data that does not match the tool result."
        )
    return AekoToolError("INTERNAL_ERROR", "The tool failed before returning a result.")


@contextmanager
def read_boundary():
    try:
        yield
    except Exception as exc:  # noqa: BLE001 - every failure becomes a bounded MCP error
        raise read_failure(exc) from None


def uuid_arg(value: Any, name: str) -> str:
    try:
        if not isinstance(value, str):
            raise ValueError
        return str(UUID(value))
    except ValueError:
        raise AekoToolInputError("INVALID_ARGUMENT", f"{name} must be a UUID.") from None


def path_segment_arg(value: Any, name: str) -> str:
    """Accept one exact ID that can be placed in a URL path unchanged."""
    try:
        encoded_length = len(value.encode("utf-8")) if isinstance(value, str) else 0
    except UnicodeError:
        encoded_length = 0
    if (
        not isinstance(value, str)
        or not value
        or encoded_length == 0
        or encoded_length > 255
        or _UNSAFE_PATH_SEGMENT.search(value)
    ):
        raise AekoToolInputError(
            "INVALID_ARGUMENT", f"{name} must be one exact ID without slashes, spaces, or query characters."
        )
    return value


def text_bytes(result: BaseModel) -> int:
    """UTF-8 size of FastMCP's text rendering of a structured result."""
    return len(pydantic_core.to_json(result, fallback=str, indent=2))


class _Result(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BrandPackageMember(_Result):
    document_id: str
    version_id: str
    version: int
    kind: Literal["skill", "eval", "wiki"]
    subkind: str
    key: str
    package_slug: str = Field(description="Canonical member slug to pass to aeko_read_brand_package_file.")
    digest: str = Field(description="Member version SHA-256 digest.")
    origin: Literal["aeko_default", "brand"]
    upstream_document_id: Optional[str] = None


class BrandPackagePage(_Result):
    domain_id: str
    id: str = Field(description="Accepted package release ID.")
    active: bool = Field(description="Whether this release is the brand's current head; a run snapshot may be false.")
    version: int = Field(description="Package release version to pin.")
    digest: str = Field(description="Package release SHA-256 digest to pin with the version.")
    base_package_id: Optional[str] = None
    base_version: Optional[int] = None
    counts: dict[str, int]
    created_by: str
    note: Optional[str] = None
    created_at: str
    activated_at: Optional[str] = None
    pending_decisions: int
    export: dict[str, Any]
    total_members: int
    members: list[BrandPackageMember]
    next_offset: Optional[int] = Field(
        default=None, description="Member offset for the next page, or null after the last member."
    )


class BrandPackageFileChunk(_Result):
    domain_id: str
    package_id: str
    package_version: int
    package_digest: str
    member: BrandPackageMember
    path: str
    hosted: Optional[bool] = None
    editable: Optional[bool] = None
    size_bytes: int = Field(description="UTF-8 size of the complete file.")
    offset: int
    next_offset: Optional[int] = Field(default=None, description="Byte offset of the next chunk, or null when complete.")
    complete: bool
    content: str = Field(description="UTF-8 content from offset up to next_offset.")


class ProductDescription(_Result):
    integration_id: str
    external_product_id: str
    platform: str
    description_html: Optional[str] = Field(
        description=(
            "Exact editable description as returned by the store, or null when the store has "
            "none. Use it byte for byte as the write base."
        )
    )
    fetched_at: str


class StoreWriteReceipt(_Result):
    store_integration_id: str = Field(description="Store integration the write request targeted.")
    external_product_id: str = Field(description="Exact product ID echoed by AEKO.")
    audit_id: str = Field(description="AEKO audit row for reconciliation and aeko_revert_store_write.")
    platform: str
    status: Literal["success", "dry_run"]
    store_updated: bool = Field(
        description="True only for status success; dry_run made no live store change."
    )
    http_status: Optional[int] = None
    payload_sent: Optional[dict[str, Any]] = Field(
        default=None, description="Payload AEKO sent to the store, omitted when larger than 32 KiB."
    )
    payload_sent_omitted: bool = False
    admin_url: Optional[str] = Field(
        default=None,
        description="Store admin URL when AEKO supplies one. The current backend does not, so this is null.",
    )


class StoreWriteHistoryItem(_Result):
    id: str = Field(description="Audit ID.")
    store_integration_id: str
    platform: str
    external_product_id: str
    operation: str
    status: str
    error_code: Optional[str] = None
    error_message: Optional[str] = Field(
        default=None,
        description=(
            "Safe adapter-authored explanation. Stored upstream response and exception text "
            "is never returned."
        ),
    )
    revert_of_audit_id: Optional[str] = None
    created_at: str


class StoreWriteHistoryPage(_Result):
    items: list[StoreWriteHistoryItem]
    total: int
    limit: int
    offset: int
    next_offset: Optional[int] = Field(
        default=None, description="Offset of the next page, or null when no more rows are reported."
    )
