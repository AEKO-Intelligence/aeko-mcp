---
name: "aeo-optimize"
description: "Run the AEKO optimization workflow for a product page: gather findings, generate improved copy, produce JSON-LD and FAQ content, and build a preview."
---

# AEO Optimize

Use this skill when the user wants to improve a PDP or article using AEKO findings.

## Workflow

1. Determine the available input:
- product URL
- domain ID
- suggestion key from AEKO suggestions v2

2. Gather context.

If the user provides a `suggestion_key`:
- Use `aeko_get_suggestion` first.
- If it is a PDP update suggestion, use `aeko_get_pdp_brief` when that gives richer page context.

If the user provides a domain and page URL:
- Use `aeko_get_page_analysis`.
- Use `aeko_get_suggestions` or `aeko_get_suggestions_v2` if prioritization context is needed.

3. Generate optimized content:
- rewrite the main description for extractability and commerce clarity
- keep claims factual
- use `[VERIFY: ...]` placeholders for missing specs, pricing, shipping, or return details

4. Generate structured data:
- Prefer using `aeko_prepare_json_ld` to collect the available schema context.
- Produce a complete `Product` JSON-LD block when the page is a PDP.

5. Generate FAQ content:
- Use `aeko_search_research_prompts` to align questions with real consumer query patterns when possible.
- Produce factual, self-contained answers that mention the product or brand explicitly.

6. Build the preview:
- Call `aeko_preview_optimized_page` with the original description, optimized description, JSON-LD, score delta, and FAQ items.
- If the environment blocks browser opening, report the returned preview file path and continue.

7. Close with:
- optimized description
- ready-to-paste JSON-LD
- FAQ content
- implementation checklist

## Output rules

- Do not fabricate ratings, shipping policies, or identifiers.
- Mark unverifiable fields with `[VERIFY]`.
- Keep the implementation checklist specific to the page.
