# Structured results for the /update-pdp path tools

Status: unreleased. This contract covers exactly six tools. Every other tool keeps its existing
text output and error strings.

| Tool | Result model | Control fields |
| --- | --- | --- |
| `aeko_get_active_brand_package` | `BrandPackagePage` | `id`, `version`, `digest`, `members[]`, `total_members`, `next_offset` |
| `aeko_get_brand_package_version` | `BrandPackagePage` | Same; the version never falls back to the head |
| `aeko_read_brand_package_file` | `BrandPackageFileChunk` | `package_id`, `package_version`, `package_digest`, `member`, `content`, `next_offset`, `complete` |
| `aeko_get_product_description` | `ProductDescription` | `integration_id`, `external_product_id`, `platform`, `description_html`, `fetched_at` |
| `aeko_update_product_page` | `StoreWriteReceipt` | `store_integration_id`, `external_product_id`, `audit_id`, `status`, `store_updated` |
| `aeko_list_store_writes` | `StoreWriteHistoryPage` | `items[].id`, `items[].store_integration_id`, `total`, `limit`, `offset`, `next_offset` |

## Wire format

The models are concrete runtime Pydantic classes registered with `structured_output=True`, so
`tools/list` publishes a field-level `outputSchema` and a successful `tools/call` returns
`structuredContent`. FastMCP also returns the same object as indented JSON text for clients that
ignore structured content.

**Text-format change:** these six tools previously returned Markdown (store tools) or compact
JSON strings (package tools). Their text is now FastMCP's JSON rendering of the result, and direct
Python callers receive model instances. The package page bound (32 KiB) is measured on that
indented text, so a page can hold fewer members than before; paging still loses no member.

## Success semantics

- **Package pins.** Existing validation is unchanged: tenant `domain_id` forwarding, UUID/digest/slug
  checks, member counts, exact release version, member version/digest revalidation before every
  file chunk, UTF-8 boundaries, and byte limits.
- **Description.** `description_html` is the exact store value. A store without a description
  returns `null`, not an empty or generated string. The response must echo the requested
  integration and product; a different identity is an error.
- **Write receipt.** The tool sends one POST with the same body as before and never retries.
  - Success requires a UUID `audit_id`, the exact requested `external_product_id`, and `status`
    `success` or `dry_run`. A reported HTTP status, when present, must be 2xx. `store_updated` is
    true only for `success`; `dry_run` made no live store change.
  - `store_integration_id` is the integration the request targeted.
  - `payload_sent` is returned when its compact JSON is at most 32 KiB. Otherwise it is `null`
    and `payload_sent_omitted` is true.
- **Admin URL.** The backend `ProductUpdateResponse` has no admin URL. `admin_url` is optional
  and is `null` today. It is populated only if AEKO later supplies an `https://` value; the
  adapter never constructs one.
- **History.** Each item keeps the backend `store_integration_id`, product, operation, status,
  error code and `revert_of_audit_id`. Backend `error_message` can contain an upstream response
  body or transport exception, so the adapter replaces it with an authored explanation and never
  returns the stored raw text. `next_offset` is `offset + len(items)` while that is below `total`,
  otherwise `null`; an empty page before `total` is treated as a malformed response.

## Errors

After a migrated function begins, a failure is raised, so MCP marks the result `isError=true` and
returns no `structuredContent`. The text is `Error executing tool <name>: ` followed by one JSON
object:

```json
{"schema":"aeko.error.v1","code":"ACTION_ITEM_WRITE_INDETERMINATE","message":"…","http_status":409,"audit_id":null,"mutation_state":"unknown"}
```

Argument or schema errors rejected by the MCP SDK before the function begins are also
`isError=true`, but they use the SDK's own text and do not carry `aeko.error.v1`.

- **`message`** is written by aeko-mcp (at most 300 characters). Backend detail messages, response
  bodies, exception text and credentials are never forwarded.
