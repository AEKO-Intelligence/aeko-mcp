---
name: "create-blog-article"
description: "Create an AEO-optimized blog article using AEKO analysis data, query patterns, and article schema guidance."
---

# Create Blog Article

Use this skill when the user wants long-form content for their own site.

## Workflow

1. Resolve product and domain context.
- Use `aeko_get_domain_info`.
- Use `aeko_get_suggestions` to find the relevant content suggestion when applicable.

2. Pull full analysis.
- Use `aeko_get_product_analysis` when an analysis ID is available.

3. Load visual context if useful.
- Use `aeko_list_product_images`.
- Use `aeko_read_product_image` for key assets.

4. Research consumer query patterns.
- Use `aeko_search_research_prompts`.

5. Draft the article.
- Structure it around real query patterns and competitive advantages.
- Include evidence, comparisons, and directly quotable passages.

6. Generate article schema.
- Use `aeko_prepare_json_ld` with `schema_type="Article"` when domain context is available.

7. Save and optionally complete the related suggestion.
- Use `aeko_save_content`.
- Use `aeko_complete_suggestion` when the work came from a suggestion.

## Output rules

- Keep the tone informative and credible, not salesy.
- Avoid unsupported claims and use `[VERIFY]` where needed.
