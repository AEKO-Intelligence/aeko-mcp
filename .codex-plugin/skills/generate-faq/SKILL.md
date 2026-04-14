---
name: "generate-faq"
description: "Generate FAQ content and FAQPage schema aligned to real AI-query patterns from AEKO research prompts."
---

# Generate FAQ

Use this skill when the user wants FAQ content for a product, category, or page.

## Workflow

1. Resolve the target.
- product or category
- brand
- country
- optional domain context

2. Research real query patterns.
- Use `aeko_search_research_prompts`.

3. Generate 8-12 FAQ pairs.
- Cover awareness, comparison, decision, trust, and post-purchase topics.
- Make answers factual, self-contained, and directly responsive.

4. Generate FAQPage schema.
- Convert the Q&A set into valid schema.org JSON-LD.

5. Output multiple forms.
- readable markdown
- HTML snippet
- JSON-LD block

6. Complete the suggestion when the work originated from one.
- Use `aeko_complete_suggestion`.

## Output rules

- Use `[VERIFY]` where facts are uncertain.
- If the market is clearly bilingual, provide both language variants when helpful.
