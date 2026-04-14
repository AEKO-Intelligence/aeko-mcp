---
name: "create-visibility-report"
description: "Generate a comprehensive AI visibility report for a domain using AEKO score, metrics, report aggregation, and prioritized action items."
---

# Create Visibility Report

Use this skill when the user wants a full AEKO domain report.

## Workflow

1. Gather the reporting data.
- Use `aeko_prepare_report(domain_id)`.
- Use `aeko_get_score(domain_id)`.
- Use `aeko_get_metrics(domain_id)`.

2. Generate the report structure.
- executive summary
- metrics section
- page analysis summary
- infrastructure status
- prioritized actions
- competitive notes if available

3. Save the report if the user wants an artifact.
- Use `aeko_save_content`.

## Output rules

- Put the headline numbers first.
- Keep recommendations tied to specific AEKO findings, not generic SEO advice.
- If a browser preview is not available, just return the saved file path.
