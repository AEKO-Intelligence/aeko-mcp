---
name: "aeko-create-external-content"
description: "Draft external-media content from an AEKO v2 brief for guest posts, partner media, neutral reference content, or press assets."
---

# AEKO Create External Content

Use this skill when the user wants to execute an `external_content` suggestion from AEKO v2.

## Workflow

1. Load the brief.
- Use `aeko_get_content_brief(suggestion_key)`.
- Verify the category is `external_content`.

2. Adapt to the destination platform.
- Match the target format such as guest post, partner media, Wikipedia-style neutral draft, or press release.
- Keep tone and evidence standards appropriate to the platform.

3. Mirror winning structures.
- Review `source_evidence`.
- Reproduce the effective heading spine and evidence density without copying.

4. Pull supporting prompt context.
- Use `aeko_search_research_prompts` to align the piece to real AI-query demand.

5. Verify brand/entity context when relevant.
- Use `aeko_check_brand_entity` if the brief depends on entity recognition or `sameAs` links.

6. Save locally only.
- Use `aeko_save_content` for the draft and any outreach assets.
- Use `aeko_complete_suggestion(suggestion_key)` after artifacts are prepared.

## Output rules

- Never publish to third-party platforms automatically.
- For neutral/reference platforms, remove marketing tone and cite third-party evidence.
- Call out notability or sourcing risks explicitly.
