---
name: "aeko-create-own-content"
description: "Draft own-site content from an AEKO v2 content brief, including article structure, FAQ coverage, and required JSON-LD."
---

# AEKO Create Own Content

Use this skill when the user wants to execute an `own_content` suggestion from AEKO v2.

## Workflow

1. Load the brief.
- Use `aeko_get_content_brief(suggestion_key)`.
- Verify the suggestion category is `own_content`.

2. Mirror competitor structure.
- Extract the major headings from `source_evidence`.
- Make the new H2/H3 spine at least as complete as the winning citation patterns.

3. Pull prompt context.
- Use `aeko_search_research_prompts` with the domain scope or the brief topics.
- Ground each major section in real consumer query phrasing.

4. Draft the content.
- Follow the brief structure.
- Match persona, tone, and word-count target.
- Keep sections self-contained and directly quotable.

5. Generate required JSON-LD.
- For each schema type listed in the brief, produce a complete block.

6. Save and complete.
- Use `aeko_save_content` for the draft and schema artifacts.
- Use `aeko_complete_suggestion(suggestion_key)` when the work is finished.

## Output rules

- Do not invent facts.
- Use `[VERIFY]` markers when the brief is missing critical details.
- Include publishing guidance relevant to the user’s CMS when helpful.
