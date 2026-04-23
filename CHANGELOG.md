# Changelog

All notable changes to `aeko-mcp` are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project adheres to semantic versioning as practiced by [PEP 440](https://peps.python.org/pep-0440/).

The backend at `panomix/aeko` pins this package by git tag in `requirements.txt` (e.g. `aeko-mcp @ git+https://github.com/AEKO-Intelligence/aeko-mcp.git@v0.4.0`). When a release here publishes, the `release-bump-backend` workflow opens a PR against the backend repo to bump the pin.

## [Unreleased]

_No unreleased changes._

## [0.5.2] — 2026-04-23

Patch — fixes tool display names in MCP clients. Before this, Claude
Desktop and other clients rendered each tool as its raw Python
function name (e.g. `aeko_get_action_plan`) because we only set
`annotations`, never the `title` kwarg on `@mcp.tool`. The MCP 2025-06
spec surfaces `title` as the human-readable label; clients fall back to
`name` when it's missing.

### Changed

Added `title="..."` on every one of the 22 tool decorators. The titles
are short verb-phrases that read cleanly in a connector sidebar:

- `aeko_list_domains` → "List connected domains"
- `aeko_get_domain_info` → "Get domain info"
- `aeko_get_visibility_summary` → "Get visibility summary"
- `aeko_get_score` → "Get AEKO score"
- `aeko_search_research_prompts` → "Search research prompts"
- `aeko_get_tracked_prompts` → "List tracked prompts"
- `aeko_get_tracked_prompt` → "Get tracked prompt details"
- `aeko_track_prompt` → "Track a prompt"
- `aeko_untrack_prompt` → "Untrack a prompt"
- `aeko_list_action_items` → "List action items"
- `aeko_list_technical_items` → "List technical items"
- `aeko_get_action_plan` → "Get action plan (Plan.md)"
- `aeko_complete_action_item` → "Complete action item"
- `aeko_get_brand_kit` → "Get brand kit"
- `aeko_update_brand_kit` → "Update brand kit"
- `aeko_list_store_integrations` → "List connected stores"
- `aeko_get_product_description` → "Get product description HTML"
- `aeko_update_product_description` → "Update product description"
- `aeko_update_product_tags` → "Update product tags"
- `aeko_update_product_meta` → "Update product SEO meta"
- `aeko_list_store_writes` → "List store write history"
- `aeko_revert_store_write` → "Revert store write"

No tool `name` or schema changed — `name` is the callable identifier
and must remain stable for existing callers.

## [0.5.1] — 2026-04-23

Patch release — docstring + module-header cleanup. No tool surface
changes. After v0.5.0 deployed, the tool descriptions shown in MCP
clients still referenced retired skills (most visibly
`aeko_get_action_plan` leading with "Internal helper for `/aeko-run-action`").
This release refreshes docstrings and list-output dispatch hints to point
at the v0.5.0 executor skills (`/aeko-update-pdp`,
`/aeko-create-content`, `/aeko-fix-technical`).

### Changed
- `aeko_get_action_plan` — first-line docstring rewritten. Now reads
  "Fetch the Plan.md for one Action or Technical item." instead of
  the old "Internal helper for `/aeko-run-action`" defensive blurb
  (the `/aeko-run-action` skill is retired). Standalone use is
  explicitly OK.
- `aeko_list_action_items` list output — "Run:" hint now branches on
  `execution_class`:
  - `store_write_artifact` → `/aeko-update-pdp <item_id>`
  - `local_content_artifact` → `/aeko-create-content <item_id>`
  - `technical_artifact` → `/aeko-fix-technical <item_id>`
  - unknown/missing → `/aeko-action-center <item_id>`
- `aeko_list_action_items` / `aeko_get_brand_kit` / `aeko_update_brand_kit`
  docstrings — replaced `/aeko-run-action` references with the v0.5.0
  executor skill names.
- `aeko_mcp/tools/store_write.py` module header — removed the retired
  `aeko_update_product_jsonld` from the tool-list comment; added
  `aeko_get_product_description` and a note that JSON-LD writes go
  through `aeko_update_product_description`.
- `aeko_mcp/templates/pdp_responsive_scaffold.html` header comment —
  updated "produced by aeko-run-action" to "produced by /aeko-update-pdp".

### Notes for MCP-client UX
- The MCP-server-level description in Claude Desktop connector settings
  is sourced from Anthropic's Directory listing, not from the `instructions`
  field in MCP code. To make AEKO show a description next to the URL in
  Claude Desktop, submit AEKO to the Directory. The `instructions` string
  in `server.py` is still used by Claude as context once connected, just
  not in the settings card.

## [0.5.0] — 2026-04-23

Major tool-layer consolidation. Driven by the full audit recorded at
`.claude/plans/tranquil-baking-iverson.md`. **53 tools in → 22 tools out**
(18 kept + 4 new + 35 deprecated, ~58% surface reduction). Companion
skill rewrites + 8 new skills in the `aeko-plugin` repo ship in lockstep.

### Added — 4 new tools

- `aeko_track_prompt(raw_prompt, ai_platform, ...)` — WRITE. Closes the
  find-prompts-to-track loop paired with `aeko_search_research_prompts`.
- `aeko_untrack_prompt(prompt_id)` — WRITE. Inverse; preserves historical
  data (sets `UserPrompts.status='untracked'`).
- `aeko_get_tracked_prompt(prompt_id, window?)` — READ_ONLY. Citation-
  forensics payload for one prompt: responses per AI platform + citation
  arrays + crawled source metadata (JSON-LD types, extracted text,
  source-analysis scores). Core primitive for `/aeko-prompt-deep-dive`,
  `/aeko-brand-competitor-analysis`, and `/aeko-create-content`.
- `aeko_get_product_description(integration_id, external_product_id)` —
  READ_ONLY. Returns raw editable Cafe24/Shopify description HTML so
  skills can read → patch → write back (e.g. `/aeko-refresh-jsonld`).

### Changed — 2 tools modified

- `aeko_get_visibility_summary(domain_id, scope?, window?)` — consolidated
  with `scope={overview,cited_sources,tracked_prompt_metrics}` + optional
  `window`. Absorbs the retired `aeko_get_cited_sources` (#8) and
  `aeko_get_metrics` (#6) surfaces behind one callable.
- `aeko_search_research_prompts` — adds `persona_type` filter (backend
  already accepted the param).

### Removed — 35 deprecated tools

Duplicates / consolidations:
- `aeko_get_metrics` (#6), `aeko_get_cited_sources` (#8),
  `aeko_get_geo_score` (#10) — consolidated into #3.

Retired backend concepts:
- `aeko_get_product_analysis` (#7) — backend product-analyses retired;
  replaced by skill `/aeko-product-competitor-analysis`.

Unused / heuristic mislabeled:
- `aeko_get_citability` (#11) — zero active skill callers.
- `aeko_score_text` (#12), `aeko_audit_content_file` (#13) — heuristic
  scorers surfaced as citation predictors; mislabeled.

Full v1 + v2 suggestion surface (8):
- `aeko_get_suggestions` (#14), `aeko_complete_suggestion` (#15),
  `aeko_get_suggestions_v2` (#16), `aeko_get_suggestion` (#17),
  `aeko_list_prompt_groups` (#18), `aeko_get_pdp_brief` (#19),
  `aeko_get_content_brief` (#20), `aeko_get_store_level_brief` (#21).
  Suggestions layer is redundant with Action Items; all routing goes
  through `aeko_list_action_items` / `aeko_list_technical_items` +
  `aeko_get_action_plan`.

Content/technical-prep wrappers (5) — skills generate artifacts directly:
- `aeko_prepare_llms_txt` (#28), `aeko_prepare_robots_txt_fix` (#29),
  `aeko_validate_llms_txt` (#30), `aeko_prepare_json_ld` (#31),
  `aeko_check_brand_entity` (#32).

PDP inspection wrappers (5) — skills use WebFetch + Plan.md target_url:
- `aeko_list_pdp_candidates` (#33), `aeko_inspect_product_page` (#34),
  `aeko_read_product_page_image` (#35), `aeko_get_pdp_optimization_brief`
  (#36), `aeko_deploy_pdp_html` (#37).

Store-write redundancy:
- `aeko_update_product_jsonld` (#40) — JSON-LD lives in description HTML;
  refresh flow reads via new `aeko_get_product_description` and writes
  via `aeko_update_product_description`.

Local filesystem wrappers (5) — covered by native `Read`/`Write`/`Glob`/`Bash`:
- `aeko_list_product_images` (#45), `aeko_read_product_image` (#46),
  `aeko_scan_content_directory` (#47), `aeko_read_content_file` (#48),
  `aeko_save_content` (#49).

Compound report + local preview + cached crawl wrappers (3):
- `aeko_prepare_report` (#50), `aeko_get_page_analysis` (#51),
  `aeko_preview_optimized_page` (#52), `aeko_fetch_source_content` (#53).

Prerequisite: plugin skills must have a filesystem MCP connector
available when running outside Claude Code. Added to
`aeko-plugin/README.md`.

### Backend dependencies

Shipped in `panomix/aeko` alongside this release:

1. `GET /api/store-integrations/{id}/products/{ext_id}/description` —
   new read endpoint for raw editable description. Dual-auth.
2. `GET /api/tracked-prompts/{prompt_id}?window=latest|7d|30d|90d` —
   new read endpoint composing `Responses` + `ResponseCitations` +
   `Sources` + `CrawledPages`. Dual-auth.
3. `POST /api/tracked-prompts` + `DELETE /api/tracked-prompts/{id}` —
   auth dep swapped from `require_user_context` to
   `require_dual_auth_with_rate_limit` so MCP opaque tokens work.

### Plugin (aeko-plugin repo) — companion changes

- Retired 8 skills: `aeko-run-action` (split into update-pdp + create-content),
  `aeko-create-own-content`, `aeko-create-external-content` (both replaced
  by `/aeko-create-content`), `aeko-competitive-pdp-input`,
  `aeko-fix-store-level` (merged into `/aeko-fix-technical`),
  `aeo-audit-local`, `competitive-research`, `create-visibility-report`.
- Added 8 skills: `/aeko-update-pdp`, `/aeko-create-content`,
  `/aeko-find-prompts-to-track`, `/aeko-prompt-deep-dive`,
  `/aeko-visibility-report`, `/aeko-brand-competitor-analysis`,
  `/aeko-product-competitor-analysis`, `/aeko-refresh-jsonld`.
- Rewrote `/aeko-action-center` to surface three categories by
  `execution_class` (Technical / PDP / Content). Rewrote
  `/aeko-fix-technical` to absorb llms.txt / robots.txt / JSON-LD
  generation with embedded spec rules (no more `prepare_*` tools).
- Revived `/aeko-update-pdp` command name — retired in v0.4.0 as a
  wrapper, ships in v0.5.0 as a real Plan.md-driven executor. The
  v0.4.0 CHANGELOG retirement table entry is updated inline in
  `aeko-plugin/README.md`.

### Note on the audit

Full decision matrix (tool-by-tool + skill-by-skill) in
`.claude/plans/tranquil-baking-iverson.md`. The operating principle
committed going forward: tools earn a slot only when they expose AEKO-
unique backend intelligence; skills earn a slot when they compress
useful workflow (AEKO-grounded or not — `/aeo-audit` is the exception).

## [0.4.0] — 2026-04-21

### Added
- `aeko_list_action_items(domain_id, status, limit, offset)` — list pending Action-tab items for a domain. Powers `/aeko-action-center` end-to-end.
- `aeko_list_technical_items(domain_id, status, limit, offset)` — list pending Technical-tab items. Shares the `GET /api/action-items?tab=technical` endpoint since the `ActionItems` table holds both tabs.
- `.github/workflows/release-bump-backend.yml` — on a published Release, opens a PR against `panomix/aeko` that bumps the `requirements.txt` pin to the new tag.
- `CHANGELOG.md` (this file).

### Changed
- Tool description hardening on 5 internal-helper tools to deprioritize standalone use in Claude's tool-selection heuristics: `aeko_get_action_plan`, `aeko_validate_llms_txt`, `aeko_get_content_brief`, `aeko_get_store_level_brief`, `aeko_get_pdp_optimization_brief`. Each description now opens with "Internal helper for `/aeko-<skill>`; not intended for standalone use." Tools remain wired for skills.
- (`aeko_check_ocr_cache`, `aeko_store_ocr_result`, `aeko_get_technical_guide` were named in the plan but don't exist in the repo — tracked as a separate audit.)
- `docs/aeko-mcp-overview.md` — reflects the Tier 1 (ingredients) / Tier 2 (meal kits) / Tier 3 (plumbing) split.

### Backend dependencies
- Requires backend `list_action_items` to use `require_dual_auth_with_rate_limit` (was `require_user_context` which fails on MCP opaque tokens). Backend change ships in the same cycle as this release.

### Plugin (aeko-plugin repo) — companion changes
- Deleted 5 deprecated wrapper skills: `aeko-update-pdp`, `aeko-optimize-pdp`, `aeo-optimize`, `generate-faq`, `generate-jsonld`.
- Deleted 3 ungrounded generic skills: `create-blog-article`, `create-social-content`, `create-marketing-materials`.
- `aeko-action-center/SKILL.md` — removed the Stage-1 "Not runnable" banner; skill now executes against live tools.

## [0.3.0] — 2026-04-17

### Added
- `action_plan` tool group: `aeko_get_action_plan`, `aeko_complete_action_item`.
- `brand_kit` tool group: `aeko_get_brand_kit`, `aeko_update_brand_kit`.

### Changed
- `aeko_complete_suggestion` now posts to `/api/suggestions/{suggestion_id}/complete` (was the non-existent `/api/suggestions/complete`); parameter renamed `suggestion_key` → `suggestion_id`.
- Tool annotations introduced via `_annotations.py` presets (`READ_ONLY`, `WRITE`, `WRITE_ONCE`, `DESTRUCTIVE`, `LOCAL_READ_ONLY`, `LOCAL_WRITE`) so Claude Desktop can offer "always allow" on read-only tools uniformly.

### Removed
- Retired `campaigns` tool group (`aeko_list_campaigns`, etc.) — the campaigns concept is deprecated product-side.
- Retired `content_recommendations` tool group for the same reason.

## [0.2.0] — prior to 2026-04-10

Earlier history predates the changelog. See git log for pre-v0.3.0 changes.

[Unreleased]: https://github.com/AEKO-Intelligence/aeko-mcp/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/AEKO-Intelligence/aeko-mcp/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/AEKO-Intelligence/aeko-mcp/releases/tag/v0.3.0
