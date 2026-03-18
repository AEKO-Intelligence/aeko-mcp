# AEKO MCP

MCP server for [AEKO](https://aeko-intelligence.com) — monitor and optimize how AI engines (ChatGPT, Claude, Gemini, Perplexity) recommend your products in international markets.

## Quick Start (Claude Code Plugin)

```bash
# Add the marketplace
/plugin marketplace add AEKO-Intelligence/aeko-mcp

# Install the plugin
/plugin install aeko-mcp@AEKO-Intelligence
```

Then set your API key:

```bash
export AEKO_API_KEY="your-api-key"
```

## Manual Setup

### Option A: pip/uv install

```bash
pip install aeko-mcp
```

Or with uv:

```bash
uv pip install aeko-mcp
```

### Option B: Clone and run

```bash
git clone https://github.com/AEKO-Intelligence/aeko-mcp.git
cd aeko-mcp
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
        "AEKO_API_URL": "https://aeko-backend.purplehill-6906b42f.koreacentral.azurecontainerapps.io"
      }
    }
  }
}
```

## Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AEKO_API_KEY` | Yes | — | Your AEKO API key |
| `AEKO_API_URL` | No | `https://aeko-backend.purplehill-6906b42f.koreacentral.azurecontainerapps.io` | API base URL |
| `AEKO_CONTENT_DIR` | No | — | Default directory for local content file scanning/reading |

## Available Tools

| Tool | Description |
|------|-------------|
| `aeko_get_visibility_summary` | Brand visibility metrics across AI engines |
| `aeko_get_domain_info` | Domain details and AI-readiness status |
| `aeko_get_page_analysis` | AI-readiness analysis for store pages |
| `aeko_get_cited_sources` | Pages cited by AI engines as sources |
| `aeko_get_product_analysis` | Competitive analysis for a product |
| `aeko_get_suggestions` | Prioritized optimization suggestions |
| `aeko_complete_suggestion` | Mark a suggestion as completed |
| `aeko_search_research_prompts` | Search research prompt library |
| `aeko_get_tracked_prompts` | List actively tracked prompts |
| `aeko_preview_optimized_page` | Generate HTML preview comparing original vs optimized content |
| `aeko_prepare_llms_txt` | Generate llms.txt content for AI crawler access |
| `aeko_prepare_robots_txt_fix` | Generate robots.txt fixes for AI crawlers |
| `aeko_prepare_json_ld` | Generate JSON-LD structured data for products |
| `aeko_list_product_images` | List product images in a directory |
| `aeko_read_product_image` | Read and return a product image |
| `aeko_save_content` | Save generated content to a file |
| `aeko_scan_content_directory` | Scan a directory for content files (HTML, MD, TXT, etc.) |
| `aeko_read_content_file` | Read and extract text from a local content file |
| `aeko_audit_content_file` | Read a local file and score it for AI citability |

## Skills

Skills are guided workflows that combine AEKO data with content generation. Use them as slash commands in Claude Code.

| Skill | Command | Description |
|-------|---------|-------------|
| AEO Audit | `/aeo-audit` | Comprehensive AEO readiness audit for any URL |
| AEO Optimize | `/aeo-optimize` | Full optimization workflow: audit → generate → preview |
| Generate JSON-LD | `/generate-jsonld` | Production-ready structured data for products |
| Generate FAQ | `/generate-faq` | AI-query-matched FAQ content with schema markup |
| Create Blog Article | `/create-blog-article` | Generate blog content optimized for AI visibility |
| Create Social Content | `/create-social-content` | Generate social media content from AEKO data |
| Create Marketing Materials | `/create-marketing-materials` | Generate marketing collateral using AEKO insights |
| AEO Audit Local | `/aeo-audit-local` | Batch citability audit of local content files |
| Competitive Research | `/competitive-research` | AI visibility gap analysis against a competitor |

### Example usage

```
/aeo-optimize https://mystore.com/product-page
```

Claude will fetch your AEKO data, generate optimized content (description, JSON-LD, FAQ), and open a browser preview showing the before/after comparison.

For end-user guides, see the [AEKO User Guide](https://aeko-intelligence.com/en/docs).

## Getting an API Key

1. Sign up at [aeko-intelligence.com](https://aeko-intelligence.com)
2. Go to **Settings** > **API Keys**
3. Create a new API key and copy it

## License

MIT
