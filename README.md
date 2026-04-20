# AEKO MCP

MCP server for [AEKO](https://aeko-intelligence.com) — monitor and optimize how AI engines (ChatGPT, Claude, Gemini, Perplexity) recommend your products in international markets.

## Quick Start

### Claude Code

```bash
# Add the marketplace
/plugin marketplace add AEKO-Intelligence/aeko-mcp

# Install the plugin
/plugin install aeko-mcp@AEKO-Intelligence
```

The bundled plugin now connects to the hosted AEKO MCP endpoint:
- `https://aeko-intelligence.com/mcp`

After installing or updating the plugin:
- restart Claude Code or run `/reload-plugins`
- open `/mcp`
- choose `aeko`
- authenticate in the browser when prompted

### Claude Desktop

Claude Desktop supports the same plugin marketplace as Claude Code, so the install flow below gives you both the AEKO skills and the hosted MCP in one go.

1. Open Claude Desktop → **Settings → Plugins**
2. Click **Browse plugins → Add marketplace**
3. Paste the GitHub repo: `AEKO-Intelligence/aeko-mcp`
4. From the marketplace, install **aeko-mcp**
5. Once installed, click **Manage → Connectors**
6. Find **AEKO** in the list and click **Connect**
7. Complete the browser OAuth flow → done

After the first connect, AEKO tools and skills are available in any Claude Desktop chat. Re-authenticate from the same Connectors panel if the session ever expires.

### Codex Desktop / Codex CLI

Preferred:

```bash
codex mcp add --transport http aeko https://aeko-intelligence.com/mcp
```

Then authenticate through the MCP client/browser flow.

This repo also includes a Codex plugin manifest at `.codex-plugin/plugin.json`.
For repo-local discovery, it also includes `.agents/plugins/marketplace.json`.

### Remote HTTP Server

The same package can also run as a remote streamable HTTP MCP server:

```bash
pip install aeko-mcp

aeko-mcp \
  --transport streamable-http \
  --host 0.0.0.0 \
  --port 8000
```

Clients can then connect to `http://localhost:8000/mcp`.

## Self-Hosting

```bash
pip install aeko-mcp
aeko-mcp --transport streamable-http --host 0.0.0.0 --port 8000
```

### Add to Codex Manually

For the recommended hosted setup:

```bash
codex mcp add --transport http aeko https://aeko-intelligence.com/mcp
```

### Codex Plugin Packaging

This repo now ships the Codex plugin pieces needed for local distribution:

- `.codex-plugin/plugin.json`
- `.codex-plugin/.mcp.json`
- `.codex-plugin/skills/`
- `.agents/plugins/marketplace.json`

The marketplace entry points at the repo root as a local plugin source, so the same checkout can be opened directly in Codex desktop and treated as a plugin-bearing workspace.

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

AEKO MCP exposes a growing set of tools covering visibility metrics, suggestions,
content generation, local file operations, and store-write actions. Rather than
maintain an always-drifting table here, see the source directory:

- [`aeko_mcp/tools/`](aeko_mcp/tools/) — one module per tool group. Each
  tool is registered with `@mcp.tool()` and its docstring is shown to the
  AI client at runtime.

Current groups include: `visibility`, `content`, `product`, `suggestions`
(+ `suggestions_v2` for the categorized brief format), `research`, `generate`,
`report`, `citability`, `aeko_score`, `campaigns`, `content_recommendations`,
`store_write`, `pdp`, `action_plan`, and `brand_kit`.

The `action_plan` and `brand_kit` groups (v0.3.0+) power the Plan.md /
action-item execution loop — `aeko_get_action_plan`, `aeko_complete_action_item`,
`aeko_get_brand_kit`, `aeko_update_brand_kit`. Consumed by the
`aeko-run-action` and `aeko-brand-kit` skills.

Inside Claude Code or Codex, run the `list tools` equivalent to see the
live set with descriptions.

## Skills

Skills are guided workflows that combine AEKO data with content generation.
Use them as slash commands in Claude Code or `/skill` invocations in Codex.

- [`skills/`](skills/) — Claude Code skills
- [`.codex-plugin/skills/`](.codex-plugin/skills/) — Codex skills (kept in
  parity with the Claude set)

Currently available skills (Claude unless noted):

| Skill | Purpose |
|-------|---------|
| `/aeo-audit` | Audit any URL for AEO readiness |
| `/aeo-audit-local` | Batch citability audit of a local directory |
| `/aeo-optimize` | Full optimize: audit → generate → preview |
| `/generate-jsonld` | Production-ready JSON-LD for products |
| `/generate-faq` | AI-query-matched FAQ + FAQPage JSON-LD |
| `/create-blog-article` | Blog content tuned for AI visibility |
| `/create-social-content` | Social posts from AEKO data |
| `/create-marketing-materials` | Marketing collateral with AEKO insights |
| `/create-visibility-report` | Full AI visibility report |
| `/competitive-research` | AI visibility gap analysis vs a competitor |
| `/aeko-action-center` | Review and route categorized suggestions |
| `/aeko-update-pdp` | Execute a PDP update suggestion end-to-end |
| `/aeko-fix-store-level` | Execute a store-level (llms.txt, robots.txt, schema) fix |
| `/aeko-create-own-content` | Draft own-site content from a v2 brief |
| `/aeko-create-external-content` | Draft external-media content from a v2 brief |
| `/aeko-draft-from-campaign` | Draft content from a campaign recommendation |

### Example usage

```
/aeo-optimize https://mystore.com/product-page
```

Claude will fetch your AEKO data, generate optimized content (description, JSON-LD, FAQ), and open a browser preview showing the before/after comparison.

## Codex Support

The shared MCP server in `aeko_mcp/` is portable across Claude and Codex.

- Claude packaging lives in `.claude-plugin/`
- Codex packaging lives in `.codex-plugin/`
- Claude skills remain under `skills/`
- Codex skills live under `.codex-plugin/skills/`
- Repo-local Codex marketplace metadata lives in `.agents/plugins/marketplace.json`

The two skill directories are kept in parity — both sides see the same
skill set. See [`.codex-plugin/skills/`](.codex-plugin/skills/) for the
current list.

For end-user guides, see the [AEKO User Guide](https://aeko-intelligence.com/en/docs).

## Authentication

Browser OAuth 2.1 flow — nothing to copy or paste.

1. Sign up at [aeko-intelligence.com](https://aeko-intelligence.com).
2. Add AEKO as a remote MCP server in your client:
   ```bash
   claude mcp add --transport http aeko https://aeko-intelligence.com/mcp
   # or
   codex mcp add --transport http aeko https://aeko-intelligence.com/mcp
   ```
   For Claude Desktop, add `https://aeko-intelligence.com/mcp` as a custom connector from `Customize > Connectors`.
3. Your client opens a browser to AEKO, you sign in, approve access — done.
   The MCP client registers itself via [RFC 7591 Dynamic Client Registration](https://www.rfc-editor.org/rfc/rfc7591),
   obtains an access token via [OAuth 2.1](https://datatracker.ietf.org/doc/html/draft-ietf-oauth-v2-1) + PKCE,
   and refreshes it automatically.

## Hosting

`aeko-mcp` is designed for remote streamable HTTP MCP hosts.

If you want to embed AEKO MCP inside another ASGI app, import these helpers:

```python
from aeko_mcp.server import create_streamable_http_app, mcp_lifespan
```

Mount the app at your preferred path and run `mcp_lifespan()` in the host app lifespan.

## License

MIT
