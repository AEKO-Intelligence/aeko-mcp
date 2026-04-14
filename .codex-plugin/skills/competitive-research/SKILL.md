---
name: "competitive-research"
description: "Research a competitor’s AI visibility strategy and produce a gap analysis with concrete recommendations."
---

# Competitive Research

Use this skill when the user wants to understand a competitor’s AI visibility posture.

## Workflow

1. Resolve the target competitor.
- Accept a competitor name, URL, and optional user `domain_id`.

2. Gather AEKO baseline context when the user’s domain is available.
- Use `aeko_get_score`
- Use `aeko_get_metrics`
- Use `aeko_get_visibility_summary`
- Use `aeko_get_suggestions`
- Use `aeko_search_research_prompts`

3. Research the competitor externally if browsing is available.
- Review the main site, key product pages, visible schema, FAQ patterns, and authority signals.
- Inspect whether they expose AI-friendly infrastructure such as `robots.txt`, `llms.txt`, or rich structured data.

4. Rate the competitor across:
- structured data
- content citability
- entity recognition
- infrastructure
- content strategy
- authority signals

5. Produce a gap analysis.
- Compare user vs competitor when user domain context exists.
- Otherwise compare competitor vs AEO best practices.

6. Recommend follow-up actions.
- Route to the most relevant AEKO/Codex skill for the highest-impact next step.

## Output rules

- Prioritize findings over narrative.
- If browsing is unavailable or incomplete, say which conclusions are inferred.
