---
name: aeko-optimize-pdp
description: >
  Merchant-first product detail page optimization flow. Lets the user choose a
  synced weak PDP, pick a rewrite strategy, pick research depth, generate
  merchant-safe HTML, and then either save it for manual Cafe24/Shopify paste
  or write it back through the store API.
argument-hint: [product-id]
allowed-tools: aeko_list_pdp_candidates, aeko_inspect_product_page, aeko_read_product_page_image, aeko_get_pdp_optimization_brief, aeko_deploy_pdp_html, aeko_list_product_images, aeko_read_product_image, aeko_save_content, aeko_prepare_json_ld, aeko_search_research_prompts, aeko_complete_suggestion, WebSearch, WebFetch
---

# AEKO · Optimize Product Detail Page

Use this skill when the user wants to optimize one of their own synced product detail pages, not when they already have a specific suggestion key.

## Step 1: Choose the product

If the user did not already provide a product id:

1. Call `aeko_list_pdp_candidates(...)`.
2. Show the most relevant non-ready products first.
3. Ask the user which `Product ID` they want to optimize.

Prefer pages marked `needs_fixes` or pages with open `pdp_update` suggestions.

## Step 2: Choose the rewrite strategy

Ask the user which of these two modes they want:

1. `append_below_images`
- Keep the current image-led top section.
- Add structured HTML below the images.
- This is the default.

2. `rewrite_from_scratch`
- Replace the full PDP body with a cleaner structure.
- Use this when the current page is very thin, messy, or image-only.

If the user is unsure, default to `append_below_images`.

## Step 3: Choose research depth

Ask the user how deep the content input should be:

1. `product_page_only`
- Use store facts and product-page extracted facts only.

2. `product_page_web`
- Add official web facts from the brand or manufacturer.
- This is the default.

3. `product_page_web_competitor`
- Add competitor structure + differentiator research before drafting.
- If chosen, run `/aeko-competitive-pdp-input <product-id>` first and fold the output into the draft.

## Step 4: Load the brief

Call:

`aeko_get_pdp_optimization_brief(product_id=..., strategy=..., research_depth=...)`

Use the returned brief as the source of truth for:
- product/store/domain context
- AEKO page-analysis issues
- matching `pdp_update` suggestion context
- required JSON-LD / must-include items
- recommended section spine

## Step 5: Inspect the live product page

Call:

`aeko_inspect_product_page(product_id=...)`

Use it to capture:
- the live PDP heading structure
- the primary image URLs on the page
- any useful title/meta context from the live product page

If one of the live image URLs looks important, open it directly with:

`aeko_read_product_page_image(product_id=..., image_index=1)`

## Step 6: Extract facts from images when needed

If the user has local PDP images available, use:
- `aeko_list_product_images`
- `aeko_read_product_image`

Extract concrete product-page facts only:
- materials
- dimensions
- specs
- certifications
- included components
- use cases
- warnings

Do not invent facts that are not present in AEKO/store data, the product page/images, or the official sources you reviewed.

If the live page image URLs are enough, use them as the basis for “extract from product page” mode even when local images are not available.

## Step 7: Draft the PDP HTML

Write merchant-safe HTML suitable for Cafe24 or Shopify product detail editors.

Requirements:
- Keep the structure aligned with the selected strategy.
- Make the section spine clearer than the current page.
- Use concise H2/H3s and scannable content blocks.
- Add FAQ content when it materially helps product understanding.
- If the brief references a matching AEKO suggestion, make the draft satisfy its `topics`, `required_jsonld`, and `must_include` fields.

If bilingual output is clearly needed for the store or market, produce both KO and EN blocks.

## Step 8: Generate JSON-LD when appropriate

If the brief calls for structured data:

1. Use `aeko_prepare_json_ld(domain_id, schema_type, page_url=product_url)`.
2. Generate complete JSON-LD for the required schema types.
3. Include it either as a separate saved artifact or inside the PDP HTML only if the platform flow can handle it safely.

## Step 9: Present the deployment choice

After the HTML is ready, ask the user how they want to deploy:

1. `manual_copy`
- Save the HTML locally.
- Tell them exactly where to paste it in Cafe24/Shopify.

2. `write_api`
- Push it to the connected store immediately through AEKO's store integration.

Then call:

`aeko_deploy_pdp_html(product_id=..., html=..., deployment_mode=...)`

## Step 10: Wrap up

If the brief surfaced a matching `Suggestion key` and the user has deployed or explicitly accepted the final HTML, call:

`aeko_complete_suggestion(suggestion_key)`

Finish by reporting:
- which product was optimized
- strategy used
- research depth used
- where the HTML was saved or whether it was published via API
- any follow-up work still recommended
