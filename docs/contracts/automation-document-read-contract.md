# Authenticated brand package reads

MCP 0.20.0 adds read-only wrappers for the backend `auto04` document package API. Deploy the
backend migration and routes before making these tools available to customers. They do not
depend on a local checkout or ask an AI platform to read another machine's filesystem.

| Tool | Backend request | Model-visible result |
| --- | --- | --- |
| `aeko_list_brand_documents` | GET `/api/automations/documents?domain_id=…&kind=…` | Selected metadata, default/brand ownership, active/draft version, paginated up to 100 rows |
| `aeko_get_document_package` | GET `/api/automations/documents/{id}/versions/{version}?domain_id=…` | Version ID/digest and file manifest; no body or arbitrary metadata |
| `aeko_read_document_file` | GET `/api/automations/documents/{id}/versions/{version}/files?domain_id=…&path=…` | One UTF-8 chunk, default 8 KiB, maximum 16 KiB, with byte continuation offset |

Version is the positive integer revision number from the document list. The package/file
response retains the immutable version UUID and digest. A draft is not implicitly active.
Read every required instruction before execution; use continuation offsets unchanged and
keep the version/digest pinned. Reference retrieval should remain selective.

File paths are query values and must match stored package entries; no local file is opened.
UUID validation prevents path interpolation from redirecting a request. The backend applies
canonical package path rules, visibility, entitlement and file-size limits. The wrapper checks
returned document/version/path identity, caps file size and refuses mid-codepoint offsets.
JSON escaping and the response envelope add wire bytes beyond the content chunk budget.

Authentication is forwarded through the existing request ContextVar. Normal clients use
their own OAuth session. A hosted run uses the narrow run credential, with backend request
authorization restricting route, method, brand and scope. MCP annotations describe read
behavior; they do not enforce permissions. No token appears in returned package data.

The backend's single-version response includes raw/projected text but only support-file
metadata. MCP omits that text from its manifest output. The file endpoint returns one full
bounded file to MCP, which slices it before returning to the model. No whole package or
unbounded version history enters a tool response. Discovery currently obtains the backend
document list before paginating locally; backend pagination can replace this when available.

This is retrieval, not automated loading/activation. The caller still composes the saved job
prompt with the selected brand skills/evals, applies those evals, and respects account write
permissions. AEKO's current hosted worker ignores support files; the manifest reports this
explicitly. Exporting instructions does not implement GitHub synchronization or an updater.
