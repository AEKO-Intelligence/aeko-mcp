# aeko-mcp — What It Does

> Notion paste-ready overview of the AEKO MCP (Model Context Protocol) server. Everything below reflects the actual shipped state of the repo at [`github.com/AEKO-Intelligence/aeko-mcp`](https://github.com/AEKO-Intelligence/aeko-mcp).

---

## 1. What aeko-mcp is

**aeko-mcp** is a Model Context Protocol server that turns an AI assistant (Claude Code, Claude Desktop, Codex, Cursor) into a full AEKO operator. It exposes AEKO's backend — visibility data, tracked prompts, citability scoring, and optimization suggestions — as native tools the LLM can call, and it ships a set of guided **skills** (slash commands) that walk the LLM through end-to-end workflows like auditing a product page or drafting an article optimized for AI citations.

In practice, it is the bridge between the user's local computer (files, browser previews, generated content) and AEKO's insight layer. The user stays in Claude Code, asks for an AEO audit or content draft, and aeko-mcp silently fetches the right data and saves the output to disk.

aeko-mcp is a thin, stateless process. It holds no database. Every call hits the AEKO backend over HTTPS.

---

## 2. Where it sits in the AEKO stack

```
┌────────────────────────┐
│  Claude Code / Desktop │
│  Cursor / any MCP host │
└─────────┬──────────────┘
          │  MCP (stdio or HTTP)
          ▼
┌────────────────────────┐       ┌─────────────────────┐
│  aeko-mcp              │──────▶│  AEKO backend       │
│  - MCP tools           │ HTTPS │  FastAPI            │
│  - skill workflows     │       │  Azure Container    │
│  - reads/writes local  │       │  Apps (koreacentral)│
│    files               │       └──────────┬──────────┘
└────────────────────────┘                  │
                                            ▼
                                   ┌─────────────────────┐
                                   │  Postgres + Pipelines│
                                   │  (prompt tracking,   │
                                   │   source scraping,   │
                                   │   suggestion jobs)   │
                                   └─────────────────────┘
```

- **aeko-mcp is a thin wrapper.** No state, no caching, no offline mode. Every tool is a one-shot HTTP call.
- **Local-side capabilities** (reading product images, scanning content directories, saving generated HTML/JSON-LD, opening browser previews) are still the reason a local stdio deployment matters. The same codebase can now also be run as a remote streamable HTTP MCP server for login-based hosted setups.
- **Backend URL** defaults to `https://aeko-backend.purplehill-6906b42f.koreacentral.azurecontainerapps.io`. Override with `AEKO_API_URL`.

---

## 3. Authentication

aeko-mcp is both a local stdio MCP and a remote streamable-HTTP MCP.
Those two modes use different auth paths:

- **Remote HTTP (recommended).** MCP clients discover the AEKO
  Authorization Server via `/.well-known/oauth-protected-resource` +
  `/.well-known/oauth-authorization-server`, register themselves via
  RFC 7591 Dynamic Client Registration, and drive an OAuth 2.1 + PKCE
  flow that ends with the user logging into AEKO in their browser.
  The AS issues an opaque bearer access token (prefix `aeko_ot1_`,
  1-hour TTL) plus a rotation-enabled refresh token (30-day TTL).
  Tokens are sent on every backend request as `Authorization: Bearer <token>`.
  **Nothing to paste.** This is the flow `claude mcp add --transport http`
  and `codex mcp add --transport http` use.
- **Local stdio (legacy).** The `AEKO_AUTH_TOKEN`
  env var is still honored for local process setups and clients without
  OAuth support. This is the path behind the "Advanced / Legacy — Agent Token"
  section in AEKO Settings. The token is a short-lived HS256 JWT
  (prefix `aeko_at1_`) minted from the user's logged-in AEKO session.

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `AEKO_AUTH_TOKEN` | **Yes for stdio** | — | Legacy/local bearer token used by stdio installs and the temporary bridge flow |
| `AEKO_API_URL` | No | Azure Container Apps URL (above) | Override for staging/local backend |
| `AEKO_CONTENT_DIR` | No | — | Default directory for local content scanning/reading tools |
| `AEKO_IMAGE_DIR` | No | — | Sandbox root for product image tools |
| `AEKO_OUTPUT_DIR` | No | `./aeko_output/` | Where `aeko_save_content` writes files |
| `AEKO_MCP_TRANSPORT` | No | `stdio` | Run local stdio or streamable HTTP |
| `AEKO_MCP_STREAMABLE_HTTP_PATH` | No | `/` | Path the streamable HTTP app serves on. Defaults to `/` so embedding apps can `app.mount("/mcp", create_streamable_http_app())` without doubling the prefix. Override to `/mcp` when running standalone. |

---

## 4. Install & configure

### Claude Code (recommended)

```bash
# Add the AEKO marketplace
/plugin marketplace add AEKO-Intelligence/aeko-mcp

# Install the plugin
/plugin install aeko-mcp@AEKO-Intelligence
```

The bundled plugin points at the hosted AEKO MCP URL:
- `https://aeko-intelligence.com/mcp`

After installing or updating the plugin:
- restart Claude Code or run `/reload-plugins`
- open `/mcp`
- choose `aeko`
- complete the browser OAuth flow

No env var setup is required for the normal Claude Code path.

### Claude Desktop

Use AEKO as a **custom remote connector**, not through `claude_desktop_config.json`:

1. Open `Customize > Connectors`
2. Click `Add custom connector`
3. Enter `https://aeko-intelligence.com/mcp`
4. Save it
5. Click `Connect` and complete the browser OAuth flow

This is the OAuth-first Desktop path.

### Codex

Add AEKO as a remote MCP server:

```bash
codex mcp add --transport http aeko https://aeko-intelligence.com/mcp
```

Then authenticate through the MCP client/browser flow.

### Cursor

Use Cursor's remote MCP support with the same hosted URL:
- `https://aeko-intelligence.com/mcp`

### Manual install (legacy / local stdio)

```bash
pip install aeko-mcp
# or from source:
git clone https://github.com/AEKO-Intelligence/aeko-mcp.git
cd aeko-mcp && pip install -e .
python -m aeko_mcp
```

For remote HTTP hosting:

```bash
python -m aeko_mcp --transport streamable-http --host 0.0.0.0 --port 8000
```

---

## 5. Tools exposed

aeko-mcp ships a growing set of tools across several functional groups — visibility, content, product, suggestions, research, preview, images, generate, report, citability, score, local_content, campaigns, content_recommendations, and store_write. Each is a `@mcp.tool()` the LLM can call by name with typed arguments. See [`aeko_mcp/tools/`](../aeko_mcp/tools/) for the current source of truth.

### Scoring & metrics (3)
| Tool | Purpose |
|---|---|
| `aeko_get_score` | Composite AEKO Score (0–100, grade A–F) with 5-component breakdown: AI Mention Frequency, Citation Rate, Content Citability, Technical Readiness, Sentiment. Includes top competitors. |
| `aeko_get_metrics` | 7-day performance metrics with week-over-week trends. |
| `aeko_get_visibility_summary` | Brand visibility across ChatGPT / Claude / Gemini / Perplexity over 30 days. |

### Domain & page analysis (3)
| Tool | Purpose |
|---|---|
| `aeko_get_domain_info` | Domain details and AI-readiness infrastructure status (llms.txt, robots.txt AI blockers, JSON-LD, sitemap). |
| `aeko_get_page_analysis` | Per-page AI-readiness score, structured data status, issues, and recommendations. |
| `aeko_get_cited_sources` | Pages from your domain that AI engines have cited, with citation counts and source prompts. |

### Research prompts (3)
| Tool | Purpose |
|---|---|
| `aeko_search_research_prompts` | Search the research prompt library by scope, keyword, country, AI platform, query type. Returns KO + EN phrasing and latest AI response with mention metrics. |
| `aeko_get_tracked_prompts` | List prompts actively tracked for the user's domain. |
| `aeko_get_product_analysis` | Competitive analysis for a product URL — competitor positioning, visibility gaps, market opportunities. |

### AI citability (2)
| Tool | Purpose |
|---|---|
| `aeko_get_citability` | Citability score for a specific page, with 5-dimension breakdown: Answer Block Quality, Self-Containment, Structural Readability, Statistical Density, Uniqueness Signals. |
| `aeko_score_text` | Score arbitrary text for AI citability (supports language-specific analysis). |

### Infrastructure & content preparation (5)
| Tool | Purpose |
|---|---|
| `aeko_prepare_llms_txt` | Gather data for llms.txt generation. |
| `aeko_prepare_robots_txt_fix` | Analyze robots.txt for AI crawler blocks, return a fix snippet. |
| `aeko_validate_llms_txt` | Validate an existing llms.txt for spec compliance. |
| `aeko_prepare_json_ld` | Gather data for JSON-LD generation with field guidance per schema type (Product, FAQ, Article, Organization, WebSite, HowTo). |
| `aeko_prepare_report` | Aggregate all domain data for report generation. |

### Local content & preview (6)
| Tool | Purpose |
|---|---|
| `aeko_list_product_images` | List images in a sandboxed directory. |
| `aeko_read_product_image` | Return an image to Claude as an MCP Image object. |
| `aeko_save_content` | Save generated content to `AEKO_OUTPUT_DIR` (supports `.md`, `.html`, `.json`, `.txt`). |
| `aeko_scan_content_directory` | Scan a directory for content files (HTML, MD, TXT, CSV, JSON, PDF, DOCX). |
| `aeko_read_content_file` | Read and extract text from a local file (HTML/PDF/DOCX extraction). |
| `aeko_audit_content_file` | Read a local file and score it for AI citability. |

### Suggestions & optimization (3)
| Tool | Purpose |
|---|---|
| `aeko_get_suggestions` | Prioritized optimization suggestions (legacy flat list). |
| `aeko_complete_suggestion` | Mark a suggestion as completed (logged to backend as `completed_via='mcp'`). |
| `aeko_check_brand_entity` | Check Wikipedia/Wikidata entity recognition for a brand. |

### Preview (1)
| Tool | Purpose |
|---|---|
| `aeko_preview_optimized_page` | Generate a self-contained HTML preview (Tailwind + JS) with Original / Optimized / Diff / JSON-LD tabs, Rich Result card, and AEO checklist. Auto-opens in the browser. |

### Suggestions v2 — the 4-category action model (6, new)

The v2 suggestion layer organizes optimization work into 4 action buckets and attaches a **rich content brief** to every suggestion (target domain/URL, required structure, persona, tone, required JSON-LD, must-include fields, competitor source evidence). These tools consume a forward-looking backend contract (`/api/suggestions/v2`, `/api/suggestions/v2/{key}`, `/api/prompt-groups`). They degrade gracefully with a markdown fallback when the backend endpoints are not yet live, so they can ship ahead of backend.

| Tool | Purpose |
|---|---|
| `aeko_get_suggestions_v2` | Fetch categorized suggestions grouped into the 4 buckets: **pdp_update**, **own_content**, **external_content**, **store_level**. Optional filters: `category`, `group_id`, `priority`. |
| `aeko_get_suggestion` | Hydrate a single v2 suggestion with its full brief and source evidence. |
| `aeko_list_prompt_groups` | List prompt groups defined for a domain (e.g. "mattress category") so work can be scoped by intent. |
| `aeko_get_pdp_brief` | Product-detail-page rewrite brief — combines the v2 brief with the current page analysis and citability score for `brief.target_url`. Accepts an optional `domain_id` override. |
| `aeko_get_content_brief` | Content-creation brief for `own_content` or `external_content` suggestions, with supporting tracked-prompt context. |
| `aeko_get_store_level_brief` | Store-level-fix brief (llms.txt, robots.txt, sitemap, schema infra) with a recommended tool chain. |

---

## 6. Backend endpoints aeko-mcp wraps

aeko-mcp holds no state. Every tool maps to one or more backend HTTP calls.

| Endpoint | Method | Used by |
|---|---|---|
| `/api/geo-score` | GET | `aeko_get_score` |
| `/api/tracked-prompts/metrics` | GET | `aeko_get_metrics` |
| `/api/visibility/summary` | GET | `aeko_get_visibility_summary`, `aeko_get_cited_sources` |
| `/api/domains/{domain_id}` | GET | `aeko_get_domain_info`, `aeko_prepare_llms_txt`, `aeko_prepare_robots_txt_fix`, `aeko_prepare_json_ld`, `aeko_prepare_report` |
| `/api/store-pages/analysis` | GET | `aeko_get_page_analysis`, `aeko_get_pdp_brief` (v2) |
| `/api/suggestions` | GET | `aeko_get_suggestions` (legacy) |
| `/api/suggestions/complete` | POST | `aeko_complete_suggestion` (body: `{suggestion_key, completed_via: "mcp"}`) |
| `/api/research/prompts` | GET | `aeko_search_research_prompts` |
| `/api/tracked-prompts` | GET | `aeko_get_tracked_prompts` |
| `/api/citability/page` | GET | `aeko_get_citability`, `aeko_get_pdp_brief` (v2) |
| `/api/citability/score` | POST | `aeko_score_text` |
| `/api/product-analyses` | GET | `aeko_prepare_report` |
| `/api/brand-entities` | GET | `aeko_check_brand_entity` |
| `/api/suggestions/v2` | GET | `aeko_get_suggestions_v2` **(backend not yet shipped)** |
| `/api/suggestions/v2/{key}` | GET | `aeko_get_suggestion`, `aeko_get_pdp_brief`, `aeko_get_content_brief`, `aeko_get_store_level_brief` **(backend not yet shipped)** |
| `/api/prompt-groups` | GET | `aeko_list_prompt_groups` **(backend not yet shipped)** |

Everything is authenticated with `Authorization: Bearer <token>`. In hosted HTTP mode, the MCP client obtains and refreshes that token via AEKO's OAuth flow. In legacy stdio mode, the token can still come from `AEKO_AUTH_TOKEN`. Errors are mapped to user-friendly messages: 401 → reconnect your AEKO session, 403 → subscription or scope may not include this feature, 404 → resource not found, 5xx → server error, try again later. The v2 tools additionally swallow *all* exceptions and return a friendly "endpoint unavailable" markdown block, so the MCP can be shipped before the backend finishes the v2 contract.

---

## 7. How suggestions flow through MCP

The suggestion lifecycle is the beating heart of aeko-mcp:

```
┌────────────────┐   scheduled   ┌────────────────┐
│ Tracked prompts│──────────────▶│ AEKO pipelines │
│ + synced store│               │ (source scrape,│
└────────────────┘               │  brief gen)    │
                                 └───────┬────────┘
                                         │ writes
                                         ▼
                                ┌──────────────────┐
                                │ suggestions table│
                                │  + content brief │
                                └────────┬─────────┘
                                         │
                    ┌────────────────────┼─────────────────────┐
                    │                    │                     │
                    ▼                    ▼                     ▼
          aeko_get_suggestions_v2  aeko_get_pdp_brief    aeko_get_content_brief
          (categorized)            aeko_get_store_level_brief
                    │                    │                     │
                    └────────────┬───────┴─────────────────────┘
                                 ▼
                          Claude drafts artifacts locally
                          (HTML, JSON-LD, markdown, files)
                                 │
                                 ▼
                          aeko_save_content(...)
                                 │
                                 ▼
                        aeko_complete_suggestion(key)
                                 │  POST /api/suggestions/complete
                                 ▼
                        { status: completed, completed_via: "mcp" }
```

The user never edits suggestion rows in Postgres. They invoke a skill, Claude calls the right brief tool, drafts the output, saves it, and the completion API flips the suggestion state. Every completion is tagged `completed_via='mcp'` so AEKO can measure MCP-driven adoption.

---

## 8. Skills (guided workflows)

Skills are slash commands the user invokes in their MCP host. They encode the opinionated sequence: *gather data → draft → preview → save → complete*. 15 ship today.

### Legacy / general-purpose (10)
| Skill | Command | What it does |
|---|---|---|
| AEO Audit | `/aeo-audit` | 5-category weighted AEO readiness audit for any URL (Schema 25% / Citability 25% / Infrastructure 20% / Content 20% / Platform 10%). |
| AEO Optimize | `/aeo-optimize` | Full product-page optimization: audit → generate optimized description + JSON-LD + FAQ → open browser preview → export. |
| Generate JSON-LD | `/generate-jsonld` | Production-ready Product schema with 12-point completeness checklist. |
| Generate FAQ | `/generate-faq` | AI-query-matched FAQ content with FAQPage JSON-LD, seeded from real tracked prompts. |
| Create Blog Article | `/create-blog-article` | Blog content optimized for AI visibility. |
| Create Social Content | `/create-social-content` | Platform-specific social content from AEKO metrics. |
| Create Marketing Materials | `/create-marketing-materials` | Email / ad copy / landing content. |
| AEO Audit Local | `/aeo-audit-local` | Batch citability audit of a local directory (HTML, MD, PDF, DOCX). |
| Create Visibility Report | `/create-visibility-report` | Full AI visibility report with AEKO Score, page-by-page analysis, and ranked actions. |
| Competitive Research | `/competitive-research` | AI visibility gap analysis against a competitor. |

### v2 — 4-category action model (5, new)

One skill per action bucket, plus a router. Each skill expects a v2 `Suggestion` brief and draws on `source_evidence` (scraped winning competitor structures) as the load-bearing instruction to "mirror what already wins AI citations."

| Skill | Command | What it does |
|---|---|---|
| **Action Center** | `/aeko-action-center` | Top-level router. Shows the 4 buckets, offers prompt-group scoping, prints ready-to-copy slash-command blocks for the user to run. Falls back to legacy skills when v2 endpoints are unavailable. |
| **Update PDP** | `/aeko-update-pdp <suggestion-key>` | Own Store · Product Detail Update. Rewrites a PDP with bilingual KO/EN, regenerates JSON-LD, generates FAQ block, opens browser preview. Publishes to Shopify / Cafe24 / Naver Smartstore instructions. |
| **Create Own Content** | `/aeko-create-own-content <suggestion-key>` | Own Store · Content. Drafts a blog article / FAQ / landing page on the user's own domain matching the brief's structure, persona, and tone. |
| **Create External Content** | `/aeko-create-external-content <suggestion-key>` | Other Media · Content. Drafts Wikipedia entries, partner media guest posts, Naver 블로그 / Tistory / Brunch drafts, press releases. **Never auto-publishes** — outputs local files only. |
| **Fix Store-Level** | `/aeko-fix-store-level <suggestion-key>` | Own Store · Store-Level. Generates llms.txt, robots.txt fixes, sitemap.xml, or schema infra. Flags Cafe24 hosting caveats for llms.txt. |

---

## 9. Typical user workflows

**1. Morning triage in Claude Code**
```
/aeko-action-center
```
Claude shows how many suggestions live in each of the 4 buckets, highlights critical items, and prints ready-to-copy command blocks for the highest-priority suggestion in each bucket. User picks one and runs it.

**2. Rewriting a product detail page**
```
/aeko-update-pdp sugg_pdp_abc123
```
Claude pulls the brief (structure, persona, required JSON-LD, competitor evidence), mirrors the winning H2 spine, drafts a bilingual KO/EN description, generates `Product` + `FAQPage` JSON-LD, opens a browser preview with before/after diff, saves to `aeko_output/pdp/`, and marks the suggestion complete. User copies the HTML into Cafe24 admin.

**3. Fresh AEO audit of a product URL**
```
/aeo-audit https://mystore.com/products/mattress-queen
```
Claude runs the 5-category weighted audit, returns a ranked list of fixes with severity and effort estimates.

**4. Generating a Wikipedia draft**
```
/aeko-create-external-content sugg_ext_xyz789
```
Claude drafts a neutral-POV Wikipedia article referencing reliable third-party sources, verifies brand entity recognition, saves to `aeko_output/content/external/wikipedia.org/`. The user submits it manually — the skill never touches the network.

**5. Local content audit of a directory of drafts**
```
/aeko-audit-local ./drafts
```
Claude scans every HTML / MD / PDF / DOCX in the directory, scores each for citability, and returns a report ranked by impact.

---

## 10. Limitations / not-yet

- **v2 backend contract is not yet live.** `/api/suggestions/v2`, `/api/suggestions/v2/{key}`, and `/api/prompt-groups` are scheduled. The 6 v2 tools and 5 v2 skills ship now and degrade gracefully with a markdown "endpoint unavailable" message. The legacy `aeko_get_suggestions` + 10 legacy skills keep working regardless.
- **No write-back to e-commerce platforms.** aeko-mcp drafts PDP HTML, JSON-LD, and articles to local files but does not POST them to Shopify / Cafe24 / Naver Smartstore. The user pastes into the admin themselves. This is intentional for Phase 1; write-back is being scoped as a Phase 2.
- **No URL → domain_id reverse lookup.** Tools that need a `domain_id` require the UUID up front. The skills prompt the user when it is missing.
- **Single-tenant.** One AEKO bearer token per install today. Multi-workspace will need a rethink.
- **No prompt-group CRUD from MCP.** Once prompt groups exist in the backend, aeko-mcp can *read* them (`aeko_list_prompt_groups`) but not create or edit them. Group management is a dashboard concern.
- **No offline mode.** Every tool is a live backend call. No caching, no stale snapshots.

---

## 11. Links

- **Repo**: [github.com/AEKO-Intelligence/aeko-mcp](https://github.com/AEKO-Intelligence/aeko-mcp)
- **AEKO dashboard**: [aeko-intelligence.com](https://aeko-intelligence.com)
- **User guide**: [aeko-intelligence.com/en/docs](https://aeko-intelligence.com/en/docs)
- **Auth direction**: login-based AEKO bearer token flow
- **Backend base URL (prod)**: `https://aeko-backend.purplehill-6906b42f.koreacentral.azurecontainerapps.io`

---

*For the authoritative current tool list, see [`aeko_mcp/tools/`](../aeko_mcp/tools/). For skills, see [`skills/`](../skills/) (Claude Code) and [`.codex-plugin/skills/`](../.codex-plugin/skills/) (Codex).*
