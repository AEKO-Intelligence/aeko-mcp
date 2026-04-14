---
name: "create-marketing-materials"
description: "Generate AEO-aware marketing assets such as product copy, newsletters, landing pages, press releases, or ad copy using AEKO analysis data."
---

# Create Marketing Materials

Use this skill when the user wants marketing copy derived from AEKO analysis.

## Workflow

1. Resolve the requested asset type.
- product description rewrite
- email newsletter
- landing page copy
- press release
- ad copy

2. Gather shared context.
- Use `aeko_get_domain_info`
- Use `aeko_get_suggestions`
- Use `aeko_get_product_analysis`
- Use `aeko_search_research_prompts`
- Use product image tools if visual context matters

3. Generate the selected asset.
- Tailor format, tone, and length to the channel.
- Preserve factual claims and clear product positioning.

4. Add structured data when relevant.
- For PDP or landing-page work, use `aeko_prepare_json_ld`.

5. Save the result.
- Use `aeko_save_content`.

## Output rules

- Keep the output channel-specific.
- Make the copy quotable and entity-rich where appropriate, but do not over-optimize into awkward phrasing.
