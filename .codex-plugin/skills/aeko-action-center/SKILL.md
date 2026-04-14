---
name: "aeko-action-center"
description: "Review categorized AEKO suggestions for a domain and route the user to the highest-value next action in Codex."
---

# AEKO Action Center

Use this skill when the user wants help deciding what to work on next in AEKO.

## Workflow

1. Resolve the domain.
- Use `aeko_get_domain_info` if needed.

2. Check whether prompt groups exist.
- Use `aeko_list_prompt_groups`.
- If groups exist, ask whether the user wants to scope work to one group.

3. Fetch categorized suggestions.
- Prefer `aeko_get_suggestions_v2`.
- If v2 is unavailable, fall back to `aeko_get_suggestions`.

4. Summarize the current work queue:
- count of suggestions per category
- top priorities
- which category is blocking AI visibility most

5. Route the user to one of the Codex-supported next actions:
- `aeo-optimize` for page-level rewrite work
- `generate-jsonld` for schema implementation
- `aeo-audit` for verification or investigative review

6. If the backend only returns legacy flat suggestions:
- explain that the richer v2 briefs are unavailable
- recommend the closest supported Codex skill based on the suggestion type

## Output rules

- Keep the summary compact.
- Prioritize the top 1-3 actions, not the whole backlog.
- When recommending a next step, include the exact domain ID, page URL, or suggestion key needed to continue.
