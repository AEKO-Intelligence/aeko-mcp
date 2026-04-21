# Plan — Remove the "campaign" concept from AEKO MCP

## Context

AEKO is retiring the "campaign" concept. The MCP package currently surfaces
10 campaign-coupled tools + 1 dedicated skill across two tool files, plus
backend routes that the MCP wrapping depends on. This plan covers the MCP
cleanup and the backend coordination needed, sequenced so deleting the MCP
surface cannot break tool availability for existing users mid-deploy.

The cleanup is also a natural moment to make one scope call: whether
`aeko_fetch_source_content` (currently in `content_recommendations.py`) stays
alive as a standalone tool or goes away with the file.

## Inventory — what references campaigns today

### MCP package (`aeko-mcp`)

**Tool files** (delete or refactor):
- `aeko_mcp/tools/campaigns.py` — 4 tools
  - `aeko_list_campaigns` (GET `/api/campaigns`)
  - `aeko_get_campaign` (GET `/api/campaigns/{id}`)
  - `aeko_create_campaign` (POST `/api/campaigns`)
  - `aeko_delete_campaign` (DELETE `/api/campaigns/{id}`)
- `aeko_mcp/tools/content_recommendations.py` — 6 tools, all campaign-scoped except one
  - `aeko_get_content_recommendations` (GET `/api/campaigns/{id}/content-recommendations`)
  - `aeko_get_content_recommendation` (GET `/api/content-recommendations/{id}`)
  - `aeko_dismiss_content_recommendation` (POST `/api/content-recommendations/{id}/dismiss`)
  - `aeko_complete_content_recommendation` (POST `/api/content-recommendations/{id}/complete`)
  - `aeko_regenerate_content_recommendations` (POST `/api/campaigns/{id}/content-recommendations/regenerate`)
  - `aeko_fetch_source_content` (GET `/api/sources/content?url=...`) — **not campaign-scoped**

**Server registration:**
- `aeko_mcp/server.py:37` imports `campaigns` and `content_recommendations`

**Skills:**
- `skills/aeko-draft-from-campaign/SKILL.md` — entire skill depends on campaigns
- `skills/competitive-research/SKILL.md` and `skills/create-marketing-materials/SKILL.md` mention "campaign" in prose but don't call campaign tools — verify and drop the mentions

**README:**
- Tool group list on line ~120 lists `campaigns` and `content_recommendations` — remove

### Backend (`aeko_backend`)

- `api/routes/campaigns.py` — entire file (12+ route handlers)
- `api/routes/content_recommendations.py` — entire file
- `api/__init__.py:6` — `campaigns, content_recommendations` imports
- `api/__init__.py:129-130` — `app.include_router(campaigns.router)` + `content_recommendations.router`
- Alembic — check for campaign tables (`campaigns`, `content_recommendations`, `persona_gap_signals`?) that need drop migrations
- `api/services/plan_md.py` — check for campaign references in the prose templating
- `postgres/models.py` — `Campaign`, `ContentRecommendation`, related models — drop once migrations run
- Tests — any `test_*campaigns*` or `test_*content_recommendations*` files

### Frontend (`aeko_front`)

Out of scope for this plan; flag that pages/components referencing campaigns
will 404 against the updated backend, so the frontend cleanup must ship in
the same release window.

## Scope decision — keep or drop `aeko_fetch_source_content`

This is the one content_recommendations tool that is NOT campaign-scoped —
it fetches AEKO-cached content for an arbitrary URL. Two options:

**Option A (drop):** Delete the tool with the file. Simpler, fewer moving
parts. Any skill that relied on it loses the capability.

**Option B (keep):** Move `aeko_fetch_source_content` to a new
`aeko_mcp/tools/sources.py` before deleting `content_recommendations.py`.
Keeps the capability available for future non-campaign flows.

**Recommendation: Option B.** The tool is a thin wrapper over
`/api/sources/content`, has zero coupling to the campaign data model, and
dropping it would be a silent feature regression for users who rely on it
indirectly. Cost: one small new file + a one-line import in server.py.

Decision needed from Codex/team: confirm Option B or override to A.

## Fix Sequence

The order matters — if the MCP package drops tools before the backend still
serves them, nothing breaks (users just lose the surface). If the backend
drops routes before the MCP package stops calling them, existing deployed
plugin versions start 404'ing. So: **MCP first, then backend.**

### PR 1 (MCP) — Drop campaign surface

Files to edit:

1. `aeko_mcp/tools/campaigns.py` — **delete entire file**
2. `aeko_mcp/tools/content_recommendations.py` — **delete entire file**
3. `aeko_mcp/tools/sources.py` — **new file** containing only
   `aeko_fetch_source_content` (Option B) — READ_ONLY annotation
4. `aeko_mcp/server.py:37` — remove `campaigns, content_recommendations`
   from the import line, add `sources`
5. `skills/aeko-draft-from-campaign/` — **delete entire directory**
6. `skills/competitive-research/SKILL.md`, `skills/create-marketing-materials/SKILL.md`
   — grep for "campaign" and trim references
