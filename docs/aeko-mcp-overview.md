# aeko-mcp — What It Does

> Notion paste-ready overview of the AEKO MCP (Model Context Protocol) server. Reflects the shipped state as of **v0.5.0 (2026-04-23)**: 22 tools + 12 skills after the major consolidation audit. Source of truth: [`github.com/AEKO-Intelligence/aeko-mcp`](https://github.com/AEKO-Intelligence/aeko-mcp). For tool-level details, always cross-check with `aeko_mcp/tools/*.py`.

---

## 1. What aeko-mcp is

**aeko-mcp** is a Model Context Protocol server that turns an AI assistant (Claude Code, Claude Desktop, Codex, Cursor) into a full AEKO operator. It exposes AEKO's backend — visibility data, tracked prompts, citability scoring, and optimization suggestions — as native tools the LLM can call, and it ships a set of guided **skills** (slash commands) that walk the LLM through end-to-end workflows like auditing a product page or drafting an article optimized for AI citations.

In practice, it is the bridge between the user's local computer (files, browser previews, generated content) and AEKO's insight layer. The user stays in Claude Code, asks for an AEO audit or content draft, and aeko-mcp silently fetches the right data and saves the output to disk.

aeko-mcp is a thin, stateless process. It holds no database. Every call hits the AEKO backend over HTTPS.

### The three-tier surface

The MCP surface is organized into three tiers. This frames how tools and skills compose for different user moments.

- **Tier 1 — Ingredients (advertised tools).** Composable primitives Claude freestyles with: `aeko_list_domains`, `aeko_get_domain_info`, `aeko_get_visibility_summary` (scope-consolidated), `aeko_get_score`, `aeko_search_research_prompts`, `aeko_get_tracked_prompts`, `aeko_get_tracked_prompt` (new v0.5.0), `aeko_track_prompt` / `aeko_untrack_prompt` (new v0.5.0), `aeko_get_brand_kit`, `aeko_list_store_integrations`, `aeko_get_product_description` (new v0.5.0). Value is in the **data**; Claude assembles the sequence.
- **Tier 2 — Meal kits (skills / slash commands).** Opinionated workflows with guardrails: `/aeko-action-center`, `/aeko-update-pdp`, `/aeko-create-content`, `/aeko-fix-technical`, `/aeko-brand-kit`, `/aeko-visibility-report`, `/aeko-find-prompts-to-track`, `/aeko-prompt-deep-dive`, `/aeko-brand-competitor-analysis`, `/aeko-product-competitor-analysis`, `/aeko-refresh-jsonld`, plus the utility `/aeo-audit`. Value is in the **sequence**; the skill enforces the contract (JSON-LD, responsive HTML, brand voice, audit trail).
- **Tier 3 — Plumbing (internal helpers).** Tools wired for skills but not intended for standalone use: `aeko_get_action_plan`, `aeko_complete_action_item`, `aeko_update_brand_kit`, `aeko_update_product_description`, `aeko_update_product_tags`, `aeko_update_product_meta`, `aeko_list_store_writes`, `aeko_revert_store_write`. Their descriptions open with "Internal helper for `/aeko-<skill>`" (where applicable) so Claude deprioritizes them in standalone reasoning.

**The v0.5.0 operating principle:** MCP tools earn their slot only when they expose AEKO-unique backend intelligence (visibility forensics, citation mentions, action items, brand kit, tracked-prompt forensics, store writes with audit). If Plan.md + generic primitives (domain info, brand kit, tracked prompts) + web-accessible data cover it, it belongs in a skill — not as a tool. Skills earn their slot by compressing useful workflow, whether AEKO-grounded or not (`/aeo-audit` is the canonical exception). See `CHANGELOG.md` v0.5.0 for the 53 → 22 audit rationale.

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
- **Backend URL** defaults to `https://aeko-backend.purplehill-6906b42f.koreacentral.azurecontainerapps.io`. Override with `AEKO_API_URL`.

---

## 3. Authentication

aeko-mcp is designed to run as a remote streamable-HTTP MCP.

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
| Variable | Required | Default | Purpose |
|---|---|---|---|
| `AEKO_API_URL` | No | Azure Container Apps URL (above) | Override for staging/local backend |
| `AEKO_MCP_TRANSPORT` | No | `streamable-http` | Run the remote HTTP server |
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

### Self-hosting

```bash
pip install aeko-mcp
aeko-mcp --transport streamable-http --host 0.0.0.0 --port 8000
```

---

## 5. Tools exposed (22 total — v0.5.0)

aeko-mcp ships 22 tools across six modules — `visibility`, `research`, `aeko_score`, `action_plan`, `brand_kit`, `store_write`. Each is a `@mcp.tool()` the LLM can call by name with typed arguments. See [`aeko_mcp/tools/`](../aeko_mcp/tools/) for the source of truth.

### Domain / account (2)
| Tool | Purpose |
|---|---|
| `aeko_list_domains` | List the user's connected domains. |
| `aeko_get_domain_info` | Domain details + AI-readiness infrastructure status (llms.txt, robots.txt AI blockers, JSON-LD, sitemap). |

### Visibility / citation forensics (3)
| Tool | Purpose |
|---|---|
| `aeko_get_score` | Composite AEKO Score (0–100, grade A–F) with 5-component breakdown. Powers the Brand Visibility page. |
| `aeko_get_visibility_summary(domain_id, scope?, window?)` | **Consolidated in v0.5.0** — `scope` selects one of `overview` (default), `cited_sources`, `tracked_prompt_metrics`. Optional `window` = `7d / 30d / 90d`. Absorbs the retired `aeko_get_metrics` and `aeko_get_cited_sources`. |
| `aeko_get_tracked_prompt(prompt_id, window?)` | **New in v0.5.0** — citation-forensics payload for one tracked prompt: responses per AI platform, per-response citation array, crawled source metadata (JSON-LD types, extracted text, source-analysis scores). Core primitive for the deep-dive + content skills. |

### Research prompts (4)
| Tool | Purpose |
|---|---|
| `aeko_search_research_prompts` | Search the research prompt library (country, AI platform, query type, funnel stage, persona). Returns KO + EN phrasing with latest response metrics. Persona filter added in v0.5.0. |
| `aeko_get_tracked_prompts` | List prompts actively tracked for the user's domain. |
| `aeko_track_prompt(raw_prompt, ai_platform, ...)` | **New in v0.5.0 (WRITE)** — closes the find-prompts-to-track loop. |
| `aeko_untrack_prompt(prompt_id)` | **New in v0.5.0 (WRITE)** — inverse; preserves historical data (`UserPrompts.status='untracked'`). |

### Action Items / Plan.md (4)
| Tool | Purpose |
|---|---|
| `aeko_list_action_items(domain_id, status, ...)` | List pending items from the Action tab (`store_write_artifact` + `local_content_artifact`). |
| `aeko_list_technical_items(domain_id, status, ...)` | List pending items from the Technical tab (`technical_artifact`). |
| `aeko_get_action_plan(item_id)` | Fetch one item's Plan.md (YAML frontmatter + templated prose). Same endpoint serves Action and Technical tabs. |
| `aeko_complete_action_item(item_id, ...)` | Mark an item complete with optional `artifact_summary`, `artifact_paths`, `write_result`. |

### Brand Kit (2)
| Tool | Purpose |
|---|---|
| `aeko_get_brand_kit(domain_id)` | Fetch the active Brand Kit. |
| `aeko_update_brand_kit(kit_id, ...)` | Patch Brand Kit fields. Bumps `snapshot_version` only on semantic field changes. |

### Store write (Cafe24 / Shopify) (7)
| Tool | Purpose |
|---|---|
| `aeko_list_store_integrations` | List connected Cafe24 / Shopify stores. Available on all tiers. |
| `aeko_get_product_description(integration_id, external_product_id)` | **New in v0.5.0** — returns raw editable description HTML (Cafe24 `description` / Shopify `body_html`). Load-bearing for JSON-LD refresh + `append_below_existing` flows. |
| `aeko_update_product_description(...)` | Replace full description HTML. Writes JSON-LD too (embedded `<script>` blocks inside the HTML). |
| `aeko_update_product_tags(...)` | Replace the tag list. |
| `aeko_update_product_meta(...)` | Update SEO title + meta description. |
| `aeko_list_store_writes` | Audit history of recent writes. |
| `aeko_revert_store_write(audit_id)` | Push the before-snapshot back. |

---

## 6. Backend endpoints aeko-mcp wraps

aeko-mcp holds no state. Every tool maps to one or more backend HTTP calls.

| Endpoint | Method | Used by |
|---|---|---|
| `/api/domains` | GET | `aeko_list_domains` |
| `/api/domains/{domain_id}` | GET | `aeko_get_domain_info` |
| `/api/geo-score` | GET | `aeko_get_score` |
| `/api/visibility/summary` | GET | `aeko_get_visibility_summary` (all three scopes) |
| `/api/research/prompts` | GET | `aeko_search_research_prompts` |
| `/api/tracked-prompts` | GET/POST/DELETE | `aeko_get_tracked_prompts`, `aeko_track_prompt`, `aeko_untrack_prompt` |
| `/api/tracked-prompts/{prompt_id}` | GET | `aeko_get_tracked_prompt` (composes Responses + ResponseCitations + Sources + CrawledPages) |
| `/api/action-items` | GET | `aeko_list_action_items`, `aeko_list_technical_items` (distinguished by `tab` param) |
| `/api/action-items/{item_id}` | GET | `aeko_get_action_plan` |
| `/api/action-items/{item_id}/complete` | POST | `aeko_complete_action_item` |
| `/api/brand-kit/{domain_id}` | GET | `aeko_get_brand_kit` |
| `/api/brand-kits/{kit_id}` | PATCH | `aeko_update_brand_kit` |
| `/api/store-integrations` | GET | `aeko_list_store_integrations` |
| `/api/store-integrations/{id}/products/{ext_id}/description` | GET | `aeko_get_product_description` |
| `/api/store-integrations/{id}/products/{ext_id}` | POST | `aeko_update_product_description`, `aeko_update_product_tags`, `aeko_update_product_meta` |
| `/api/store-write-audit` | GET | `aeko_list_store_writes` |
| `/api/store-write-audit/{audit_id}/revert` | POST | `aeko_revert_store_write` |

Everything is authenticated with `Authorization: Bearer <token>`. In hosted HTTP mode, the MCP client obtains and refreshes that token via AEKO's OAuth flow. Errors are mapped to user-friendly messages: 401 → reconnect your AEKO session, 403 → subscription or scope may not include this feature, 404 → resource not found, 5xx → server error, try again later.

---

## 7. How Action Items flow through MCP (v0.5.0)

The Action Items + Plan.md pipeline is the beating heart of aeko-mcp. The v2 Suggestions layer was retired in v0.5.0 — Action Items is now the single routing surface.

```
┌────────────────┐   scheduled   ┌────────────────┐
│ Tracked prompts│──────────────▶│ AEKO pipelines │
│ + synced store│               │ (source scrape,│
└────────────────┘               │  item gen +    │
                                 │  Plan.md       │
                                 │  templating)   │
                                 └───────┬────────┘
                                         │ writes
                                         ▼
                                ┌─────────────────────┐
                                │ ActionItems table   │
                                │  + templated        │
                                │    Plan.md prose    │
                                └────────┬────────────┘
                                         │
             ┌───────────────────────────┼────────────────────────────┐
             │                           │                            │
             ▼                           ▼                            ▼
    aeko_list_action_items        aeko_list_technical_items    (execution_class branches)
    (Action tab)                  (Technical tab)
             │                           │
             └─────────────┬─────────────┘
                           ▼
                  /aeko-action-center  ── surfaces 3 categories:
                                         • Technical
                                         • 상품 페이지 개선 (PDP)
                                         • Content generation
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
      /aeko-fix-      /aeko-update-   /aeko-create-
      technical       pdp             content
              │            │            │
              └────────────┼────────────┘
                           ▼
                  aeko_get_action_plan(item_id)
                  + aeko_get_brand_kit(domain_id)
                  + aeko_get_tracked_prompt / aeko_get_product_description
                  + WebFetch (for target_url + crawled sources)
                           │
                           ▼
                  Claude drafts the artifact locally
                  (HTML, JSON-LD, markdown)
                           │
                           ▼
                  write path diverges by execution_class:
                  • store_write_artifact → aeko_update_product_description (+ optional revert)
                  • technical_artifact   → Write to local file + deployment guidance
                  • local_content_artifact → Write to local file
                           │
                           ▼
                  aeko_complete_action_item(item_id, artifact_summary, ...)
                  POST /api/action-items/{item_id}/complete
                  { status: completed, completed_via: "mcp" }
```

The user never edits ActionItems rows in Postgres. They invoke `/aeko-action-center`, pick a category, dispatch to the executor skill, the skill fetches Plan.md + live context, drafts the artifact, writes it (store API or local disk per `execution_class`), and flips the item to `completed`. Every completion is tagged `completed_via='mcp'` so AEKO can measure MCP-driven adoption.

---

## 8. Skills (guided workflows) — v0.5.0

Skills are slash commands the user invokes in their MCP host. They encode the opinionated sequence: *gather data → draft → preview → save → complete*. 12 skills ship in v0.5.0 (8 retired + 8 new + 4 kept vs. v0.4.0 — see `CHANGELOG.md`).

### Retired in v0.5.0 (alongside v0.4.0 retirements)

`/aeko-run-action` (split by `execution_class`), `/aeko-create-own-content`, `/aeko-create-external-content` (both merged into `/aeko-create-content`), `/aeko-competitive-pdp-input` (absorbed into `/aeko-update-pdp` + `/aeko-brand-competitor-analysis`), `/aeko-fix-store-level` (merged into `/aeko-fix-technical`), `/aeo-audit-local`, `/competitive-research`, `/create-visibility-report`.

### Router + executors (4)
| Skill | Command | What it does |
|---|---|---|
| **Action Center** | `/aeko-action-center [domain_id]` | Router. Lists pending items grouped into three categories by `execution_class`: Technical / PDP (상품 페이지 개선) / Content generation. Prints ready-to-copy dispatch blocks. Never executes items itself. |
| **Update PDP** | `/aeko-update-pdp <item_id>` | Executor for `store_write_artifact` items. Fetches Plan.md → WebFetch product page + images → drafts responsive HTML + JSON-LD → writes shadow product (default) or appends below existing → marks complete with audit trail. |
| **Create Content** | `/aeko-create-content <item_id>` | Executor for `local_content_artifact` items. Pulls tracked-prompt citation forensics to identify winning source structures (Reddit, Naver blogs, partner media, etc.) → drafts content that mimics those structures in user's brand voice → saves locally only. Never writes to store. |
| **Fix Technical** | `/aeko-fix-technical <item_id>` | Executor for `technical_artifact` items (llms.txt, robots.txt, site-level JSON-LD). Self-contained with embedded llmstxt.org + robots.txt AI-crawler + schema.org JSON-LD spec rules. Produces artifacts locally with deployment guidance. |

### Brand Kit (1)
| Skill | Command | What it does |
|---|---|---|
| **Brand Kit** | `/aeko-brand-kit <domain_id>` | View or edit a domain's brand kit (voice, tone, must-include, forbidden). Load-bearing input for every content + PDP skill. |

### Visibility intelligence (3)
| Skill | Command | What it does |
|---|---|---|
| **Visibility Report** | `/aeko-visibility-report [domain_id] [window=7d\|14d\|30d\|90d] [depth=summary\|full]` | On-demand visibility report. `depth=summary` → C-level snapshot. `depth=full` → deep dive with per-page analysis + ranked actions. |
| **Find Prompts to Track** | `/aeko-find-prompts-to-track [domain_id]` | Discovery loop. Searches the research prompt library with filters (AI platform, persona, funnel stage, country), surfaces candidates, tracks the ones the user picks. |
| **Prompt Deep Dive** | `/aeko-prompt-deep-dive <prompt_id> [window]` | Citation-forensics deep-dive on one tracked prompt. Lists per-platform responses, ranks cited sources, explains why they win citations, recommends a concrete action. The AEKO-unique value prop operationalized. |

### Competitor analysis (2)
| Skill | Command | What it does |
|---|---|---|
| **Brand Competitor Analysis** | `/aeko-brand-competitor-analysis [domain_id] <competitor>` | Brand-level competitor positioning via WebSearch + Wikipedia/Wikidata + tracked-prompt cross-reference. |
| **Product Competitor Analysis** | `/aeko-product-competitor-analysis <product_id> [competitor_urls...]` | Product-level property comparison. WebSearch finds comparable products if not specified, WebFetch inspects each PDP, Claude builds a comparison matrix aligned with what AI engines care about. |

### JSON-LD maintenance (1)
| Skill | Command | What it does |
|---|---|---|
| **Refresh JSON-LD** | `/aeko-refresh-jsonld <product_id>` | Periodic JSON-LD refresh (review counts, aggregate rating, recent reviews). Fetch current description via `aeko_get_product_description` → patch JSON-LD blocks in place → write back via `aeko_update_product_description`. Designed to be scheduled. |

### Utility (1)
| Skill | Command | What it does |
|---|---|---|
| **AEO Audit** | `/aeo-audit [url]` | 5-category weighted AEO readiness audit for any URL (Schema 25% / Citability 25% / Infrastructure 20% / Content 20% / Platform 10%). Calls no AEKO MCP tools — pure workflow compression. |

---

## 9. Typical user workflows (v0.5.0)

**1. Morning triage in Claude Code**
```
/aeko-action-center
```
Claude shows pending items grouped into Technical / PDP / Content categories, highlights critical items, and prints ready-to-copy dispatch commands for each. User picks one and runs the corresponding executor (`/aeko-fix-technical`, `/aeko-update-pdp`, or `/aeko-create-content`).

**2. Rewriting a product detail page**
```
/aeko-update-pdp itm_pdp_abc123
```
Claude pulls Plan.md (frontmatter + templated prose), fetches Brand Kit + live page via WebFetch, mirrors the winning H2 spine, drafts bilingual KO/EN description, generates `Product` + `FAQPage` (+ `Review`/`AggregateRating` if data exists) JSON-LD, writes to a shadow product (default) via `aeko_update_product_description`, and marks the item complete with audit trail. Revert is available via `aeko_revert_store_write`.

**3. Fresh AEO audit of any URL**
```
/aeo-audit https://mystore.com/products/mattress-queen
```
Claude runs the 5-category weighted audit, returns a ranked list of fixes with severity and effort estimates.

**4. Discovering prompts to track**
```
/aeko-find-prompts-to-track
```
Claude asks for filter criteria (AI platform, persona, funnel stage, country), queries the research prompt library, surfaces 10–20 candidates grouped by persona/platform, the user picks which to track, and the skill calls `aeko_track_prompt` for each.

**5. Deep-diving a tracked prompt**
```
/aeko-prompt-deep-dive prm_xxx 30d
```
Claude pulls the full citation-forensics payload — responses per AI platform, citation arrays, crawled source metadata — ranks the top sources, explains why they win citations, and recommends one concrete action (mirror page, fix missing JSON-LD, track a related prompt).

**6. Refreshing JSON-LD on a flagship product**
```
/aeko-refresh-jsonld prd_xxx
```
Claude fetches the current description HTML via `aeko_get_product_description`, parses the embedded JSON-LD, updates `AggregateRating.ratingValue` / `reviewCount` / fresh `review[]` entries, and writes the patched HTML back via `aeko_update_product_description`. Designed for periodic scheduling.

**7. Weekly / monthly visibility report**
```
/aeko-visibility-report 7d summary
```
C-level snapshot: headline KPI movement, top-performing prompts, new citations this week, notable losses, recommended next action. Use `depth=full` for the page-by-page deep dive.

---

## 10. Limitations / not-yet

- **Shadow product endpoint is pending.** The canonical PDP write mode is `shadow_product`, but until `POST /api/store-integrations/{id}/products/{ext_id}/shadow` ships, backend stamps `preview_only` + `write_target=local` on `pdp_html` items. `/aeko-update-pdp` handles both modes end-to-end.
- **Store write-back covers Cafe24 + Shopify only.** Naver Smartstore, Coupang, and other KR-specific platforms are not yet wired. Content skills write to local disk; users paste into those admins manually.
- **No URL → domain_id reverse lookup.** Tools that need a `domain_id` require the UUID up front. The skills prompt the user when it is missing.
- **Single-tenant.** One AEKO bearer token per install today. Multi-workspace will need a rethink.
- **No offline mode.** Every tool is a live backend call. No caching, no stale snapshots.
- **Filesystem MCP prerequisite for Claude Desktop.** Skills that write artifacts locally need `Read`/`Write`/`Glob`/`Bash`. Claude Code has these natively. Claude Desktop requires installing `@modelcontextprotocol/server-filesystem` or equivalent — see `aeko-plugin/README.md`.

---

## 11. Links

- **Repo**: [github.com/AEKO-Intelligence/aeko-mcp](https://github.com/AEKO-Intelligence/aeko-mcp)
- **AEKO dashboard**: [aeko-intelligence.com](https://aeko-intelligence.com)
- **User guide**: [aeko-intelligence.com/en/docs](https://aeko-intelligence.com/en/docs)
- **Auth direction**: login-based AEKO bearer token flow
- **Backend base URL (prod)**: `https://aeko-backend.purplehill-6906b42f.koreacentral.azurecontainerapps.io`

---

*For the authoritative current tool list, see [`aeko_mcp/tools/`](../aeko_mcp/tools/). For skills, see [`skills/`](../skills/) (Claude Code) and [`.codex-plugin/skills/`](../.codex-plugin/skills/) (Codex).*
