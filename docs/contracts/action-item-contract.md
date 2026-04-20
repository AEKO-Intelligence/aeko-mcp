# AEKO MCP Consolidation Contract — Schemas + New Tool Signatures

Source of truth for the post-consolidation AEKO MCP surface (Action, Technical, Brand Kit).
All new skills and MCP tools MUST reference this document.

Contract version pinning (semver inside date):
- Action plan: `2026-04-17.action.v1.1`
- Technical guide: `2026-04-17.technical.v1.1`

Version format: `<YYYY-MM-DD>.<tab>.v<major>.<minor>`. Additive changes (new optional keys, new optional frontmatter fields, new enum values added to existing optional fields) bump `minor` and do not break skills pinned on `major`. Breaking changes (renamed / removed / type-changed keys) bump `major` and require matching skill updates. Skills MUST gate only on `<YYYY-MM-DD>.<tab>.v<major>.` (trailing dot) — never on the full minor string.

### Changelog

**v1.1 (2026-04-20)** — additive alignment with the Phase 3 backend plan:
- `ItemStatus`: added `generating_prose`, `ready`; retired `in_progress` (no prior consumer). Async prose generation → the executable states are now `pending` (legacy / prose pre-generated at create) and `ready` (Phase 3 / prose generated asynchronously by Sonnet).
- `SubscriptionTier`: added `growth` between `starter` and `pro`.
- `WriteTarget` documented explicitly as `live | shadow | local` (previously implicit in §3.2). This is the canonical set; backend stamping MUST use these values, not `shadow | production | none`.
- §11.2 Stage-1 guidance: while `aeko_create_shadow_product` is pending, backend MUST stamp `write_mode: preview_only` + `write_target: local` on `pdp_html` items. Flip to `shadow_product` + `shadow` once the shadow endpoint is live.
- `pdp_responsive_contract`: added `faq_jsonld_required`, `review_jsonld_when_available`.
- §3.4 Citability + `[VERIFY]` baseline (executor-enforced).
- Product JSON-LD expanded to list `shippingDetails`, `hasMerchantReturnPolicy`, `speakable`, `sameAs` as SHOULD-populate.

**v1.0 (2026-04-17)** — initial consolidation contract.

## 1. Canonical Execution Model

```ts
type ItemTab = "action" | "technical";

type ExecutionClass =
  | "store_write_artifact"
  | "local_content_artifact"
  | "technical_artifact";

type WriteMode =
  | "shadow_product"
  | "append_below_existing"
  | "preview_only";

type WriteTarget =
  | "live"        // touches the live store (append_below_existing)
  | "shadow"      // non-selling draft product (shadow_product)
  | "local";      // disk only, no API call (preview_only, local_content_artifact)

type ArtifactType =
  | "pdp_html"
  | "own_store_markdown"
  | "external_media_markdown"
  | "llms_txt"
  | "robots_txt_patch"
  | "json_ld"
  | "technical_bundle";

type ItemStatus =
  | "pending"             // legacy / prose pre-generated at create time; executable
  | "generating_prose"    // Phase 3: Sonnet is generating the prose body
  | "ready"               // Phase 3: prose generated, plan is executable
  | "completed"
  | "failed"
  | "dismissed";

type SubscriptionTier =
  | "starter"
  | "growth"
  | "pro"
  | "enterprise";
```

Dispatch rule: MCP branches on `execution_class`, NOT on UI action type.

Executable statuses: the skill runs when `status ∈ {pending, ready}`. `generating_prose` → the skill halts with a "plan is still being generated, retry in a moment" message (409 from the backend).

## 2. Shared Item Summary

Used by both list endpoints.

```ts
interface AekoItemSummary {
  id: string;
  tab: ItemTab;
  status: ItemStatus;
  title: string;
  priority: "critical" | "high" | "medium" | "low";
  execution_class: ExecutionClass;
  artifact_type: ArtifactType;
  domain_id: string;
  target_url?: string;
  product_id?: string;
  integration_id?: string;
  write_mode?: WriteMode;
  channels?: string[];
  keywords?: string[];
  persona_label?: string;
  updated_at: string;
  created_at: string;
  preview: string;
}
```

