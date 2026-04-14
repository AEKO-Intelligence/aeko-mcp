---
name: "aeko-fix-store-level"
description: "Execute an AEKO v2 store-level suggestion such as llms.txt, robots.txt, sitemap, or schema-infrastructure work."
---

# AEKO Fix Store Level

Use this skill when the user wants to execute a `store_level` suggestion from AEKO v2.

## Workflow

1. Load the brief.
- Use `aeko_get_store_level_brief(suggestion_key)`.
- Verify the category is `store_level`.

2. Resolve `domain_id`.
- If the brief exposes it, use that.
- If not, ask the user for the domain UUID instead of guessing.

3. Execute the correct chain by content type.

For `llms_txt`:
- Use `aeko_prepare_llms_txt(domain_id)`.
- Draft the file.
- Recommend validation with `aeko_validate_llms_txt` after deployment.

For `robots_txt`:
- If the current robots content is available, use it.
- Then use `aeko_prepare_robots_txt_fix(domain_id, current_robots_txt)`.
- Draft the updated file and explain which crawlers become accessible.

For `sitemap`:
- Use `aeko_get_domain_info(domain_id)` and the brief structure to generate the sitemap artifact.

For schema infrastructure:
- Use `aeko_prepare_json_ld(domain_id, schema_type)`.
- Generate the required schema block(s).

4. Save and complete.
- Use `aeko_save_content`.
- Use `aeko_complete_suggestion(suggestion_key)`.

## Output rules

- Be deployment-specific: say where each file belongs on the site.
- If a platform may block root-file deployment, warn the user before they implement.
