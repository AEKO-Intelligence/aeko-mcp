# AEKO MCP Consolidation Contract — Schemas + New Tool Signatures

Source of truth for the post-consolidation AEKO MCP surface (Action, Technical, Brand Kit).
All new skills and MCP tools MUST reference this document.

Contract version pinning (semver inside date):
- Action plan: `2026-04-17.action.v1.5` (current — backend-saved content variations + selected `brand_kit_id` frontmatter)
- Technical guide: `2026-04-17.technical.v1.1`

Version format: `<YYYY-MM-DD>.<tab>.v<major>.<minor>`. Additive changes (new optional keys, new optional frontmatter fields, new enum values added to existing optional fields) bump `minor` and do not break skills pinned on `major`. Breaking changes (renamed / removed / type-changed keys) bump `major` and require matching skill updates. Skills MUST gate only on `<YYYY-MM-DD>.<tab>.v<major>.` (trailing dot) — never on the full minor string.

### Changelog

**v1.5 (current)** — backend-saved content variations + selected Brand Kit identity:

- Plan.md frontmatter now includes optional `brand_kit_id`, allowing executor skills to load the exact kit selected in the AEKO app instead of relying on active-by-domain lookup. This also gives aeko.shop media presign the correct Brand Kit id.
- New MCP helpers: `aeko_get_brand_kit_by_id` and `aeko_list_brand_kits`. `aeko_request_media_upload` sends `brand_kit_id`.
- Backend-saved content variations + item-based publishing:
- New `Destination` enum in §1 with closed values `own_store_blog | aeko_shop`. Used by the new content-variation tools and `ActionItemSummary.publish_statuses`.
- New §7b "Content Variation Response" — describes the variation row shape (`variation_id, item_id, destination, title, body_html?, body_markdown?, metadata, status (saved|published|failed), created_at, published_at?, publish_result?, last_error?, meta_summary`), the lifecycle (`saved → published | failed`), and the `publish_statuses` aggregation surfaced on `ActionItemSummary` / `ActionItemDetail` per destination with precedence `published > failed > saved`.
- New MCP tools in §8: `aeko_save_content_variation` (WRITE_ONCE, called by `/aeko-create-content` Step 7.5 after local artifact validation), `aeko_list_content_variations` (READ_ONLY, called by `/aeko-publish-content` Step 1), `aeko_publish_content_variation` (WRITE_ONCE, called by `/aeko-publish-content` Step 6 — the backend branches per destination: `aeko_shop` → live aeko.shop publish via existing `AekoShopPublisher`; `own_store_blog` → AEKO-owned draft row in `aeko_content_drafts`, NEVER calls Cafe24/Shopify live APIs).
- `aeko_shop` variation metadata may include Plan.md-derived `featured_products[]` snapshots. Publish upserts those rows into aeko.shop `products` first, then creates the post so aeko.shop maps `post_products` from `featured_product_source_ids`. This supports products that were selected in the content plan but are not yet present in AEKO's synced `store_products` table.
- **Retires v1.4 prerequisite #4** (the never-shipped `aeko_publish_content` handler) — the three-tool surface above subsumes it. `/aeko-publish-content` reads backend rows; the disk-scan path is gone.
- Lifecycle clarification on §6 Item Completion: with v1.5's Step 7.5 in `/aeko-create-content`, an item stays `pending` if the user opts into backend save AND any save call fails. Local-only completion (user declines the save prompt OR no publishable destinations were drafted) still fires `aeko_complete_action_item` normally.
- Backend tables added (informational; not part of skill contract surface): `content_variations` (the variation rows), `aeko_content_drafts` (own_store_blog destination only — AEKO-authored drafts pending push to the user's connected store). See `/Users/seanhan/.claude/plans/backend-saved-content-variations-snoopy-wozniak.md` §1.1 + §1.2 for column shapes.

**v1.4 (proposed — pending backend wiring)** — `products[]` frontmatter field:
- New optional frontmatter field `products: ProductRef[]` for action items created from the dashboard's `상품 선택` content-scope mode. Documents the shape in §3.2.1 (id, **source_id**, name, slug, sku, outbound_url, image_url, short_description). `source_id` is required: it is the external brand-registered identifier (e.g., Shopify variant ID) that the aeko.shop backend joins on (`Product.source_id`), distinct from `id` (AEKO's internal UUID).
- Consumer surface: `/aeko-create-content` parses `products[]` in Step 1 and renders product references in `aeko_shop`-channel artifacts as `<figure role="callout" data-variant="product" data-product-source-id="<source_id>">` callouts in body HTML. The aeko.shop sanitizer (`aeko-shop-backend/app/sanitizer.py`) rejects every `<script>` element, so `aeko_shop` body HTML **does not** embed JSON-LD — the frontend regenerates Article + Product structured data from `PostUpsert` fields at render time (`aeko-shop-front/lib/structured-data.ts`). `/aeko-publish-content` reads `featured_products[].product_source_id` from the artifact's sibling `<slug>.meta.json` (a 1:1 mirror of `PostUpsert`); JSON-LD parsing was removed.
- **Not yet landed.** Three prerequisite tasks block the version bump from being live: (1) `api/services/plan_md.py::build_plan_md` must hydrate `products[]` from `selected_product_ids`, populating both `id` and `source_id`; (2) the action-item-create endpoint must accept those IDs from the dashboard payload; (3) executor skills bump `contract_version` pin from v1.3 to v1.4 once 1+2 ship. (Prerequisite #4 — the never-shipped `aeko_publish_content` handler — is **superseded by v1.5's three-tool content-variation surface**; see the v1.5 changelog entry above.) Until those land, all live Plan.md continues to be stamped at v1.3 and `/aeko-create-content` drafts `aeko_shop` articles without product callouts (the recipe's "no products" fallback path).

**v1.3 (2026-04-23)** — aeko-mcp v0.5.0 tool consolidation:
- `/aeko-run-action` is retired. It split into three executors aligned with `execution_class`: `/aeko-update-pdp` (store_write_artifact), `/aeko-create-content` (local_content_artifact), `/aeko-fix-technical` (technical_artifact). Contract references to "the executor skill" below apply to whichever of the three matches `execution_class`.
- Retired MCP tools referenced in prior contract revisions — `aeko_inspect_product_page`, `aeko_fetch_source_content`, `aeko_update_product_jsonld`. Replacements: executors WebFetch `target_url` + crawled source URLs directly; JSON-LD lives inside the description HTML and is written via `aeko_update_product_description`. New read primitive `aeko_get_product_description` exposes the raw editable HTML for read → patch → write-back flows.
- §3.1 Authoring split and §3.3 `## Execution` prose: updated tool-list guidance to reflect the v0.5.0 surface (brand kit + tracked-prompt forensics + WebFetch, no more `aeko_inspect_product_page`).
- §4 Technical Guide Document: clarified that technical items share `aeko_get_action_plan` — there is no separate `aeko_get_technical_guide` tool (was proposed in v1.1, never shipped). Section kept for its frontmatter contract, which technical items still honour.
- §7a Store Write Response: removed `aeko_update_product_jsonld` from the list of direct-write tools.
- §8 tool surface: removed `aeko_get_technical_guide` stub. Added `aeko_get_product_description` and new tracked-prompt forensics primitive `aeko_get_tracked_prompt(prompt_id, window?)` that the content executor relies on.

**v1.2 (2026-04-20, late)** — prose-templating pivot:
- Backend retires Sonnet prose generation. `api/services/plan_md.py::render_plan_prose` emits a deterministic templated body at item-create time; no Service Bus round-trip, no async wait. Local Claude (in the aeko-run-action skill) fetches real context via MCP tools at execution time.
- `ItemStatus`: `generating_prose` is no longer emitted by the backend on new inserts; new rows land directly in `ready`. Skills still recognise `generating_prose` for legacy rows but the retry branch is expected-dead code.
- §3.1 Authoring split: rewritten — backend stamps frontmatter AND a thin templated prose body. Sonnet no longer authors prose. The executor skill calls `aeko_get_brand_kit`, `aeko_get_tracked_prompts` / `aeko_search_research_prompts`, `aeko_inspect_product_page`, `aeko_fetch_source_content` at run time and synthesizes the artifact locally.
- §5 `AekoBrandKit`: aligned with live backend schema. Fields dropped that never shipped (`brand_description`, `persona`, `competitors`, `viewpoint`, `writing_style`, `tone`, `writing_guidelines`, `cta_text`, `cta_link`, `sample_headlines`, `sample_bodies`). Fields kept/added that match `api/schemas/brand_kits.py`: `brand_name`, `tagline`, `tone_of_voice`, `brand_voice_summary`, `target_audience`, `primary_color`, `logo_url`, `sample_urls`, `must_include`, `forbidden`, `status`, `metadata.account_tier`, `metadata.billing_url`.
- §8 tool signatures: completion tool is canonically `aeko_complete_action_item` (matches backend prose). `aeko_update_brand_kit` takes `(kit_id, <fields>)` and PATCHes `/api/brand-kits/{kit_id}` — there is no PATCH-by-domain route on the backend.

**v1.2 (2026-04-27)** — tier restructure (4→3 tiers):
- `SubscriptionTier`: removed `growth`. New ladder is `starter | pro | enterprise`. Backend keeps `growth` as a deprecated PackageType alias for one week to absorb in-flight requests, then drops it. MCP clients SHOULD treat any inbound `growth` as `starter` during the alias window.
- `tier_required` semantics: store-write artifacts (`pdp_html`, `json_ld`) and shadow products are now Starter+ (was Growth+). Content-generation artifacts (`own_store_markdown`, `external_media_markdown`) move to Pro+ (was Growth+).
- Brand Kit auto-generation moves to Pro+ (was Growth+) — pairs with Content Generation.

**v1.1 (2026-04-20)** — additive alignment with the Phase 3 backend plan:
- `ItemStatus`: added `generating_prose`, `ready`; retired `in_progress` (no prior consumer). Async prose generation → the executable states are now `pending` (legacy / prose pre-generated at create) and `ready` (Phase 3 / prose generated asynchronously by Sonnet).
- `SubscriptionTier`: added `growth` between `starter` and `pro` (subsequently removed in v1.2 — see above).
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
  | "pending"             // legacy rows only; executable
  | "generating_prose"    // retired 2026-04-20 (v1.2 pivot) — no longer emitted on new inserts. Recognised for forward-compat on old rows.
  | "ready"               // canonical on-create state — prose is templated inline at item creation
  | "completed"
  | "failed"
  | "dismissed";

type SubscriptionTier =
  | "starter"
  | "pro"
  | "enterprise";

type Destination =
  // Closed-set for v1.5. Used by content-variation rows and
  // ActionItemSummary.publish_statuses. Backend picks HTML vs markdown
  // body per destination platform; see §7b for the row shape and the
  // per-destination publish branching in /aeko-publish-content.
  | "own_store_blog"   // AEKO-authored draft for the user's connected store CMS;
                       //   publish creates an aeko_content_drafts row only,
                       //   NEVER calls Cafe24/Shopify live APIs.
  | "aeko_shop";       // Live publish to aeko.shop via the existing AekoShopPublisher;
                       //   enforces Pro+ tier and brand.aeko_shop_disabled gates server-side.
// "growth" was removed in the 4→3 tier restructure (2026-04-27).
// Backend keeps "growth" in PackageType as a deprecated alias for one
// week (T+7d cleanup migration drops it). MCP clients SHOULD treat
// any inbound "growth" value as "starter" during that window.
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

### 3.1 Authoring split (revised under v1.2 prose-templating pivot)

- **Backend app layer** stamps the YAML frontmatter AND a thin templated prose body at item-create time. Both are deterministic functions of the `ActionItems` row; no AI model is invoked during plan generation. Source: `api/services/plan_md.py::build_plan_md` + `render_plan_prose`.
- **Local Claude in the executor skill** (`/aeko-update-pdp`, `/aeko-create-content`, or `/aeko-fix-technical` per `execution_class`) does the creative synthesis at run time: calls `aeko_get_brand_kit`, `aeko_get_tracked_prompts` / `aeko_search_research_prompts` / `aeko_get_tracked_prompt`, plus `aeko_get_product_description` (raw editable HTML) and/or `WebFetch` (live page + crawled source URLs) to pull live context, then composes the actual artifact against the frontmatter's machine contract. The templated prose points Claude at exactly these tools — it is execution scaffolding, not narrative guidance.

The skill parses frontmatter for dispatch (all machine values) and reads the templated prose for execution steps (tool list, citability rules, JSON-LD rules, ad-law guardrails, acceptance-criteria echo). Frontmatter remains the sole source of machine truth; prose never re-declares a frontmatter value.

**Frontmatter is machine-only.** Executor skills MUST NOT echo the raw frontmatter block to the user in chat. Render a short, human-friendly header (domain, artifact type, write mode, persona) and show only the prose body to the user. The full Plan.md is available if the user asks for it explicitly.

**Prose language contract.** The templated prose body is rendered in the language indicated by `target_language` (ISO-639-1). Korean and English are currently supported; other values fall back to English. Machine keys stay in English inside prose (e.g. `` `forbidden` ``) regardless of prose language.

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
| `products` | ProductRef[] (optional, **proposed v1.4 — not yet landed**) | When the v1.4 backend wiring ships, this field will be populated for action items created from the dashboard's 상품 선택 mode. Drives `aeko_shop`-channel product callout rendering (`<figure role="callout" data-variant="product" data-product-source-id="<source_id>">`) in body HTML and the sibling `<slug>.meta.json` sidecar's `featured_products[].product_source_id` consumed at publish. **No in-body JSON-LD** — the aeko.shop frontend regenerates Article + Product structured data from `PostUpsert` fields at render time. See §3.2.1 for the field shape. Until v1.4 lands, all live Plan.md continues to be stamped at v1.3 with no `products[]` field; executor skills tolerate the absence. See changelog for the four prerequisite tasks. |
| `persona_label` | string (optional) | |
| `requires_ocr_ingest` | boolean | |
| `requires_brand_kit` | boolean | |
| `brand_kit_id` | string (optional) | Selected Brand Kit UUID when the action item was created. Executor skills should prefer this exact kit over active-by-domain lookup. |
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

### 3.2.1 Products dictionary (proposed v1.4 — not yet landed)

This section documents the **target shape** for the `products[]` frontmatter field once v1.4 ships. The field is **not** populated on v1.3 Plan.md today; executor skills accept it when present and ignore its absence cleanly. See the changelog for the four prerequisite tasks blocking v1.4.

When the dashboard's `콘텐츠 범위` selector is set to `상품 선택`, the user picks 1+ products from the brand's catalog. Once v1.4 lands, those selections SHOULD flow into `frontmatter.products[]` as a list of `ProductRef` objects. Each entry:

| Path | Type | Notes |
|---|---|---|
| `products[].id` | string (UUID) | Stable AEKO-internal Product table identifier. Required. Used for cross-AEKO references; **not** what aeko.shop publish joins on. |
| `products[].source_id` | string (1..240) | External brand-registered identifier (e.g., Shopify variant ID, Cafe24 SKU). Required for v1.4 forward. This is the value `PostUpsert.featured_products[].product_source_id` joins on in the aeko.shop backend (`Product.source_id` via `_product_by_source(brand_id, source_id)` in `aeko-shop-backend/app/routes/internal.py`). It is also the value rendered into the `data-product-source-id` attribute on every `<figure role="callout" data-variant="product">` callout in `aeko_shop` body HTML. **Not** the same ID space as `id`. |
| `products[].name` | string | Display name. Required. |
| `products[].slug` | string | URL slug, used for aeko.shop deep links (`https://aeko.shop/brands/<brand>/products/<slug>`). Required. |
| `products[].sku` | string (optional) | Stock-keeping unit if present in the catalog. Not consumed by `aeko_shop` body HTML (the sanitizer's `<a>`/`<figure>` allow-list has no `data-product-sku` attribute). Renderable as plain text in non-`aeko_shop` channels. |
| `products[].outbound_url` | string (URL) | Deep link to the product page — aeko.shop URL when the product lives on aeko.shop, or the client store's product URL when off-platform. Required. |
| `products[].image_url` | string (URL) | `https://cdn.aeko.shop/...` image URL. Used for `aeko_shop` product callout `<img src>` and the article's `<slug>.meta.json` `hero_image_url` (first entry only). Required. The aeko.shop sanitizer rejects every non-`cdn.aeko.shop` `<img src>` with HTTP 400, so this field must be CDN-hosted. |
| `products[].short_description` | string (optional, ≤240 chars) | Used in the `<figure><figcaption>` callout caption for `aeko_shop`. Plain-text rendering for non-`aeko_shop` channels. Omit when absent — do not fabricate. |

State-volatile fields from the Product model (`about_md`, `price_minor`, `currency`, `available`) are **deliberately excluded** from the Plan.md payload. aeko.shop's renderer hydrates these from its live Product table at publish time, joining via `PostUpsert.featured_products[].product_source_id` (NOT `id`).

YAML rendering example:

```yaml
products:
  - id: "3f2c1a04-...-..."
    name: "쿨링 슬립웨어"
    slug: "cool-sleep"
    sku: "BIO-CLS-001"
    outbound_url: "https://aeko.shop/brands/bioelements/products/cool-sleep"
    image_url: "https://cdn.aeko.shop/brands/bioelements/catalog/cool-sleep-hero.jpg"
    short_description: "체온 1.5°C 낮추는 메리노 울 슬립웨어"
```

**Consumer surface:**

- `aeko-create-content` parses `products[]` in Step 1 (skill SKILL.md §1). Drives the `aeko_shop` channel's product callout rendering at §5.3 (sanitizer-safe `<figure role="callout" data-variant="product" data-product-source-id="<source_id>">` per the editorial-html-jsonld recipe's "Product callout pattern" section) and the sibling `<slug>.meta.json` sidecar's `featured_products[]` array.
- `aeko-publish-content` reads `featured_products[].product_source_id` from the artifact's `<slug>.meta.json` (the 1:1 mirror of `PostUpsert`) — **not** from Plan.md and **not** from JSON-LD parsing. The aeko.shop backend joins on `Product.source_id` via `_product_by_source(brand_id, source_id)` (`aeko-shop-backend/app/routes/internal.py`). `id` (the AEKO internal UUID) is used only for cross-AEKO references, not for the publish join. Plan.md is consulted at publish time only as an **advisory drift check** — its unavailability does not block publish.
- No other channel consumes `products[]` — Tistory / Naver Blog / social channels / editorial channels render product names as plain text only.

**Backend wiring (prerequisite, separate ticket):** Four tasks block v1.4 from being live: (1) `api/services/plan_md.py::build_plan_md` accepts `selected_product_ids` (list of UUIDs) from the action-item-create payload and hydrates the `ProductRef` fields (both `id` and `source_id`) by joining against the Product table at plan-build time. (2) Frontend `상품 선택` form surfaces selected product IDs to the action-item-create endpoint. (3) Executor skills bump `contract_version` minor from 1.3 to 1.4 once 1+2 ship. (4) The aeko.shop `aeko_publish_content` MCP handler ships under `aeko-mcp/aeko_mcp/tools/` — does not currently exist.

### 3.3 Prose body structure (backend-templated)

The prose body is concatenated after the closing `---` of the frontmatter with a single blank line. Source: `api/services/plan_md.py::render_plan_prose`. Sections are deterministic given the row; two calls on an unchanged row produce byte-identical prose.

1. `# Plan: <item.title>`
2. `## Why this plan matters` — 1-2 sentence stub keyed on `artifact_type`. No invented competitive context or fake prompt IDs.
3. `## Execution` — an explicit tool list for the executor to run, composed from the v0.5.0 surface: `aeko_get_brand_kit(...)`, `aeko_get_tracked_prompts(...)` / `aeko_search_research_prompts(...)` / `aeko_get_tracked_prompt(...)` for live context, `aeko_get_product_description(...)` for `store_write_artifact` items that need the editable HTML, and `WebFetch` for target URLs / crawled source pages (replacing the retired `aeko_inspect_product_page` and `aeko_fetch_source_content`). Honors curated inputs: if `prompts_to_rank_on` is populated, that is the ground-truth set and discovery is skipped. When `prompts_to_rank_on`, `keywords`, and brand-kit are all empty, a visible thin-input advisory is emitted. Closes with a reminder to call `aeko_complete_action_item(item_id=..., artifact_summary=..., artifact_paths=[...])` on success.
4. `## Content citability rules` — static passage-structure rules (80-167 words, name the subject explicitly, definition patterns, no fabricated facts — emit `[VERIFY: <field>]`).
5. `## JSON-LD rules` — emitted only when `artifact_type == pdp_html` AND `pdp_responsive_contract.json_ld_required`. Covers Product schema required vs conditional fields, `[VERIFY]` never inside JSON-LD, `type="application/ld+json"` exactness. FAQPage sub-section emitted only when `faq_jsonld_required`.
6. `## Ad-law guardrails` — country-specific (KR populated today). Always emits a visible section; markets without curated rules get an explicit "no guardrails curated yet — apply good-faith judgment" stub so the executor knows compliance was considered.
7. `## Acceptance criteria` — literal echo of the machine contract: `sections_required`, `must_include`, `forbidden`, and (for `pdp_html`) `pdp_responsive_contract`.

Prose body invariants:
- Byte-stable and pure on the row. Anything per-item dynamic arrives via the frontmatter, not the prose.
- No YAML, no `---` fences, no re-declarations of frontmatter values.
- References fields by their backtick-quoted English name (e.g. "every listed string in `must_include`") so the executor can pattern-match.
- Never inlines Brand Kit or product-data values — those are fetched at execution time via the tools listed in §3 `## Execution`.

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

Technical items share the same fetch tool as Action items — `aeko_get_action_plan(item_id)` — because the backend's `GET /api/action-items/{item_id}` endpoint serves both tabs. The returned markdown is the guide.md for technical items (YAML frontmatter + templated prose body, same dual-format as §3). The stub `aeko_get_technical_guide` proposed in the v1.1 contract draft was never shipped and has been removed from §8. Skills for technical artifacts (e.g. `/aeko-fix-technical`) call `aeko_get_action_plan`.

### 4.1 Authoring split

Identical rule to §3.1: backend app layer stamps frontmatter from DB columns and renders the templated prose body inline at item-create time (v1.2 pivot — no AI model); frontmatter is machine-only and not echoed to the user; prose language follows `target_language` on the parent item (technical items inherit language from the domain when not set).

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

### 4.3 Prose body structure (backend-templated)

Recommended sections:

1. `# Guide: <artifact headline>`
2. `## Why this fix matters` — what the AI-search / crawler gap is.
3. `## Target artifact` — what shape the output takes, in plain language.
4. `## Content guidance` — narrative instructions (what to say, how to structure).
5. `## Validation approach` — how the executor should self-check before completing; for `deploy_if_supported`, what the deploy verifies.
6. `## What to avoid` — common Korean/Cafe24/Shopify-specific pitfalls.

Prose body rules identical to §3.3: narrative sections may paraphrase; a terminal acceptance-criteria section (if present) references fields by their backtick-quoted English name.

## 5. Brand Kit

Aligned with live backend: `api/schemas/brand_kits.py::BrandKitResponse` / `BrandKitUpdate`.

```ts
interface AekoBrandKit {
  id: string;                             // kit UUID — required for PATCH
  user_id: string;
  domain_id?: string;
  name: string;
  status: "active" | "draft" | "generating" | "failed";
  brand_name: string;

  tagline?: string;
  tone_of_voice?: string;                 // voice descriptor, max 500 chars
  brand_voice_summary?: string;           // how the brand talks, max 4000 chars
  target_audience?: string;               // who the brand talks to, max 4000 chars
  primary_color?: string;                 // hex, #rgb or #rrggbb
  logo_url?: string;                      // absolute URL

  sample_urls: string[];                  // reference pages for voice grounding
  must_include: string[];                 // hard-include phrases (≤30 items, ≤200 chars each)
  forbidden: string[];                    // hard-exclude phrases (≤30 items, ≤200 chars each)

  source_signals?: Record<string, unknown>;
  generator_version?: string;
  generated_at?: string;
  snapshot_version: string;               // bumps only on SEMANTIC field change (see below)
  last_error?: string;
  created_at: string;
  updated_at: string;

  metadata?: {
    account_tier: SubscriptionTier;       // Read from the authenticated user row at serialize time. Used by executor skills for tier_required gating. See §1.
    billing_url?: string;                 // Env-configured (AEKO_BILLING_URL); consumed by tier-gate upgrade copy.
  };
}

interface AekoBrandKitUpdate {
  name?: string;
  status?: "active" | "draft";            // client may only set these two; "generating" / "failed" are system-controlled
  brand_name?: string;
  tagline?: string;
  tone_of_voice?: string;
  brand_voice_summary?: string;
  target_audience?: string;
  primary_color?: string;
  logo_url?: string;
  sample_urls?: string[];
  must_include?: string[];
  forbidden?: string[];
}
```

Patch semantics: omitted fields remain unchanged. `snapshot_version` bumps ONLY when one of the SEMANTIC fields changes — `brand_voice_summary`, `tone_of_voice`, `target_audience`, `must_include`, `forbidden`. Cosmetic edits (`name`, `brand_name`, `tagline`, `logo_url`, `primary_color`, `sample_urls`, `status`) preserve the snapshot so downstream action_items that reference the old snapshot are not falsely invalidated.

> Not shipped: `persona`, `competitors`, `viewpoint`, `writing_style`, `tone` (bare), `writing_guidelines`, `cta_text`, `cta_link`, `sample_headlines`, `sample_bodies`. These were in the v1.1 contract draft but never landed in the backend schema. Do not reference them from skills.

## 6. Item Completion

Canonical tool: `aeko_complete_action_item`. The backend's templated prose (see §3.3 `## Execution`) names this exact tool; skills MUST use the same name. The tool hits `POST /api/items/{item_id}/complete`, which is a shared endpoint used by both Action and Technical items.

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

The direct-write tools (`aeko_update_product_description`, `aeko_update_product_tags`, `aeko_update_product_meta`) MUST return this structured response so the skill can build consistent `write_result` payloads for `aeko_complete_action_item`. (`aeko_update_product_jsonld` was retired in aeko-mcp v0.5.0 — JSON-LD lives inside the description HTML and is written via `aeko_update_product_description`.)

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

If the direct-write tools return markdown-only (missing `audit_id`), the executor skill (`/aeko-update-pdp`) handles the gap by setting `write_result.audit_id = null` and surfacing a warning to the user: "audit_id unavailable — revert is not supported for this write."

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

If any required field is missing, `/aeko-update-pdp` MUST refuse to mark the item complete and surface the missing field to the user.

## 7b. Content Variation Response (v1.5)

Variation rows are append-only records keyed `(item_id, variation_id)` where `variation_id` is a server-issued UUID. Created by `aeko_save_content_variation` after `/aeko-create-content` Step 7.5; consumed by `aeko_publish_content_variation` from `/aeko-publish-content`. Lifecycle is **independent** of the action item's `status` — an item can be `completed` with zero variations saved (the user declined the Step 7.5 save), or `pending` with no variations (save failed mid-loop and the skill stopped before completion).

```ts
interface ContentVariation {
  id: string;                       // variation_id (server-issued UUID)
  item_id: string;                  // FK to action_items.item_id (Text)
  destination: Destination;         // "own_store_blog" | "aeko_shop" per §1
  title: string;
  body_html: string | null;         // populated for aeko_shop (sanitizer-safe body)
  body_markdown: string | null;     // populated for own_store_blog (and aeko_shop's debug mirror)
  metadata: object | null;          // mirrors the local .meta.json sidecar; per-destination required keys
                                    //   enforced server-side (aeko_shop needs
                                    //   og_description, featured_product_source_ids,
                                    //   and, when Plan.md products exist,
                                    //   featured_products[] snapshots;
                                    //   hero_image_url is optional)
  artifact_paths: string[] | null;  // local-disk audit references from the create-content run
  status: "saved" | "published" | "failed";
  last_error: string | null;        // populated when status="failed"
  created_at: string;               // ISO-8601 timestamptz
  updated_at: string;
  published_at: string | null;      // set when publish succeeded
  publish_result: object | null;    // stored handles such as post_id/slug/url or draft_id
  meta_summary: {                   // flat summary surfaced by aeko_list_content_variations
    featured_products_count: number;
    has_hero_image: boolean;
    locale: string | null;
  };
}

interface ContentVariationPublishResponse {
  variation_id: string;
  destination: Destination;
  status: "published" | "failed";
  // exactly one of the following pair is populated per destination:
  aeko_shop_url: string | null;     // populated when destination="aeko_shop"
  post_id: string | null;           // populated when destination="aeko_shop"
  draft_id: string | null;          // populated when destination="own_store_blog"
}
```

**`ActionItemSummary.publish_statuses`** — populated server-side by `/api/action-items` (list + detail). Aggregates content_variation rows per `(item_id, destination)` with precedence `published > failed > saved` so a single failed variation doesn't get masked by a more recent `saved` row of the same destination:

```ts
interface ActionItemSummary {
  // ... existing fields ...
  publish_statuses?: {              // optional; absent / {} / null all render identically (no badges)
    own_store_blog?: "saved" | "published" | "failed";
    aeko_shop?: "saved" | "published" | "failed";
  };
}
```

**Publish branching by destination** (server-side, inside `POST /api/content-variations/{variation_id}/publish`):

- `aeko_shop`: build an `AekoShopPostPublishRequest` adapter from the variation row's `title` / `body_html` / `metadata` → call existing `AekoShopPublisher.publish_post(...)`. `body_html` and `og_description` are required; `hero_image_url` is optional. If `metadata.featured_products[]` is present, publish first upserts those Plan.md-derived product snapshots into aeko.shop's `products` table (without replacing the whole catalog), then creates the post so aeko.shop can populate `post_products` from `featured_product_source_ids`. Pro+ tier, `brand.aeko_shop_disabled`, and the 10/hour rate limit are enforced inside `publisher.enforce_publish_gate`. On success the variation flips to `published`, `published_at` is set, and `publish_result` stores the post handles IN THE SAME TRANSACTION as the publisher's row insert.
- `own_store_blog`: insert a new `aeko_content_drafts` row with `synthetic_external_id = f"aeko:{item_id}:{variation_id}"`. Flip variation to `published` in the same transaction. **NEVER calls Cafe24/Shopify live APIs** — this is draft-only storage; the user pushes manually via the AEKO dashboard or via a future auto-connector (deferred to a separate ticket).

**Failure semantics**: 4xx for tier / disabled / 422-adapter / 404-not-owned. Already-published rows return a normal `published` response populated from `publish_result` and do not create duplicates. 502 for aeko-shop upstream errors. Retriable failures (tier, disabled, rate-limit) leave the row as `saved`; 422 and 502 may flip to `failed` with `last_error` populated.

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
    """Fetch the Plan.md / guide.md for an item (Action or Technical).
    Shared endpoint: backend returns the templated markdown (YAML frontmatter
    + prose body) for any tab. §3 describes the Action shape; §4 describes
    the Technical shape."""
    # Backend: GET /api/action-items/{item_id} -> Plan.md / guide.md string
    # Response = "---\n" + yaml_frontmatter + "\n---\n\n" + prose_body

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
def aeko_get_brand_kit_by_id(kit_id: str) -> str:
    """Fetch a Brand Kit by kit id, regardless of status."""
    # Backend: GET /api/brand-kits/{kit_id} -> AekoBrandKit

@mcp.tool()
def aeko_list_brand_kits(
    domain_id: str | None = None,
    status: str | None = None,
) -> str:
    """List Brand Kits, optionally filtered by domain and status."""
    # Backend: GET /api/brand-kits?domain_id=<uuid>&status=...

@mcp.tool()
def aeko_update_brand_kit(
    kit_id: str,
    name: str | None = None,
    status: str | None = None,          # "active" | "draft" only
    brand_name: str | None = None,
    tagline: str | None = None,
    tone_of_voice: str | None = None,
    brand_voice_summary: str | None = None,
    target_audience: str | None = None,
    primary_color: str | None = None,
    logo_url: str | None = None,
    sample_urls: list[str] | None = None,
    must_include: list[str] | None = None,
    forbidden: list[str] | None = None,
) -> str:
    """Patch Brand Kit fields by kit id."""
    # Backend: PATCH /api/brand-kits/{kit_id} body: BrandKitUpdate -> BrandKitResponse
    # Note: no PATCH-by-domain alias exists — skills must capture the kit's `id`
    # from the aeko_get_brand_kit response and pass it here.

@mcp.tool()
def aeko_complete_action_item(
    item_id: str,
    artifact_summary: str = "",
    artifact_paths: list[str] | None = None,
    write_result: dict | None = None,
) -> str:
    """Mark an Action or Technical item complete."""
    # Backend: POST /api/items/{item_id}/complete body: AekoCompleteItemRequest
    # Name chosen to match the backend's templated prose (api/services/plan_md.py).

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
    Required for append_below_existing write mode so /aeko-update-pdp can
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

# --- v1.5: Content variation surface (replaces the never-shipped aeko_publish_content) ---

@mcp.tool()
def aeko_save_content_variation(
    item_id: str,
    destination: str,                       # "own_store_blog" | "aeko_shop" per Destination enum (§1)
    title: str,
    body_html: str | None = None,           # at least one of body_html / body_markdown required (validated tool-side)
    body_markdown: str | None = None,
    metadata: dict | None = None,           # mirrors .meta.json; aeko_shop requires og_description
                                            #   + featured_product_source_ids; include
                                            #   featured_products[] snapshots when
                                            #   Plan.md products exist; hero_image_url
                                            #   is optional
    artifact_paths: list[str] | None = None,
) -> str:
    """Save a publishable variation to the backend. Called by /aeko-create-content
    Step 7.5 after local-artifact validation. Backend derives brand_kit_id from
    action_items.brand_kit_id (the tool does NOT carry brand_id).
    """
    # Backend: POST /api/content-variations  body: ContentVariationCreate
    # Auth: require_dual_auth_with_rate_limit + require_scope("mcp:write")
    # Response: ContentVariationResponse (incl. server-issued variation_id)
    # Annotation: WRITE_ONCE (same args called twice creates two rows — append-only)

@mcp.tool()
def aeko_list_content_variations(
    item_id: str,
    destination: str | None = None,
    status: str | None = None,
    limit: int = 20,
) -> str:
    """List saved variations for an item, ordered newest-first.
    Called by /aeko-publish-content Step 1 to discover what's available to publish.
    """
    # Backend: GET /api/content-variations?item_id=<uuid>&destination=...&status=...&limit=...
    # Auth: require_dual_auth_with_rate_limit
    # Response: ContentVariationListResponse (hard cap limit=50)
    # Annotation: READ_ONLY

@mcp.tool()
def aeko_publish_content_variation(
    item_id: str,
    variation_id: str,
) -> str:
    """Publish a saved variation. Backend reads the row server-side and branches
    on destination: aeko_shop → live publish via existing AekoShopPublisher;
    own_store_blog → AEKO-owned draft row in aeko_content_drafts (never calls
    Cafe24/Shopify live APIs). The skill carries only item_id at publish time;
    the backend reads all publish payload fields from the stored row.
    item_id is kept in the tool signature for the skill's downstream
    aeko_complete_action_item write_result handoff.
    """
    # Backend: POST /api/content-variations/{variation_id}/publish
    # Body: {"item_id": item_id} for defense-in-depth item/variation matching.
    # Auth: require_dual_auth_with_rate_limit + require_scope("mcp:write")
    # Response: ContentVariationPublishResponse (aeko_shop_url + post_id for aeko_shop;
    #            draft_id for own_store_blog; already-published rows return stored handles)
    # Annotation: WRITE_ONCE
```

All MCP tools return markdown strings for human-facing output.

## 9. Defaults and Invariants

- `aeko_get_action_plan` returns ONE Plan.md / guide.md string assembled from one DB row (shared across Action and Technical tabs — see §4). MCP never reconstructs plan state from multiple endpoints.
- Plan.md / guide.md are dual-format: YAML frontmatter + prose body. Both are deterministic backend outputs of the row (v1.2 pivot — prose is templated, no AI author). Prose MUST reference fields by name, never by value.
- `aeko_update_brand_kit` is patch semantics keyed on `kit_id`. Omitted fields unchanged. `snapshot_version` bumps only on SEMANTIC field changes (`brand_voice_summary`, `tone_of_voice`, `target_audience`, `must_include`, `forbidden`). See §5.
- `aeko_complete_action_item` always posts `completed_via="mcp"`, `status="completed"`.
- `write_mode` lives on the item contract (frontmatter), not as a runtime flag to the skill.
- `execution_class` is the only dispatch key the executor relies on.
- `brand_kit_id` should be present in frontmatter whenever the action item was created with a selected Brand Kit. Executors prefer this exact kit over active-by-domain lookup.
- `brand_kit_snapshot_version` is mandatory in frontmatter whenever `requires_brand_kit: true`, so plans can prove freshness.

## 10. Contract Tests

- `aeko_list_action_items` / `aeko_list_technical_items` return only their own tab's items; each summary includes `execution_class`, `artifact_type`, `preview`.
- `aeko_get_action_plan` output starts with `---\n`, has a closing `\n---\n` before a blank line and the first `#` header; YAML between the fences parses; every required frontmatter key from §3.2 is present.
- `aeko_get_action_plan` for a PDP item → frontmatter has `requires_ocr_ingest: true`, `responsive_html_required: true`, `write_mode` set, and the `pdp_responsive_contract.*` block present.
- `aeko_get_action_plan` for a non-PDP content item → frontmatter has `execution_class: local_content_artifact` and NO `pdp_responsive_contract.*` keys.
- `aeko_get_action_plan` on a technical-tab item → frontmatter has `execution_class: technical_artifact`; `validation_hints` present when applicable; every required §4.2 key present.
- Frontmatter / prose drift test: for any Plan.md, no line in the prose body equals `---` (no stray closing fence); no bullet *line* in the prose body equals, verbatim (after stripping leading bullet markers and whitespace), any string listed in `must_include` or `forbidden`. Whole-line equality only — legitimate narrative references to those values within a sentence are permitted.
- `aeko_get_brand_kit` → `aeko_update_brand_kit` round-trip does not drop unspecified fields.
- `aeko_complete_action_item` accepts both store-write and non-store-write completions.
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

- `aeko_get_action_plan` — MUST assemble frontmatter from DB columns + templated prose body and return a single markdown string. Serves both Action and Technical items via the shared `GET /api/action-items/{item_id}` endpoint.
- `aeko_list_action_items` / `aeko_list_technical_items` — MUST return tab-scoped summaries.
- `aeko_get_brand_kit` / `aeko_get_brand_kit_by_id` / `aeko_list_brand_kits` / `aeko_update_brand_kit` — MUST exist for Brand Kit checks to work. `metadata.account_tier` and `metadata.billing_url` MUST be populated for the `tier_required` gate + upgrade copy to resolve correctly; if absent, skills fall through to the backend as the authoritative gate (see §3.2).
- `aeko_complete_action_item` — MUST accept both store-write and non-store-write completions.
- `aeko_create_shadow_product` — MUST return `AekoShadowProductResponse` with all six provenance fields.
- `aeko_get_product_description` — required for `append_below_existing` write mode; until wired, `/aeko-update-pdp` aborts that mode with a clear user message. Shipped in aeko-mcp v0.5.0.
- `aeko_update_product_description` — MUST return `AekoStoreWriteResponse` (§7a); until upgraded, skill flags `audit_id: null` and warns revert is unavailable.
- `aeko_check_ocr_cache` / `aeko_store_ocr_result` — optional per §8; skills degrade to live OCR when absent.

Any skill referencing a Stage-1 tool that is absent at runtime MUST stop with "<tool> is not yet available — required for this item's write_mode/artifact_type" rather than producing partial output.

**Frontmatter keys added across v1.x** — backend stamping responsibility:
- `tier_required` — set from the item's source policy. Post-2026-04-27 (4→3 tier restructure), `append_below_existing` and `shadow_product` items both stamp `tier_required: "starter"` (live-store writes and shadow products are Starter+). Content-generation artifacts (`own_store_markdown`, `external_media_markdown`) stamp `tier_required: "pro"`. Optional; absent = Starter-accessible.
- `write_target` — second safety signal, MUST agree with `write_mode` per the pairing rule in §3.2, and MUST use the canonical values `live | shadow | local` (not `production` / `none`). Optional but strongly recommended so the skill can refuse cleanly on misconfigured items.
- `faq_jsonld_required` / `review_jsonld_when_available` — see §3.2 for semantics.

**Stage-1 write-mode guidance (while `aeko_create_shadow_product` is pending):**
The canonical PDP default is `write_mode: shadow_product` + `write_target: shadow`, but until the shadow endpoint ships, backend MUST stamp `write_mode: preview_only` + `write_target: local` on `pdp_html` items. The skill handles `preview_only` end-to-end today (generate HTML → open in browser → tell user to copy-paste into Cafe24). Flipping the default to `shadow_product` is a one-line backend change once the endpoint lands; no MCP release needed.

**Async-prose-generation status handling (v1.1, retired in v1.2):**
Originally: insert row with `status: generating_prose` inside the same transaction that enqueued the Sonnet prose job; flip to `ready` on success, `failed` on error. **Retired 2026-04-20** (commit `6b667ad feat(plan_md): template Plan.md prose, retire Sonnet pipeline`). Prose is now rendered inline at create time via `api/services/plan_md.py::render_plan_prose`; new rows land directly in `ready`. The 409 retry branch in skills is forward-compat-only code for legacy rows; no new inserts exercise it. A `last_error` column is still populated on create-time failures.