## 3. Action Plan Document (Plan.md)

`aeko_get_action_plan(item_id)` returns a single markdown string — the Plan.md for the item. The payload is **dual-format**: YAML frontmatter (dispatch surface) plus a Sonnet-authored prose body (narrative guidance).

### 3.1 Authoring split

- **Backend app layer** stamps the YAML frontmatter at response-assembly time from deterministic DB columns. Sonnet MUST NOT author any frontmatter key.
- **Sonnet** authors ONLY the prose body, which is stored in the `plan_prose` column. The prose MUST NOT re-declare frontmatter values. Field-name references (e.g. `` `forbidden` ``) are required in the **Acceptance criteria** section (the machine-oriented self-check) and optional elsewhere — narrative sections MAY paraphrase in the reader's language ("피해야 할 표현 목록" / "the list of words to avoid") to keep prose readable.

The skill (`aeko-run-action`) parses frontmatter for dispatch and reads prose for how to write the artifact. The two surfaces must not drift.

**Frontmatter is machine-only.** Executor skills MUST NOT echo the raw frontmatter block to the user in chat. Render a short, human-friendly header (domain, artifact type, write mode, persona) and show only the prose body to the user. The full Plan.md is available if the user asks for it explicitly.

**Prose language contract.** The prose body MUST be written in the language indicated by `target_language` (ISO-639-1). If `target_language` is absent, fall back to the primary language of `target_country`. If both are absent, default to English. Machine keys stay in English inside prose (e.g. `` `forbidden` ``) regardless of prose language.

### 3.2 Frontmatter keys (required unless marked optional)

| Key | Type | Notes |
|---|---|---|
| `item_id` | string | canonical identifier |
| `contract_version` | string | `"2026-04-17.action.v<major>.<minor>"`, e.g. `"2026-04-17.action.v1.1"` |
| `tab` | `"action"` | literal |
| `status` | `ItemStatus` | skill refuses to run unless `status ∈ {pending, ready}` (see §1) |
| `execution_class` | `ExecutionClass` | ONLY dispatch key the executor relies on |
| `artifact_type` | `ArtifactType` | narrows within a class |
| `write_mode` | `WriteMode` (optional) | required when `execution_class == "store_write_artifact"` |
| `domain_id` | string | |
| `target_url` | string (optional) | |
| `product_id` | string (optional) | |
| `integration_id` | string (optional) | required for `store_write_artifact` |
| `source_product_id` | string (optional) | used by `shadow_product` flows |
| `target_country` | string (optional) | ISO-3166-1 alpha-2 |
| `target_language` | string (optional) | ISO-639-1 |
| `channels` | string[] | empty array allowed, never omitted |
| `keywords` | string[] | empty array allowed, never omitted |
| `prompts_to_rank_on` | string[] | empty array allowed, never omitted |
| `persona_label` | string (optional) | |
| `requires_ocr_ingest` | boolean | |
| `requires_brand_kit` | boolean | |
| `responsive_html_required` | boolean | |
| `brand_kit_snapshot_version` | string (optional) | present if `requires_brand_kit`; ISO-8601 |
| `pdp_ocr_cache_key` | string (optional) | present for PDP items with a prior OCR run |
| `output_artifact_format` | `"html"` \| `"markdown"` \| `"json"` \| `"txt"` | |
| `sections_required` | string[] | empty array allowed, never omitted |
| `must_include` | string[] | empty array allowed, never omitted |
| `forbidden` | string[] | empty array allowed, never omitted |
| `tier_required` | `SubscriptionTier` (optional) | Minimum subscription tier for this item to execute. Absent → Starter (all users). Skill refuses to execute and suggests an upgrade path when the caller's tier is below this. See §1 for enum values. |
| `write_target` | `WriteTarget` (optional) | Redundant safety signal for write scope. `live` = touches the live store; `shadow` = non-selling draft; `local` = disk only. Skill double-checks this against `write_mode` — if they disagree, stop and surface the mismatch. Backend MUST use these exact values (not `production`, not `none`). |
| `generated_at` | string | ISO-8601, timestamp of frontmatter assembly |

