---
name: "create-social-content"
description: "Generate platform-specific social posts using AEKO analysis, product context, and target-market preferences."
---

# Create Social Content

Use this skill when the user wants social posts for a product or campaign.

## Workflow

1. Resolve target platforms and market.
- Default to Instagram, Facebook, X, and LinkedIn if the user does not specify.

2. Gather context.
- Use `aeko_get_domain_info`
- Use `aeko_get_suggestions`
- Use `aeko_get_product_analysis`
- Use `aeko_search_research_prompts`
- Use product image tools if asset guidance is needed

3. Generate platform-specific variants.
- Fit each platform’s length, tone, and CTA style.
- Keep language and cultural context aligned to the target market.

4. Save per-platform outputs.
- Use `aeko_save_content`.

5. Complete the related suggestion if applicable.
- Use `aeko_complete_suggestion`.

## Output rules

- Separate each platform clearly.
- Include character-count awareness and image recommendations when useful.
