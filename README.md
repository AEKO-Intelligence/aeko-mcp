# AEKO MCP

MCP server for [AEKO](https://aeko-intelligence.com) — monitor and optimize how AI engines (ChatGPT, Claude, Gemini, Perplexity) recommend your products in international markets.

This repo ships the **Python MCP server** only. For the guided workflows (skills / slash commands like `/aeko-run-action`) see **[`aeko-plugin`](https://github.com/AEKO-Intelligence/aeko-plugin)** — install both for the full experience.

## Connecting

The hosted AEKO MCP server is already running at `https://aeko-intelligence.com/mcp`. You don't need to host it yourself. Connect your client:

### Claude Desktop (recommended)

1. Settings → Connectors → **Add custom connector**
2. Server URL: `https://aeko-intelligence.com/mcp`
3. Click **Connect** and complete browser OAuth

Leave **Advanced settings** collapsed — the OAuth Client ID and Secret fields are optional
and should stay empty. Desktop self-registers through Dynamic Client Registration like
every other client.

### Claude Code / Codex CLI / Gemini CLI

Same Dynamic Client Registration, from the terminal:

```bash
# Claude Code
claude mcp add --transport http aeko https://aeko-intelligence.com/mcp

# Codex
codex mcp add --transport http aeko https://aeko-intelligence.com/mcp

# Gemini CLI
gemini mcp add --transport http aeko https://aeko-intelligence.com/mcp
```

The client opens a browser, you sign in at AEKO, approve access — done. Tokens refresh automatically.

If you prefer to edit Gemini's `~/.gemini/settings.json` directly, the equivalent block is:

```json
{
  "mcpServers": {
    "aeko": {
      "httpUrl": "https://aeko-intelligence.com/mcp"
    }
  }
}
```

Recent Gemini CLI builds also accept the consolidated `url` form with `"type": "http"` (see google-gemini/gemini-cli#13762). Either works. After editing, run `/mcp reload` inside Gemini CLI.

## Authentication

Browser OAuth 2.1 flow with PKCE. Two paths depending on client:

- **Dynamic Client Registration (the normal path — all clients)** — the client auto-registers
  with AEKO via RFC 7591 and needs no manual configuration. `_validate_redirect_uri` accepts
  any `https://` callback as well as loopback, so hosted-callback clients such as Claude
  Desktop register the same way terminal clients do. Gemini CLI uses its built-in
  `dynamic_discovery` provider, which reads `/.well-known/oauth-authorization-server` on
  first connect.
- **Pre-registered public client `aeko-mcp-v1` (fallback only)** — still served for any host
  that cannot do DCR. Do not put it in user-facing setup instructions: it adds a step, and
  the connector UI marks the field optional.

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

AEKO MCP exposes 96 tools covering setup, visibility metrics, citability, tracked-prompt angles, owner-associated source evidence, ranked content ideas and handoffs, views, content variations, media uploads, customer review contexts, saved memories, analytics, GA4, OpenAI Ads operations and pacing rules, and store-write actions.

- [`aeko_mcp/tools/`](aeko_mcp/tools/) — one module per tool group. Each tool is registered with `@mcp.tool()` and its docstring is shown to the AI client at runtime.

Current groups: `visibility`, `research`, `sources`, `content_ideas`, `store_write`, `action_plan`, `own_content`, `media_upload`, `content_variation`, `reviews`, `contexts`, `marketing`, `analytics`, `ga4`, `views`, and `setup`.

The `sources` and `content_ideas` groups support the Content dashboard's AI workflow (Pro+):

- `aeko_fetch_source_content(domain_id, source_id)` — fetch stored page evidence only after the backend verifies both domain ownership and tracked-prompt association.
- `aeko_list_content_ideas(domain_id, ...)` — list ranked ideas with filters, facets, evidence references, and honest cursor pagination.
- `aeko_start_content_idea(domain_id, fingerprint, window)` — start or reopen an idea and return the backend-authored `/aeko-create-content` handoff command.
- `aeko_dismiss_content_idea(domain_id, fingerprint, window)` — dismiss an idea from the rolling set; starting it again reverses the dismissal.
- `aeko_get_content_idea_handoff(handoff_id)` — read the full server snapshot for one rule-based content idea. Reopening keeps the ID but refreshes its evidence before the next run.

The `action_plan` group includes a permanent, token-fenced execution claim for ActionItem executors:

- `aeko_claim_action_item(item_id)` — create an exclusive execution claim for one owned `ready` item and return its unique `claim_id`. The item stays `ready`; a concurrent executor receives 409 and must stop.
- `aeko_release_action_item(item_id, claim_id=...)` — release only the matching uncompleted claim when no store mutation occurred. Claims do not expire automatically; forced recovery requires explicit confirmation that no execution or mutation is active.
- `aeko_update_product_page(...)` — submit description, JSON-LD, tags, and SEO meta as one claim-fenced product patch with one audit/revert boundary.

The `reviews` group surfaces **Context Reviews** — classified customer reviews from connected Crema / Judge.me platforms — so content drafts can be grounded in real customer-state, concern, product-experience, and felt-effect details instead of invented copy (Pro+):

- `aeko_list_review_integrations(domain_id)` — list a domain's connected review platforms (resolve the `integration_id`).
- `aeko_list_review_products(integration_id)` — products under an integration with their contextual-review counts (which products have stories to draw on).
- `aeko_get_product_reviews(integration_id, external_product_ref, min_context_score=60, limit=10)` — a product's TOP contextual reviews (score ≥ 60, strongest first) with extracted `문제`, `고객 상태`, `최근 고민`, `제품 경험`, and `느낀 효과`; this is what the create-content flow calls to ground a draft.

The `contexts` group surfaces curated **AEKO Context memories** saved in the Context tab:

- `aeko_list_contexts(domain_id, scope=None, kind=None)` — list saved curated context memories for a domain, optionally filtered by scope (`brand`, `product`, `category`) or free-text kind (for example `브랜드 충성도`, `재구매`, `피부 고민`, `content angle`).

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