For PDP items (`execution_class == "store_write_artifact"` AND `artifact_type == "pdp_html"`), the frontmatter additionally includes a nested `pdp_responsive_contract` mapping (the dotted paths below are **documentation notation**, NOT literal YAML keys — render as a nested mapping):

| Path | Type | Notes |
|---|---|---|
| `pdp_responsive_contract.mobile_first` | `true` | |
| `pdp_responsive_contract.no_javascript` | `true` | "No executable JavaScript." `<script type="application/ld+json">` blocks are explicitly permitted (they carry inert structured data, not code) and are the primary AEO signal. `<script>` tags with any other `type` attribute (or no `type`) are forbidden. `onclick`/`on*` attributes are forbidden. |
| `pdp_responsive_contract.alt_text_required` | `true` | |
| `pdp_responsive_contract.no_fixed_width_containers` | `true` | |
| `pdp_responsive_contract.semantic_sections_required` | `true` | |
| `pdp_responsive_contract.css_mode` | `"inline_or_scoped_style_block_only"` | |
| `pdp_responsive_contract.json_ld_required` | `true` | A `<script type="application/ld+json">` block with a valid schema.org `Product` object MUST be embedded in the rendered HTML. Required: `@context`, `@type: Product`, `name`, `description`, `image`, `brand.name`. SHOULD-populate-when-available: `offers` (`price`, `priceCurrency`, `availability`, `url`), `sku`, `gtin13`, `mpn`, `aggregateRating`, `review`, `shippingDetails`, `hasMerchantReturnPolicy`, `speakable` (with CSS selectors for key content), `sameAs` (prefer Wikipedia > Wikidata > LinkedIn > YouTube). When a SHOULD field's data is missing, omit the key entirely — never emit empty strings, `null`, or fabricated values. For human-visible text (description, offers.price when partially known), use the `[VERIFY: <field>]` marker convention (see §3.4). |
| `pdp_responsive_contract.faq_jsonld_required` | `true` | When `faq` appears in `sections_required`, a second `<script type="application/ld+json">` block with a valid `FAQPage` schema object MUST be embedded. Each `mainEntity` entry is a `Question` with a non-empty `acceptedAnswer.Answer.text`. Minimum 3 Q&A pairs; pairs MUST match the visible FAQ HTML in the same document (no JSON-LD Q&As without a visible counterpart). |
| `pdp_responsive_contract.review_jsonld_when_available` | `true` | If crawled/OCR data surfaces real customer reviews (text + rating + author, even partial), emit a third `<script type="application/ld+json">` block: `AggregateRating` on the Product object plus up to 5 top `Review` objects. If no review data is available, skip silently — do NOT fabricate reviews. |

YAML rendering:

```yaml
pdp_responsive_contract:
  mobile_first: true
  no_javascript: true
  alt_text_required: true
  no_fixed_width_containers: true
  semantic_sections_required: true
  css_mode: inline_or_scoped_style_block_only
  json_ld_required: true
  faq_jsonld_required: true
  review_jsonld_when_available: true
```

YAML serialization rules: stable key order (above), empty arrays serialized as `[]` not omitted, booleans canonical (`true`/`false`), timestamps ISO-8601 with `Z` suffix.

### 3.3 Prose body structure (Sonnet output)

The prose body is concatenated after the closing `---` of the frontmatter with a single blank line. Recommended sections (Sonnet generates these; heading text is illustrative):

1. `# Plan: <short artifact headline>`
2. `## Why this plan exists` — 1–2 paragraphs on the visibility gap and the strategy.
3. `## Target outcome` — 3–5 bullets of plain-language success criteria.
4. `## Content guidance` — narrative how-to (voice, structure, AEO framing).
5. `## Brand voice summary` — who the reader is, what sounds on/off brand.
6. `## Reference examples` — references Brand Kit sample URLs by name.
7. `## Research prompts to cover` — what each prompt in `prompts_to_rank_on` is actually asking.
8. `## What to avoid` — qualitative traps (ad-law, platform quirks). Hard forbidden strings live in `forbidden`; this is the *why*.
9. `## Acceptance criteria` — self-check bullets for the executor before completing.

