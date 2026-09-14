# aeko-mcp — Agent Guide

Python MCP (Model Context Protocol) server bridging Claude and other AI assistants to the AEKO backend for AI engine optimization (AEO): brand visibility across ChatGPT/Claude/Gemini/Perplexity, AI-readiness audits, AEO-optimized content drafting, and store-write workflows (Cafe24, Shopify).

- **Version:** 0.24.0 (`pyproject.toml`) · **Framework:** FastMCP (mcp SDK >=1.11.0,<1.16.0), httpx, pydantic, Pillow
- **Hosted endpoint:** `https://aeko-intelligence.com/mcp` (clients connect here; no self-hosting needed)
- **Auth:** OAuth 2.1 + PKCE — Dynamic Client Registration (RFC 7591) for all clients including Claude Desktop (`_validate_redirect_uri` accepts hosted `https://` callbacks, not just loopback); pre-registered public client `aeko-mcp-v1` retained as a fallback only, and deliberately kept out of user-facing setup docs. Opaque bearer tokens (`aeko_ot1_`, 1h TTL) + 30-day refresh tokens.
- **Transport:** streamable-http, stateless, JSON responses by default (`aeko_mcp/server.py`)
- **Backend (prod default):** `https://aeko-backend.purplehill-6906b42f.koreacentral.azurecontainerapps.io` (override with `AEKO_API_URL`)

## Registered tool groups — 120 tools across 20 modules (`aeko_mcp/tools/`)

| Module | Tools | Covers |
|---|---|---|
| `visibility` | 5 | Domain setup, visibility summary, citability, domain info, list domains |
| `research` | 7 | Research prompts, tracked-prompt angles, quota, prompt detail, untrack |
| `store_write` | 12 | Store connect/sync, manual product inject, claim-fenced product writes, audit trail, revert |
| `action_plan` | 8 | Action items, technical items, atomic claim/release, create/dismiss/complete lifecycle |
| `fact_check` | 2 | Owner-scoped findings, exact source/Wiki references, current evidence freshness and decision history |
| `content_variation` | 5 | Save/publish/unpublish/list/update content variations |
| `own_content` | 1 | `aeko_list_own_content` |
| `media_upload` | 1 | `aeko_request_media_upload` |
| `reviews` | 7 | Review integrations/products, Context Reviews, suggested prompts |
| `contexts` | 11 | Curated AEKO Context memories, CRUD, opportunity/Focus workflows, metrics, translations |
| `marketing` | 30 | Contextual reviews, review injection, OpenAI Ads setup/discovery/compose/edit/report/optimize/state, pacing rules |
| `marketing_reporting` | 3 | Read-only OpenAI Ads account list, explicit-account product insight pages, stored conversion reports ([contract](docs/contracts/ads-reporting-read-contract.md)) |
| `analytics` | 3 | SOV, drift, Measure |
| `ga4` | 4 | GA4 status, property selection, sync |
| `views` | 3 | Prompt view list/create/add prompts |
| `setup` | 4 | Starter prompts and account-market read/replace setup |
| `sources` | 1 | Owner-associated cited-source content |
| `content_ideas` | 4 | Ranked content ideas, start/dismiss lifecycle, server-snapshotted handoffs |
| `automation_documents` | 3 | Brand skill/eval discovery, exact-version manifest, byte-bounded file reads; requires backend auto04 package routes |
| `brand_packages` | 6 | Active/exact whole-package discovery, digest-fenced canonical-member reads, and bounded Brand Wiki navigation/detail; requires backend auto06 routes |

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate && pip install -e .
aeko-mcp --transport streamable-http --host 0.0.0.0 --port 8000
```

Client setup: `claude mcp add --transport http aeko https://aeko-intelligence.com/mcp` (codex/gemini equivalents in README). Key env vars: `AEKO_API_URL`, `AEKO_MCP_TRANSPORT`, `AEKO_MCP_HOST`/`PORT`, `AEKO_MCP_STREAMABLE_HTTP_PATH` (default `/`), `AEKO_MCP_STATELESS_HTTP` (default true), `AEKO_MCP_JSON_RESPONSE` (default true).

## Where to look

- `README.md` — connection, auth, config table, embedding in another ASGI app
- `docs/aeko-mcp-overview.md` — architecture + token flow; older narrative sections may lag the registered tool surface, so trust `aeko_mcp/tools/*.py` for tool details
- `docs/contracts/` — cross-repo contracts (e.g. `action-item-contract.md`)
- `CHANGELOG.md` — release history; backend pins this package by git tag

---
Workspace catalog: `/Users/seanhan/aeko-intelligence/AGENTS.md` · Canonical docs: `/Users/seanhan/aeko-intelligence/aeko-agents/docs/`
