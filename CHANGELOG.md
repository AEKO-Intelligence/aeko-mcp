# Changelog

All notable changes to `aeko-mcp` are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project adheres to semantic versioning as practiced by [PEP 440](https://peps.python.org/pep-0440/).

The backend at `panomix/aeko` pins this package by git tag in `requirements.txt` (e.g. `aeko-mcp @ git+https://github.com/AEKO-Intelligence/aeko-mcp.git@v0.4.0`). When a release here publishes, the `release-bump-backend` workflow opens a PR against the backend repo to bump the pin.

## [Unreleased]

_No unreleased changes._

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