- **`code`**:
  - a typed backend `detail.code` when present;
  - otherwise an adapter code:
    - request/argument problems: `INVALID_ARGUMENT`, `CAPABILITY_UNAVAILABLE`,
      `IMAGE_UPLOAD_FAILED`;
    - backend data problems: `INVALID_BACKEND_RESPONSE`, `PRODUCT_IDENTITY_MISMATCH`;
    - package pin problems: `PACKAGE_DIGEST_MISMATCH`, `PACKAGE_VERSION_MISMATCH`,
      `PACKAGE_MEMBER_NOT_FOUND`, `PACKAGE_MEMBER_DUPLICATE`, `PACKAGE_MEMBER_PIN_MISMATCH`,
      `PACKAGE_FILE_TOO_LARGE`, `PACKAGE_METADATA_TOO_LARGE`;
    - write result problems: `INVALID_WRITE_RECEIPT`, `WRITE_RESULT_UNKNOWN`;
    - transport problems: `BACKEND_UNREACHABLE`, `BACKEND_TIMEOUT`, `BACKEND_UNAVAILABLE`;
    - HTTP status classes: `BAD_REQUEST`, `AUTHENTICATION_FAILED`, `ACCESS_DENIED`, `NOT_FOUND`,
      `CONFLICT`, `VALIDATION_FAILED`, `RATE_LIMITED`, `BACKEND_ERROR`.
- **`audit_id`** is kept whenever the backend reported one: a failed platform write, or a malformed
  receipt that still contains a UUID.

### `mutation_state`

| State | Meaning | Produced by |
| --- | --- | --- |
| `not_attempted` | No store-product write was sent | All read tools; local validation, including an empty patch (formerly a successful "Nothing to update" text); local image upload failure; connection not established |
| `rejected` | AEKO definitively refused this request | Pre-write backend codes (`ACTION_ITEM_CLAIM_REQUIRED`, `…_STATUS_CONFLICT`, `…_NOT_STORE_WRITABLE`, `…_PAYLOAD_MISMATCH`, `…_TARGET_MISMATCH`, `SUBSCRIPTION_INACTIVE`, `TIER_REQUIRED`, `STORE_PRODUCT_NOT_FOUND`, `STORE_SNAPSHOT_FAILED`); untyped 400/401/403/404/422/429; a platform 4xx with a valid audit UUID, except `NETWORK_ERROR`/`PLATFORM_ERROR` |
| `unknown` | The write may have happened | `ACTION_ITEM_WRITE_INDETERMINATE`, `ACTION_ITEM_WRITE_PAYLOAD_CONFLICT`, `NETWORK_ERROR`, `PLATFORM_ERROR`; a platform 5xx with an audit ID; untyped 409, 5xx or other status; timeout after sending; empty, non-JSON, contradictory, failed-status or mismatched success receipt |

`rejected` describes only this request. A claim-level conflict can still mean that an earlier write
on the same claim has an unknown result, so those codes are classified `unknown`. Image upload is
preprocessing: it can already have created a media object even when the store-product mutation is
`not_attempted`.

The backend reports platform 401/402/403 failures as 502. That makes them `unknown` here, even
though the backend itself releases the claim fence.

**Recovery for `unknown`:** never resubmit and never release the claim automatically.
1. Read `aeko_get_product_description` and compare its bytes with the saved approved result
   and the pre-write backup.
2. Page `aeko_list_store_writes`, matching `store_integration_id`, `external_product_id`, and
   `audit_id` when one was returned.

## Client and legacy behavior

`AekoClient` raises `AekoAPIError(RuntimeError)` with `http_status`, `code`, `audit_id` and
`request_sent`. `str(error)` is unchanged. Text tools still print `RuntimeError: …` through
`legacy_error_name`, and Brand Wiki reads keep their messages.

Tool modules keep runtime annotations for MCP 1.11/1.12. The suite was run on MCP 1.11.0, 1.12.4
and 1.15.0; the ambient 1.27.0 environment is outside the supported range and is not a
compatibility claim.

## Remaining plugin alignment

Update `aeko-update-pdp` before deploying this changed MCP contract, and coordinate the plugin
and MCP releases:

- **Structured fields:** read `description_html` from the structured result or parse the JSON text
  fallback when the client does not expose structured content. Handle `null` explicitly.
- **Receipt:** read `audit_id` from the receipt and treat `admin_url` as optional (currently
  `null`). Treat `dry_run` as no live change.
- **Failures:** branch on `mutation_state`, and never retry `unknown`.
- **Reconciliation:** match history by `store_integration_id`.
- **Empty patch:** expect an error instead of "Nothing to update".