Prose body rules:
- No YAML, no `---` fences, no bulleted re-declarations of frontmatter values.
- Narrative sections (Why / Target outcome / Content guidance / Brand voice / References / Research prompts / What to avoid) MAY paraphrase field references in the prose language for readability.
- Acceptance criteria section MUST reference fields by their backtick-quoted English name (e.g. "cover every section listed in `sections_required`") so the executor can pattern-match the check.
- Never inline Brand Kit bodies; reference them by their contract field name (e.g. `sample_urls[0]`) or by URL.

### 3.4 Citability + [VERIFY] baseline (executor-enforced)

Every `pdp_html` and `own_store_markdown` artifact MUST apply these citability patterns regardless of what the prose says. The prose `## Content guidance` section SHOULD teach these patterns explicitly; if it doesn't, the executor applies them as a baseline so output quality doesn't regress to vague marketing copy.

**Passage structure:**
- Product copy passages: 80-167 words per passage.
- Blog / article sections: 134-167 words per section.
- Every paragraph is self-contained and extractable without surrounding context.

**Self-containment:**
- Name the subject explicitly in every paragraph. Never open with "it", "this", "these", "그", "이것", "저".
- Use the product or brand name naturally 2-3 times per section (not stuffed).
- Avoid "as mentioned above", "see below", "see previous section".

**Definition patterns (trigger AI citation):**
- Open each section with a direct 1-2 sentence answer before supporting detail.
- Use "X is a Y that Z" structures for core claims.
- Place the most important information in the first 40-60 words of each section.

**Statistical density:**
- Include specific numbers, dimensions, percentages, material names, year references.
- Comparative claims MUST carry a number ("30% lighter than X") or be dropped.

**`[VERIFY: <field>]` marker convention:**
When the executor needs a factual value (price, SKU, dimension, review count, etc.) and it's absent from the OCR payload, StoreProducts row, Brand Kit, and prose, the executor MUST NOT fabricate. Instead, emit `[VERIFY: <field>]` inline. Examples:
- Visible HTML: `무게는 [VERIFY: weight_grams]g입니다.`
- JSON-LD: omit the missing key entirely (do not emit `"sku": "[VERIFY: sku]"` — schema validators reject non-scalar strings for known property types).

The user summary in the executor skill's Step 6 lists every `[VERIFY: ...]` marker so the user knows exactly what to fill in before going live.

### 3a. OCR cache payload (optional, used when the frontmatter `pdp_ocr_cache_key` is set)

```ts
interface AekoOcrCacheEntry {
  ocr_cache_key: string;
  product_id: string;
  cached_at: string;                     // ISO timestamp
  images: Array<{
    index: number;
    src: string;
    width: number;
    height: number;
    text: string;                        // extracted text, verbatim, paragraph order preserved
    extracted_at: string;
  }>;
}
```

## 4. Technical Guide Document (guide.md)

`aeko_get_technical_guide(item_id)` returns a single markdown string — the guide.md for the item. Same dual-format as Plan.md: YAML frontmatter (dispatch surface) plus a Sonnet-authored prose body stored in the `guide_prose` column.

### 4.1 Authoring split

Identical rule to §3.1: backend app layer stamps frontmatter from DB columns; Sonnet authors only the prose body and references fields by name; frontmatter is machine-only and not echoed to the user; prose language follows `target_language` on the parent item (technical items inherit language from the domain when not set).

### 4.2 Frontmatter keys (required unless marked optional)

