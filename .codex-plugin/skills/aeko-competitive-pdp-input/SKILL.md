---
name: "aeko-competitive-pdp-input"
description: "Competitor-focused PDP input skill that researches comparable product pages and returns differentiators and structure guidance for the final rewrite."
---

# AEKO Competitive PDP Input

Use this skill when the user wants competitor-backed inputs before rewriting a PDP.

## Workflow

1. Load product context.
- Use `aeko_get_pdp_optimization_brief(product_id=..., strategy="append_below_images", research_depth="product_page_web_competitor")`.
- Use `aeko_inspect_product_page(product_id=...)` to capture the current page structure and image URLs before comparing competitors.
- Use `aeko_read_product_page_image(product_id=..., image_index=1)` when a live PDP image carries important factual or merchandising signals.

2. Find competitors.
- Use `WebSearch` to identify direct competitor product pages.

3. Review competitor pages.
- Use `WebFetch` on the best 2-4 PDPs.
- Capture heading structure, proof blocks, differentiators, FAQ patterns, and trust signals.

4. Produce a concise input brief.
- `Common competitor sections`
- `Competitor claims`
- `User-product edges`
- `Missing proof points`
- `Recommended differentiators`

5. Hand off to the caller.
- Tell the user to use this output as structure and positioning input, not as copy to imitate.
