# AEKO MCP Server

MCP server for [AEKO](https://aeko.ai) — monitor and optimize how AI engines (ChatGPT, Claude, Gemini, Perplexity) recommend your products in international markets.

## Quick Start (Claude Code Plugin)

```bash
# Add the marketplace
/plugin marketplace add panomix/aeko-mcp-server

# Install the plugin
/plugin install aeko-mcp-server@panomix
```

Then set your API key:

```bash
export AEKO_API_KEY="your-api-key"
```

## Manual Setup

### Option A: pip/uv install

```bash
pip install aeko-mcp-server
```

Or with uv:

```bash
uv pip install aeko-mcp-server
```

### Option B: Clone and run

```bash
git clone https://github.com/panomix/aeko-mcp-server.git
cd aeko-mcp-server
pip install -e .
python -m aeko_mcp
```

### Add to Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "aeko": {
      "command": "python",
      "args": ["-m", "aeko_mcp"],
      "env": {
        "AEKO_API_KEY": "your-api-key",
        "AEKO_API_URL": "https://api.aeko.ai"
      }
    }
  }
}
```

## Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AEKO_API_KEY` | Yes | — | Your AEKO API key |
| `AEKO_API_URL` | No | `https://api.aeko.ai` | API base URL |

## Available Tools

| Tool | Description |
|------|-------------|
| `aeko_get_visibility_summary` | Brand visibility metrics across AI engines |
| `aeko_get_domain_info` | Domain details and AI-readiness status |
| `aeko_get_page_analysis` | AI-readiness analysis for store pages |
| `aeko_get_cited_sources` | Pages cited by AI engines as sources |
| `aeko_get_product_analysis` | Competitive analysis for a product |
| `aeko_get_suggestions` | Prioritized optimization suggestions |
| `aeko_search_research_prompts` | Search research prompt library |
| `aeko_get_tracked_prompts` | List actively tracked prompts |

## Getting an API Key

1. Sign up at [aeko.ai](https://aeko.ai)
2. Go to **Settings** > **API Keys**
3. Create a new API key and copy it

## License

MIT