| Key | Type | Notes |
|---|---|---|
| `item_id` | string | |
| `contract_version` | string | `"2026-04-17.technical.v<major>.<minor>"`, e.g. `"2026-04-17.technical.v1.1"` |
| `tab` | `"technical"` | literal |
| `status` | `ItemStatus` | skill refuses to run unless `status ∈ {pending, ready}` |
| `execution_class` | `"technical_artifact"` | literal for this document |
| `artifact_type` | `"llms_txt"` \| `"robots_txt_patch"` \| `"json_ld"` \| `"technical_bundle"` | |
| `deploy_mode` | `"artifact_only"` \| `"deploy_if_supported"` | |
| `domain_id` | string | |
| `target_url` | string (optional) | |
| `site_base_url` | string (optional) | required for `robots_txt_patch` |
| `requires_brand_kit` | boolean | |
| `brand_kit_snapshot_version` | string (optional) | present when `requires_brand_kit` |
| `output_artifact_format` | `"txt"` \| `"json"` \| `"markdown"` | |
| `sections_required` | string[] | empty array allowed, never omitted |
| `must_include` | string[] | empty array allowed, never omitted |
| `forbidden` | string[] | empty array allowed, never omitted |
| `validation_hints` | string[] (optional) | e.g. schema.org type name, rel values, etc. |
| `tier_required` | `SubscriptionTier` (optional) | Minimum subscription tier. Same semantics as §3.2. See §1 for enum values. |
| `generated_at` | string | ISO-8601 |

Serialization rules identical to §3.2.

### 4.3 Prose body structure (Sonnet output)

Recommended sections:

1. `# Guide: <artifact headline>`
2. `## Why this fix matters` — what the AI-search / crawler gap is.
3. `## Target artifact` — what shape the output takes, in plain language.
4. `## Content guidance` — narrative instructions (what to say, how to structure).
5. `## Validation approach` — how the executor should self-check before completing; for `deploy_if_supported`, what the deploy verifies.
6. `## What to avoid` — common Korean/Cafe24/Shopify-specific pitfalls.

Prose body rules identical to §3.3: narrative sections may paraphrase; a terminal acceptance-criteria section (if present) references fields by their backtick-quoted English name.

## 5. Brand Kit

```ts
interface AekoBrandKit {
  domain_id: string;
  snapshot_version: string;
  updated_at: string;

  brand_description?: string;
  persona?: string;
  competitors: string[];
  viewpoint?: string;
  writing_style?: string;
  tone?: string;
  writing_guidelines: string[];
  cta_text?: string;
  cta_link?: string;

  sample_urls: string[];
  sample_headlines: string[];
  sample_bodies: string[];

  metadata?: {
    locale?: string;
    target_countries?: string[];
    target_languages?: string[];
    account_tier?: SubscriptionTier;                    // Used by executor skills for tier_required gating. See §1.
    billing_url?: string;                                // Locale-aware billing URL; consumed by tier-gate copy.
  };
}

interface AekoBrandKitUpdate {
  brand_description?: string;
  persona?: string;
  competitors?: string[];
  viewpoint?: string;
  writing_style?: string;
  tone?: string;
  writing_guidelines?: string[];
  cta_text?: string;
  cta_link?: string;
  sample_urls?: string[];
  sample_headlines?: string[];
  sample_bodies?: string[];
}
```

Patch semantics: omitted fields remain unchanged. Every update bumps `snapshot_version`.

## 6. Item Completion

```ts
interface AekoCompleteItemRequest {
  completed_via: "mcp";
  status: "completed";
  artifact_summary?: string;
  artifact_paths?: string[];
  write_result?: {
    mode?: WriteMode;
    audit_id?: string;
    admin_url?: string;
    created_product_id?: string;
  };
}
```

## 7a. Store Write Response (shared by direct-write tools)

In Stage 1, the existing direct-write tools (`aeko_update_product_description`, `aeko_update_product_jsonld`, `aeko_update_product_tags`, `aeko_update_product_meta`) MUST return this structured response so the skill can build consistent `write_result` payloads for `aeko_complete_item`:

```ts
interface AekoStoreWriteResponse {
  status: "success";
  platform: "cafe24" | "shopify";
  integration_id: string;
  external_product_id: string;
  mode: "replace" | "append_below_existing";
  field_updated: "description_html" | "json_ld" | "tags" | "meta";
  admin_url: string;
  audit_id: string;
  revert_supported: boolean;
}
```

