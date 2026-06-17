# aeko-mcp — Agent Guide

Python MCP (Model Context Protocol) server bridging Claude and other AI assistants to the AEKO backend for AI engine optimization (AEO): brand visibility across ChatGPT/Claude/Gemini/Perplexity, AI-readiness audits, AEO-optimized content drafting, and store-write workflows (Cafe24, Shopify).

- **Version:** 0.11.0 (`pyproject.toml`) · **Framework:** FastMCP (mcp SDK >=1.11.0,<1.16.0), httpx, pydantic, Pillow
- **Hosted endpoint:** `https://aeko-intelligence.com/mcp` (clients connect here; no self-hosting needed)
- **Auth:** OAuth 2.1 + PKCE — Dynamic Client Registration (RFC 7591) for Claude Code/Codex/Gemini CLI; pre-registered public client `aeko-mcp-v1` for Claude Desktop. Opaque bearer tokens (`aeko_ot1_`, 1h TTL) + 30-day refresh tokens.
- **Transport:** streamable-http, stateless, JSON responses by default (`aeko_mcp/server.py`)
- **Backend (prod default):** `https://aeko-backend.purplehill-6906b42f.koreacentral.azurecontainerapps.io` (override with `AEKO_API_URL`)

## Registered tool groups — 32 tools across 11 modules (`aeko_mcp/tools/`)

| Module | Tools | Covers |
|---|---|---|
| `visibility` | 3 | Visibility summary, domain info, list domains |
| `research` | 6 | Research prompts, tracked-prompt forensics, resolve prompts by text |
| `aeko_score` | 1 | AI-readiness score |
| `store_write` | 7 | Product description/meta/tags writes, integrations, audit trail, revert |
| `action_plan` | 4 | Action items, technical items, completion |
| `content_variation` | 4 | Save/publish/list/update content variations |
| `crawl` | 1 | `aeko_crawl_url` |
| `own_content` | 1 | `aeko_list_own_content` |
| `media_upload` | 1 | `aeko_request_media_upload` |
| `reviews` | 3 | Context Reviews (Crema/Judge.me), read-only |
| `contexts` | 1 | Curated AEKO Context memories, read-only |

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate && pip install -e .
aeko-mcp --transport streamable-http --host 0.0.0.0 --port 8000
```

Client setup: `claude mcp add --transport http aeko https://aeko-intelligence.com/mcp` (codex/gemini equivalents in README). Key env vars: `AEKO_API_URL`, `AEKO_MCP_TRANSPORT`, `AEKO_MCP_HOST`/`PORT`, `AEKO_MCP_STREAMABLE_HTTP_PATH` (default `/`), `AEKO_MCP_STATELESS_HTTP` (default true), `AEKO_MCP_JSON_RESPONSE` (default true).

## Where to look

- `README.md` — connection, auth, config table, embedding in another ASGI app
- `docs/aeko-mcp-overview.md` — architecture + token flow (**stale**: written at v0.5.0/22 tools; trust this file and the code over it)
- `docs/contracts/` — cross-repo contracts (e.g. `action-item-contract.md`)
- `CHANGELOG.md` — release history; backend pins this package by git tag

---
Workspace catalog: `/Users/seanhan/aeko-intelligence/AGENTS.md` · Canonical docs: `/Users/seanhan/aeko-intelligence/aeko-agents/docs/`
