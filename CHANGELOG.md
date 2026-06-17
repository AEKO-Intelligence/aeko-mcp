# Changelog

All notable changes to `aeko-mcp` are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project adheres to semantic versioning as practiced by [PEP 440](https://peps.python.org/pep-0440/).

The backend at `panomix/aeko` pins this package by git tag in `requirements.txt` (e.g. `aeko-mcp @ git+https://github.com/AEKO-Intelligence/aeko-mcp.git@v0.4.0`). When a release here publishes, the `release-bump-backend` workflow opens a PR against the backend repo to bump the pin.

## [0.10.0] — 2026-06-17

### Removed

- Brand kit MCP tools (`aeko_get_brand_kit`, `aeko_get_brand_kit_by_id`, `aeko_list_brand_kits`, `aeko_update_brand_kit`); `aeko_request_media_upload` + store-write image upload now key by `domain_id` instead of `brand_kit_id`.

### Added

- `aeko_get_brand_kit_by_id(kit_id)` and `aeko_list_brand_kits(domain_id=None, status=None)` so executor skills can resolve the exact Brand Kit selected in the AEKO app instead of relying only on active-by-domain lookup. *(Superseded by the brand-kit removal above — these tools no longer ship.)*

### Changed

- `aeko_request_media_upload` no longer requires `brand_kit_id` — a Brand Kit is **optional** for publishing to aeko.shop. When the brand has no kit, pass `item_id` (preferred — the action-item id, resolves the verified-domain identity) or `domain_id`. `brand_kit_id` is now an optional keyword; the required hashing/file fields move ahead of the identity inputs in the signature. The backend resolves a kit- or domain-derived brand and 400s if no identity input is usable.

### Fixed

- `aeko_request_media_upload` now sends `brand_kit_id` to `/api/aeko-shop/media/presign`; the previous `brand_id` field was ignored by the backend schema and forced an active-kit fallback.

### Docs

- README: document Gemini CLI as a first-class DCR client alongside Claude Code and Codex CLI. Adds `gemini mcp add --transport http ...` to the CLI clients section plus the equivalent `~/.gemini/settings.json` `mcpServers` block (`httpUrl` form), and notes the consolidated `url` + `type: "http"` form from google-gemini/gemini-cli#13762. Authentication section now calls out Gemini CLI's `dynamic_discovery` OAuth provider, which reads `/.well-known/oauth-authorization-server` on first connect. No code change; package version unchanged.

## [0.8.1] — 2026-05-18

Patch — restores backend worker boot. `aeko_mcp/tools/crawl.py` and `aeko_mcp/tools/own_content.py` (introduced in the v0.6 line) and `aeko_mcp/tools/media_upload.py` (introduced in v0.7) each started with `from __future__ import annotations`, which turns every parameter annotation into a string at runtime. Older `mcp` SDK releases within the declared range `mcp>=1.11.0,<1.16.0` (confirmed against `mcp==1.11.0`) have a `Tool.from_function` that calls `issubclass(param.annotation, Context)` without resolving string annotations — so the first `@mcp.tool` decoration in any affected module raises `TypeError: issubclass() arg 1 must be a class` and the embedded backend worker (panomix/aeko) fails to boot. The bug was carried into v0.8.0 and only reached production this release because earlier minor versions weren't tagged.

### Fixed

- `aeko_mcp/tools/crawl.py`, `aeko_mcp/tools/own_content.py`, `aeko_mcp/tools/media_upload.py` no longer use PEP 563 deferred annotations. The decorated tool signatures use only plain class annotations (`str`, `bool`, `int`) so the future import was load-bearing for nothing; PEP 585/604 syntax in those modules only appears in private helper return types and local-variable annotations, which `inspect.signature()` doesn't introspect. Reproduced + verified the fix in a clean venv against `mcp==1.11.0` (crash → `boot OK`).

## [0.8.0] — 2026-05-18

Minor — adds a dedicated text→UUID resolver for `prompts_to_rank_on` so the `aeko-create-content` skill no longer has to grep-parse `aeko_get_tracked_prompts` markdown. The 0.6.1 patch only fixed the ID column for English rows; `prompt_ko` still renders on a separate row without the ID column, which is why text-resolution kept failing for Korean Plan.md inputs and forcing the "인용 포렌식 없이 계속 진행 / UUID 확인 후 재실행" prompt.

### Added

- `aeko_resolve_prompts_by_text(texts: list[str])` — calls
  `GET /api/tracked-prompts` once and returns one deterministic line
  per input: either `"text" → `uuid` (matched_via: prompt_en | prompt_ko | raw_prompt)`,
  `` `uuid` → already a UUID `` for inputs that already match the UUID
  regex, or `"text" → UNRESOLVED`. Normalization is server-side (NFC
  + lowercase + strip punctuation + collapse whitespace), so Korean /
  CJK inputs match cleanly without the caller having to align columns
  across markdown rows. When backend rows arrive with no `id` field,
  the response surfaces a one-line warning rather than silently
  dropping them — exposes the backend regression that the 0.6.1
  formatter patch worked around.

## [0.6.1] — 2026-04-30

Patch — restores UUID visibility on tracked-prompt list output so skills can resolve `prompts_to_rank_on` text entries to UUIDs without a separate detail call per prompt.

### Changed

- `aeko_get_tracked_prompts` formatter (`_format_tracked_prompts`) now
  includes an `ID` column in the markdown table. The backend has always
  returned `id` per row; the formatter was dropping it, which broke the
  text-to-UUID resolution path the `aeko-create-content` skill needs when
  a Plan's `prompts_to_rank_on` is authored as raw text rather than UUIDs.
  Trailer line now points the caller at `aeko_get_tracked_prompt` for full
  forensics instead of the previous generic "use individual prompt IDs."

## [0.6.0] — 2026-04-30

Minor — adds two new tools and expands tracked-prompt forensics, primarily to support the `aeko-create-content` skill quality lift in `aeko-plugin`.

### Added

- `aeko_crawl_url(url, force_refresh=False)` — re-fetches a URL through AEKO's
  crawler and returns title, meta description, canonical URL, OG fields,
  heading hierarchy, paragraph / list / image stats, raw JSON-LD blocks
  (rendered as fenced JSON code blocks for skill copy-paste), microdata
  `itemtype` values, and citability score. Replaces `WebFetch` whenever a
  skill needs JSON-LD or schema-parity signal — `WebFetch` strips
  `<script type="application/ld+json">` during HTML→markdown conversion.
- `aeko_list_own_content(domain_id, type, limit)` — lists the brand's own
  on-site content (blog posts, PDPs, or both). Counterpart to
  `aeko_get_tracked_prompt` for the brand's own-domain side; lets content
  skills mimic in-house tone, dedupe against existing pages, and anchor
  cross-channel narratives. Returns `[{url, title, summary, content_type,
  last_seen}]`.

### Changed

- `aeko_get_tracked_prompt` formatter now surfaces two fields the backend
  was already sending but the formatter was dropping:
  - **Per-citation `crawl.extracted_text`** (capped at 600 chars,
    whitespace-collapsed) so skills can tone-match against the cited
    source body.
  - **Per-response full body** via `response_body_en` (capped at 2500
    chars). Falls back to the existing 300-char `response_snippet_en`
    when the backend hasn't shipped the field yet — old payloads continue
    to render with the legacy `**Snippet**` label.

### Backend dependency notes

This release ships the MCP-side contract for two new backend routes that
do not exist yet:

- `GET /api/crawl?url=&force_refresh=` — the `aeko_crawl_url` tool's
  backing endpoint. Reuses the existing crawl/audit pipeline that already
  populates `aeko_get_tracked_prompt`'s per-citation `crawl` payload;
  exposes it against arbitrary URLs.
- `GET /api/domains/{domain_id}/own-content?type=&limit=` — the
  `aeko_list_own_content` tool's backing endpoint.
- `crawl.extracted_text` and `response_body_en` need to be added to the
  `/api/tracked-prompts/{id}` serializer in `panomix/aeko`.

Until these land in the backend, both new tools surface the standard
"Resource not found" message, and the `aeko-create-content` skill's
graceful-degrade paths in §3.4 / §3.6 / Error paths absorb the failure.

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
