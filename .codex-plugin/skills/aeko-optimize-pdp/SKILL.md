---
name: "aeko-optimize-pdp"
description: "Merchant-first PDP optimization flow that starts from synced weak products, lets the user choose rewrite mode and research depth, then saves or publishes the final HTML."
---

# AEKO Optimize PDP

Use this skill when the user wants to optimize one of their own synced product pages.

## Workflow

1. Choose the product.
- Use `aeko_list_pdp_candidates` if the user did not provide a product id.
- Prefer `needs_fixes` pages or pages with open PDP suggestions.

2. Choose the strategy.
- `append_below_images` keeps the image-led top section and adds structured HTML below it.
- `rewrite_from_scratch` replaces the whole PDP body.
- Default to `append_below_images`.

3. Choose the research depth.
- `product_page_only`
- `product_page_web`
- `product_page_web_competitor`
- If competitor depth is chosen, run `/aeko-competitive-pdp-input <product-id>` first.

4. Load the brief.
- Use `aeko_get_pdp_optimization_brief(product_id=..., strategy=..., research_depth=...)`.
- Treat the returned product/store/domain context and AEKO issue list as the working brief.

5. Inspect the live page.
- Use `aeko_inspect_product_page(product_id=...)` to capture the current heading structure and page image URLs.
- Use `aeko_read_product_page_image(product_id=..., image_index=1)` when you need to inspect one of the live PDP images directly.

6. Gather facts.
- If the user has local PDP images, use `aeko_list_product_images` and `aeko_read_product_image`.
- Add official web facts when `product_page_web` or deeper is selected.

7. Draft the HTML.
- Keep it merchant-safe for Cafe24/Shopify editors.
- Match the chosen structure.
- Cover the brief's must-include topics and any required JSON-LD.

8. Deploy.
- Ask whether the user wants `manual_copy` or `write_api`.
- Use `aeko_deploy_pdp_html(...)`.

9. Close the loop.
- If the brief exposed a matching suggestion key and the user accepted the result, call `aeko_complete_suggestion`.