If Stage 1 ships the existing tools still returning markdown-only, `aeko-run-action` handles the gap by setting `write_result.audit_id = null` and surfacing a warning to the user: "audit_id unavailable — revert is not supported for this write."

## 7. Shadow Product Response

```ts
interface AekoShadowProductResponse {
  status: "success";
  platform: "cafe24" | "shopify";
  integration_id: string;
  source_product_id: string;
  created_product_id: string;
  selling: false;
  title: string;
  title_suffix: string;
  admin_url: string;
  audit_id: string;
  revert_supported: boolean;
}
```

If any required field is missing, `aeko-run-action` MUST refuse to mark the item complete and surface the missing field to the user.

## 8. MCP Tool Signatures (new surface)

```python
@mcp.tool()
def aeko_list_action_items(
    domain_id: str,
    status: str = "pending",
    limit: int = 20,
    offset: int = 0,
) -> str:
    """List Action-tab items for a domain."""
    # Backend: GET /api/action-items?domain_id=<uuid>&status=pending&limit=20&offset=0

@mcp.tool()
def aeko_list_technical_items(
    domain_id: str,
    status: str = "pending",
    limit: int = 20,
    offset: int = 0,
) -> str:
    """List Technical-tab items for a domain."""
    # Backend: GET /api/technical-items?domain_id=<uuid>&status=pending&limit=20&offset=0

@mcp.tool()
def aeko_get_action_plan(item_id: str) -> str:
    """Fetch the Action item Plan.md (YAML frontmatter + Sonnet prose)."""
    # Backend: GET /api/action-items/{item_id} -> Plan.md string (see §3)
    # Response = "---\n" + yaml_frontmatter + "\n---\n\n" + plan_prose

@mcp.tool()
def aeko_get_technical_guide(item_id: str) -> str:
    """Fetch the Technical item guide.md (YAML frontmatter + Sonnet prose)."""
    # Backend: GET /api/technical-items/{item_id} -> guide.md string (see §4)
    # Response = "---\n" + yaml_frontmatter + "\n---\n\n" + guide_prose

@mcp.tool()
def aeko_get_domain_info(domain_id: str) -> str:
    """Domain details + AI-readiness infrastructure status (llms.txt, robots.txt AI blockers, JSON-LD, sitemap)."""
    # Backend: GET /api/domains/{domain_id}
    # Used by: aeko-action-center (domain confirmation), aeko-brand-kit (domain lookup).

@mcp.tool()
def aeko_get_brand_kit(domain_id: str) -> str:
    """Fetch the live Brand Kit for a domain."""
    # Backend: GET /api/brand-kit/{domain_id} -> AekoBrandKit

@mcp.tool()
def aeko_update_brand_kit(
    domain_id: str,
    fields: dict,
) -> str:
    """Patch Brand Kit fields for a domain."""
    # Backend: PUT /api/brand-kit/{domain_id} body: AekoBrandKitUpdate -> AekoBrandKit

@mcp.tool()
def aeko_complete_item(
    item_id: str,
    artifact_summary: str = "",
    artifact_paths: list[str] | None = None,
    write_result: dict | None = None,
) -> str:
    """Mark an Action or Technical item complete."""
    # Backend: POST /api/items/{item_id}/complete body: AekoCompleteItemRequest

@mcp.tool()
def aeko_create_shadow_product(
    integration_id: str,
    source_product_id: str,
    description_html: str,
    title_suffix: str = "[AEKO Draft]",
) -> str:
    """Create a non-selling shadow copy of a product with new description HTML."""
    # Backend: POST /api/store-integrations/{integration_id}/products/{source_product_id}/shadow
    # Response: AekoShadowProductResponse

@mcp.tool()
def aeko_get_product_description(
    integration_id: str,
    external_product_id: str,
) -> str:
    """Fetch the current editable description HTML for a store product.
    Required for append_below_existing write mode so aeko-run-action can
    preserve the existing HTML deterministically instead of scraping the
    rendered page. Returns raw description_html as stored in Cafe24/Shopify,
    plus title + current selling flag so the skill can render a full summary.
    """
    # Backend: GET /api/store-integrations/{integration_id}/products/{external_product_id}/description
    # Response: { description_html: string, title: string, selling: boolean }

@mcp.tool()
def aeko_check_ocr_cache(ocr_cache_key: str) -> str:
    """Optional. Return cached OCR payload for a PDP snapshot, if present.
    Skill calls this before iterating images so repeat runs over the same
    product snapshot short-circuit the vision loop. If the backend does not
    wire this endpoint, the tool returns a clear "not available" marker and
    the skill falls back to live OCR.
    """
    # Backend: GET /api/ocr-cache/{ocr_cache_key}  -> AekoOcrCacheEntry | 404

@mcp.tool()
def aeko_store_ocr_result(ocr_cache_key: str, payload: dict) -> str:
    """Optional. Persist an OCR payload for future runs over the same snapshot.
    payload shape: AekoOcrCacheEntry (without ocr_cache_key — backend takes it from the path).
    """
    # Backend: PUT /api/ocr-cache/{ocr_cache_key}  body: AekoOcrCacheEntry
```

