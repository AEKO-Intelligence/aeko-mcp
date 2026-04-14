---
name: "aeko-update-pdp"
description: "Execute an AEKO v2 PDP update suggestion by rewriting the page copy, generating schema, creating FAQ content, and preparing a preview."
---

# AEKO Update PDP

Use this skill when the user wants to execute a `pdp_update` suggestion from AEKO v2.

## Workflow

1. Load the brief.
- Use `aeko_get_pdp_brief(suggestion_key)`.
- If `domain_id` is missing and needed, ask the user and call it again with the explicit `domain_id`.

2. Mirror winning structure.
- Review `source_evidence`.
- Make the new section hierarchy at least as complete as the citation-winning examples.

3. Draft the PDP rewrite.
- Follow the brief structure exactly.
- Address the current page issues and top citability gaps.
- Use bilingual output when the domain or market clearly requires it.

4. Generate structured data.
- Use `aeko_prepare_json_ld(domain_id, schema_type, page_url=target_url)` for each required type.

5. Generate FAQ content.
- Use `aeko_search_research_prompts` to align the FAQ with real query patterns.

6. Prepare the preview.
- Use `aeko_preview_optimized_page`.
- If browser auto-open is blocked, return the preview path and continue.

7. Save and complete.
- Use `aeko_save_content` for the HTML and schema outputs.
- Use `aeko_complete_suggestion(suggestion_key)`.

## Output rules

- Do not fabricate specs, ratings, shipping promises, or policy details.
- Include a concrete publishing checklist for the target commerce platform.
