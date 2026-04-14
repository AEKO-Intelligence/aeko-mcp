---
name: "aeo-audit"
description: "Audit a URL or local content file for AI Engine Optimization readiness using AEKO data, local file inspection, and page-level analysis."
---

# AEO Audit

Use this skill when the user wants an audit of a product page, article, or local content file.

## Workflow

1. Resolve whether the target is:
- a tracked AEKO page on a known domain
- a public URL
- a local file path

2. Prefer AEKO tools when domain context is available:
- Use `aeko_get_domain_info` to confirm the domain.
- Use `aeko_get_page_analysis` for page-level AI-readiness findings when the domain is known.
- Use `aeko_get_citability` for a page-level citability score when helpful.

3. For local files:
- Use `aeko_audit_content_file` for the full citability audit.
- If needed, use `aeko_read_content_file` to inspect the underlying text.

4. For public URLs outside AEKO tracking:
- Inspect the page directly with available web tools if enabled.
- Review title, description, headings, visible FAQ content, JSON-LD blocks, and extractability of key answers.

5. Score the page across these dimensions:
- structured data
- answer-block quality
- passage self-containment
- structural readability
- technical/meta signals
- trust and commerce signals

6. Output a concise audit with:
- overall score and grade
- strongest signals
- critical issues
- medium/low issues
- prioritized fixes

## Output rules

- Be concrete and reference missing schema, weak passages, or blocked technical signals explicitly.
- If facts are missing, say what needs verification instead of inventing details.
- If the user gives a local HTML/Markdown file, include file-specific recommendations.