All MCP tools return markdown strings for human-facing output.

## 9. Defaults and Invariants

- `aeko_get_action_plan` and `aeko_get_technical_guide` each return ONE Plan.md / guide.md string assembled from one DB row. MCP never reconstructs plan state from multiple endpoints.
- Plan.md / guide.md are dual-format: YAML frontmatter (app-layer stamped) + prose body (Sonnet-authored). Sonnet MUST NOT author frontmatter; prose MUST reference fields by name, never by value.
- `aeko_update_brand_kit` is patch semantics. Omitted fields unchanged. Every update bumps `snapshot_version`.
- `aeko_complete_item` always posts `completed_via="mcp"`, `status="completed"`.
- `write_mode` lives on the item contract (frontmatter), not as a runtime flag to the skill.
- `execution_class` is the only dispatch key the executor relies on.
- `brand_kit_snapshot_version` is mandatory in frontmatter whenever `requires_brand_kit: true`, so plans can prove freshness.

## 10. Contract Tests

- `aeko_list_action_items` / `aeko_list_technical_items` return only their own tab's items; each summary includes `execution_class`, `artifact_type`, `preview`.
- `aeko_get_action_plan` output starts with `---\n`, has a closing `\n---\n` before a blank line and the first `#` header; YAML between the fences parses; every required frontmatter key from §3.2 is present.
- `aeko_get_action_plan` for a PDP item → frontmatter has `requires_ocr_ingest: true`, `responsive_html_required: true`, `write_mode` set, and the `pdp_responsive_contract.*` block present.
- `aeko_get_action_plan` for a non-PDP content item → frontmatter has `execution_class: local_content_artifact` and NO `pdp_responsive_contract.*` keys.
- `aeko_get_technical_guide` → frontmatter has `execution_class: technical_artifact`; `validation_hints` present when applicable; every required §4.2 key present.
- Frontmatter / prose drift test: for any Plan.md, no line in the prose body equals `---` (no stray closing fence); no bullet *line* in the prose body equals, verbatim (after stripping leading bullet markers and whitespace), any string listed in `must_include` or `forbidden`. Whole-line equality only — legitimate narrative references to those values within a sentence are permitted.
- `aeko_get_brand_kit` → `aeko_update_brand_kit` round-trip does not drop unspecified fields.
- `aeko_complete_item` accepts both store-write and non-store-write completions.
- `aeko_create_shadow_product` response has `created_product_id`, `admin_url`, `selling=false`, `audit_id`; missing any → contract breach.

## 11. Assumptions

- MCP tools return markdown for human-facing output (repo convention). Plan.md / guide.md are dual-format markdown (YAML frontmatter + prose body).
- List endpoints, Brand Kit, completion, store-write, shadow-product and OCR-cache endpoints return structured JSON in the shapes above; MCP renders, does not invent state.
- `item_id` is the canonical identifier for both Action and Technical flows. Legacy `suggestion_key` / campaign IDs are NOT reused.