7. `README.md` — remove `campaigns` and `content_recommendations` from the
   tool groups list
8. `pyproject.toml`, `.claude-plugin/plugin.json`,
   `.claude-plugin/marketplace.json` — bump `0.3.4` → `0.4.0` (breaking
   change per semver — removes 9 public tools + a slash command)

Verification:

- `python3 -c "from aeko_mcp import server"` imports cleanly
- `python3 -c "from aeko_mcp import server; print(len(server.mcp._tool_manager.list_tools()))"` returns 50 (was 59, dropped 9)
- No `campaign` or `content_recommendation` substrings remain under `aeko_mcp/tools/` or `skills/`

### PR 2 (Backend) — Drop routes + data

Must land **after** PR 1 is shipped and users have updated. Files:

1. `api/__init__.py:6` — remove `campaigns, content_recommendations` imports
2. `api/__init__.py:129-130` — remove `include_router` calls
3. `api/routes/campaigns.py` — **delete**
4. `api/routes/content_recommendations.py` — **delete**
5. `api/schemas/campaigns.py`, `api/schemas/content_recommendations.py` (if
   they exist) — **delete**
6. `postgres/models.py` — remove `Campaign`, `ContentRecommendation`,
   `PersonaGapSignal` (or equivalent), `CampaignPromptGroup` etc. model
   classes once the drop migration ships
7. `alembic/versions/<new>_drop_campaigns.py` — new migration dropping the
   tables. Review FK constraints carefully — `suggestions`, `tracked_prompts`,
   and possibly `content_recommendations.source` rows could have orphan FKs
8. `api/services/plan_md.py` — check for campaign refs, strip if any
9. Tests — delete `test_campaigns*.py`, `test_content_recommendations*.py`

### PR 3 (Frontend) — Flagged, not planned here

Separate track for the Next.js app. Pages that embed
`/campaigns`/`/campaigns/[id]` need to be removed or redirected. Listed here
only so the release window is coordinated — do not ship PR 2 before PR 3.

## Release Sequence

1. **T+0 — Ship PR 1** (MCP package v0.4.0). Backend still has the routes,
   so any still-deployed 0.3.x plugin keeps working. New plugin installs
   lose the campaign surface cleanly.
2. **T+7 days (or whenever 0.4.0 is ≥90% of installs)** — ship PR 2 +
   PR 3 together. Backend drop is safe because no live MCP calls campaigns.
   Telemetry (from the PR 3 work earlier this month) already tracks tool
   usage — check the 7-day dashboard for residual calls to `aeko_list_campaigns`
   etc. before greenlighting PR 2.

## Stop-If-Broken Preconditions

Before merging PR 1:
- Confirm no production skill/workflow invokes `aeko-draft-from-campaign`
  (grep support tickets + internal usage).
- Confirm no customer documentation links to `/aeko-draft-from-campaign`.
- Decision on `aeko_fetch_source_content` (A or B) recorded above.

Before merging PR 2:
- Backend campaign usage telemetry shows < 1 request/day for 3 consecutive
  days (grep Azure logs / App Insights).
- Frontend PR 3 is ready to ship in the same window.
- Alembic drop migration reviewed for FK cascade safety (don't accidentally
  delete rows in linked tables).

If any unchecked → stop, surface, don't proceed.

## Open questions for Codex

1. **Keep `aeko_fetch_source_content`?** — Our recommendation is Option B
   (move to `sources.py`). Codex: confirm or override.
2. **Is `/api/sources/content` still alive** after campaigns are gone? The
   endpoint is in `content_recommendations.py` today; when we delete that
   file in PR 2, we need to either move the route to a standalone
   `sources.py` router or delete the endpoint entirely. If we delete it,
   the MCP-side `aeko_fetch_source_content` goes too (Option A forced).
3. **Version bump target** — is `0.4.0` right for "removed 9 tools +
   1 skill," or should this go to `1.0.0` given we're also removing the
   plugin-bundled MCP connector in the `aeko-plugin` rename work that's
   queued up? A single coordinated 1.0.0 might be cleaner than shipping a
   breaking 0.4.0 and then another breaking 1.0.0 a week later.
4. **Skill cleanup scope** — are `competitive-research` and
   `create-marketing-materials` intended to keep mentioning "campaign" as
   a concept word, or should we purge the term entirely? The MCP calls
   in those skills don't depend on the campaign API, but the user-facing
   copy might still reference campaigns in a way that confuses users once
   the feature is gone.
5. **Does removing campaigns affect `suggestions_v2`?** The v2 categorized
   model lists `pdp_update`, `own_content`, `external_content`,
   `store_level` — none are campaign-scoped — but campaign_id or
   `prompt_group_id` might be a column on underlying rows. Confirm there's
   no schema coupling that a drop migration would break.

## What this plan does NOT cover

- The `aeko-mcp` → `aeko-plugin` rename + connector decoupling (separate
  plan, queued up — consider coordinating with this release if we go 1.0.0).
- Frontend (`aeko_front`) cleanup — mentioned for release sequencing only.
- Any data migration or export of existing campaign rows before the drop
  migration — assume you have a policy decision already.
