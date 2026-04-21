# AEKO MCP

MCP server for [AEKO](https://aeko-intelligence.com) — monitor and optimize how AI engines (ChatGPT, Claude, Gemini, Perplexity) recommend your products in international markets.

This repo ships the **Python MCP server** only. For the guided workflows (skills / slash commands like `/aeko-run-action`, `/aeko-brand-kit`) see **[`aeko-plugin`](https://github.com/AEKO-Intelligence/aeko-plugin)** — install both for the full experience.

## Connecting

The hosted AEKO MCP server is already running at `https://aeko-intelligence.com/mcp`. You don't need to host it yourself. Connect your client:

### Claude Desktop (recommended — pre-registered public client)

1. Settings → Connectors → **Add custom connector**
2. Server URL: `https://aeko-intelligence.com/mcp`
3. Expand **Advanced settings**
   - **Client ID**: `aeko-mcp-v1`
   - **Client Secret**: leave blank (public client, PKCE only)
4. Click **Connect** and complete browser OAuth

The pre-registered client routes the callback through `https://claude.ai/api/mcp/auth_callback`, which is reliable across Desktop's sandboxed runtime.

### Claude Code / Codex CLI

These use Dynamic Client Registration (RFC 7591) automatically — no client ID needed:

```bash
# Claude Code
claude mcp add --transport http aeko https://aeko-intelligence.com/mcp

# Codex
codex mcp add --transport http aeko https://aeko-intelligence.com/mcp
```

The client opens a browser, you sign in at AEKO, approve access — done. Tokens refresh automatically.

## Authentication

Browser OAuth 2.1 flow with PKCE. Two paths depending on client:

- **Pre-registered public client** (Claude Desktop custom connector, and any future tool that supports hosted callbacks) — paste `aeko-mcp-v1` into the connector's client-ID field. No secret.
- **Dynamic Client Registration** (Claude Code, Codex CLI, any generic MCP client with loopback) — client auto-registers with AEKO via RFC 7591. No manual configuration.

AEKO is the authorization server and resource server. Tokens are opaque (not JWTs) and persist in the `oauth_access_tokens` / `oauth_refresh_tokens` tables. OAuth discovery lives at `/.well-known/oauth-authorization-server` and `/.well-known/oauth-protected-resource`.

## Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AEKO_API_URL` | No | `https://aeko-backend.purplehill-6906b42f.koreacentral.azurecontainerapps.io` | API base URL |
| `AEKO_MCP_TRANSPORT` | No | `streamable-http` | Server transport to run from the CLI entrypoint |
| `AEKO_MCP_HOST` | No | — | Host for `streamable-http` mode |
| `AEKO_MCP_PORT` | No | — | Port for `streamable-http` mode |
| `AEKO_MCP_MOUNT_PATH` | No | — | Optional mount path override when running HTTP mode |
| `AEKO_MCP_STREAMABLE_HTTP_PATH` | No | `/` | Path served by the streamable HTTP app. Defaults to `/` so the embedding ASGI app's own mount prefix (e.g. `app.mount("/mcp", create_streamable_http_app())`) is not doubled. Set to `/mcp` only when running the HTTP server standalone. |
| `AEKO_MCP_STATELESS_HTTP` | No | `true` | Run streamable HTTP in stateless mode |
| `AEKO_MCP_JSON_RESPONSE` | No | `true` | Prefer JSON HTTP responses over SSE chunks |

## Available Tools

AEKO MCP exposes tools covering visibility metrics, suggestions, content generation, local file operations, and store-write actions.

- [`aeko_mcp/tools/`](aeko_mcp/tools/) — one module per tool group. Each tool is registered with `@mcp.tool()` and its docstring is shown to the AI client at runtime.

Current groups include: `visibility`, `content`, `product`, `suggestions` (+ `suggestions_v2` for the categorized brief format), `research`, `generate`, `report`, `citability`, `aeko_score`, `sources`, `store_write`, `pdp`, `action_plan`, and `brand_kit`.

All tools carry MCP `ToolAnnotations` (`readOnlyHint`, `destructiveHint`, `openWorldHint`) so clients can offer per-tool approval policy (e.g. "always allow" for read-only GETs, approval-per-call for writes).

Inside Claude Code or Codex, run the `list tools` equivalent to see the live set with descriptions.

## Self-Hosting (optional)

```bash
pip install aeko-mcp
aeko-mcp --transport streamable-http --host 0.0.0.0 --port 8000
```

Clients can then connect to `http://localhost:8000/mcp`. Note that self-hosted instances do not have access to AEKO's backend data — they're useful for local development or forking.

## Embedding in another ASGI app

```python
from aeko_mcp.server import create_streamable_http_app, mcp_lifespan

app.mount("/mcp", create_streamable_http_app(issuer_url="https://your-host.com"))
# And add mcp_lifespan() to the host app's lifespan manager.
```

This is how the production AEKO backend embeds the MCP server alongside its REST API.

## License

MIT
