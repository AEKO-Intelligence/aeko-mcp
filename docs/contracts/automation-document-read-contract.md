# Authenticated accepted brand package reads

MCP 0.21.0 adds whole-package and Brand Wiki wrappers for the backend auto06 routes. Keep the
0.20.0 per-document tools for compatibility, but use the release-fenced reads below when work must
follow an accepted package snapshot.

| Tool | Backend request | Model-visible result |
| --- | --- | --- |
| `aeko_get_active_brand_package` | GET `/api/automations/brand-package?domain_id=…` | Active release for OAuth or the exact snapshot release for a run token; members page locally under 32 KiB |
| `aeko_get_brand_package_version` | GET `/api/automations/brand-package/versions/{version}?domain_id=…` | One exact release, with run tokens restricted to their pin |
| `aeko_read_brand_package_file` | Exact release GET, then exact member file GET | One 16 KiB UTF-8 chunk after package/member identity and digest checks |
| `aeko_get_brand_wiki_chapters` | GET `/api/automations/wiki/chapters?domain_id=…` | Fixed navigation registry; normal OAuth only because it is not run-snapshot data |
| `aeko_list_brand_wiki_pages` | GET `/api/automations/wiki/pages?domain_id=…` | Accepted page metadata and continuation offset, no bodies |
| `aeko_get_brand_wiki_page` | GET `/api/automations/wiki/pages/{id}?domain_id=…` | Authority, sources, scope, usage, and accepted version manifest; no body or history bytes |

Each request forwards one explicit tenant `domain_id`. The package-member reader accepts only an
exact `package_slug` returned by the release, then verifies release version/digest, member
document/version UUIDs, member digest, file path, and returned file identity. It never falls back
to the current head or a similarly named document. A plain FastAPI 404 from an older deployment
becomes an actionable missing-capability error; typed errors such as
`BRAND_PACKAGE_NOT_INITIALIZED`, ownership failures, and run-scope denial remain intact.

Authentication grants access only. A caller must page through the accepted manifest, select the
canonical member, and read every required instruction, eval, wiki, and support file. It must keep
the package version/digest pinned across chunks. The MCP server does not apply the instructions or
execute evals.

Normal OAuth reads the tenant's active package. A hosted run credential reads the immutable
package and wiki versions recorded in that run even if the active head moves later. Run tokens
cannot list history, export ZIPs, import, or read the non-snapshot chapter registry. These backend
checks are authoritative; read-only MCP annotations are descriptive.

MCP 0.20.0 adds read-only wrappers for the backend `auto04` document package API. Deploy the
backend migration and routes before making these tools available to customers. They do not
depend on a local checkout or ask an AI platform to read another machine's filesystem.

| Tool | Backend request | Model-visible result |
| --- | --- | --- |
| `aeko_list_brand_documents` | GET `/api/automations/documents?domain_id=…&kind=…` | Selected metadata, default/brand ownership, active/draft version, paginated up to 100 rows and 32 KiB encoded JSON |
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
Discovery stops at its encoded metadata-page byte limit and returns the exact next row offset.
The version manifest also has a 32 KiB encoded-response guard. Unexpected oversized backend
metadata fails before it can be returned to the model; valid package metadata and the maximum
64-file manifest fit this bound.

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
permissions. The accepted backend runtime materializes pinned support/wiki context for its
existing automation templates, but the MCP adapter does not provide the full Responses/MCP
runner, canonical routing for all customer-plugin commands, contextual chat, or GitHub App sync.