### 11.1 Frontmatter parsing rules

- Clients MUST use YAML 1.2 safe-load semantics (e.g. Python `yaml.safe_load`, not `yaml.load`). No custom tags, no Python object deserialization.
- Duplicate keys at the same mapping level → parse failure. Skills MUST NOT attempt recovery.
- The opening fence is a line containing exactly `---` (trailing whitespace tolerated). The closing fence is the next line containing exactly `---` at column 0. Content between fences is the YAML document.
- BOM (U+FEFF) at file start MUST be stripped before fence detection.
- Prose body starts on the line after the closing fence (trim a single leading blank line if present).
- Unknown frontmatter keys are IGNORED by executors — the contract reserves the right to add new optional keys under the same major version without breaking skills.

### 11.2 Stage-1 ship checklist (backend tools referenced but not yet wired)

Skills reference these tools; Stage-1 backend work must land them (or skills must degrade cleanly with clear messaging until they do):

- `aeko_get_action_plan` / `aeko_get_technical_guide` — MUST assemble frontmatter from DB columns + prose body and return a single markdown string.
- `aeko_list_action_items` / `aeko_list_technical_items` — MUST return tab-scoped summaries.
- `aeko_get_brand_kit` / `aeko_update_brand_kit` — MUST exist for Brand Kit checks to work. `metadata.account_tier` and `metadata.billing_url` MUST be populated for the `tier_required` gate + upgrade copy to resolve correctly; if absent, skills fall through to the backend as the authoritative gate (see §3.2).
- `aeko_complete_item` — MUST accept both store-write and non-store-write completions.
- `aeko_create_shadow_product` — MUST return `AekoShadowProductResponse` with all six provenance fields.
- `aeko_get_product_description` — required for `append_below_existing` write mode; until wired, `aeko-run-action` aborts that mode with a clear user message (per skill Step 3B.3).
- `aeko_update_product_description` — MUST return `AekoStoreWriteResponse` (§7a); until upgraded, skill flags `audit_id: null` and warns revert is unavailable.
- `aeko_check_ocr_cache` / `aeko_store_ocr_result` — optional per §8; skills degrade to live OCR when absent.

Any skill referencing a Stage-1 tool that is absent at runtime MUST stop with "<tool> is not yet available — required for this item's write_mode/artifact_type" rather than producing partial output.

**Frontmatter keys added across v1.x** — backend stamping responsibility:
- `tier_required` — set from the item's source policy. `append_below_existing` items SHOULD stamp `tier_required: "growth"` (live-store writes are Growth+); `shadow_product` items SHOULD stamp `tier_required: "starter"`. Optional; absent = Starter-accessible.
- `write_target` — second safety signal, MUST agree with `write_mode` per the pairing rule in §3.2, and MUST use the canonical values `live | shadow | local` (not `production` / `none`). Optional but strongly recommended so the skill can refuse cleanly on misconfigured items.
- `faq_jsonld_required` / `review_jsonld_when_available` — see §3.2 for semantics.

**Stage-1 write-mode guidance (while `aeko_create_shadow_product` is pending):**
The canonical PDP default is `write_mode: shadow_product` + `write_target: shadow`, but until the shadow endpoint ships, backend MUST stamp `write_mode: preview_only` + `write_target: local` on `pdp_html` items. The skill handles `preview_only` end-to-end today (generate HTML → open in browser → tell user to copy-paste into Cafe24). Flipping the default to `shadow_product` is a one-line backend change once the endpoint lands; no MCP release needed.

**Async-prose-generation status handling (v1.1):**
Backend flow for Phase 3 items: insert row with `status: generating_prose` inside the same transaction that enqueues the Sonnet prose job. On Sonnet success → flip to `status: ready`. On failure → `status: failed` + populate `last_error`. The MCP plan endpoint returns `409 Conflict` when `status == generating_prose` with a body like `"status: generating_prose — retry in a moment"`; skills render this verbatim to the user and stop. Legacy flow where prose is pre-generated at create time (no async job) writes `status: pending` directly; skills accept both states.
