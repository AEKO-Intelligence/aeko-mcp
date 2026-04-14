---
name: "aeo-audit-local"
description: "Audit a local directory of content files for AI citability and produce a prioritized scorecard with next-step recommendations."
---

# AEO Audit Local

Use this skill when the user wants a batch audit of local HTML, Markdown, or text content.

## Workflow

1. Resolve the directory path.
- Use `aeko_scan_content_directory` with the user-provided path or the configured `AEKO_CONTENT_DIR`.

2. Select files to audit.
- Prioritize HTML first, Markdown second, then other text files.
- Audit up to 20 files unless the user explicitly asks for a larger pass.

3. Audit each selected file.
- Use `aeko_audit_content_file`.
- If a result fails, note it and continue.

4. Build a scorecard.
- Include file name, type, word count, score, grade, and top issue.
- Sort weakest files first.

5. Aggregate patterns.
- report average score
- grade distribution
- recurring weaknesses
- strongest content types or pages

6. Offer a saved artifact.
- If the user wants a report saved, use `aeko_save_content`.

## Output rules

- Keep recommendations specific to the audited files.
- Highlight quick wins separately from structural issues.
