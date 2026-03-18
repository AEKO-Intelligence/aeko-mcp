---
name: generate-faq
description: >
  Generate AEO-optimized FAQ content for a product or category.
  Uses AEKO's research prompt library to match real AI engine queries.
  Outputs both readable text and FAQPage JSON-LD schema.
argument-hint: <product-or-category> [country-code]
allowed-tools: Read, Write
---

# Generate FAQ — AI-Query-Matched FAQ Content

You are generating FAQ content designed to match how consumers ask AI engines about products.

## Step 1: Understand the product/category

Parse the user's input for:
- **Product or category name** — what the FAQ is about
- **Brand name** — to mention naturally in answers
- **Target country** — defaults to US if not specified
- **Domain ID** — if available, used to fetch AEKO research prompts

## Step 2: Research real consumer queries

Call **`aeko_search_research_prompts`** with relevant filters:
- `scope`: the product category (e.g., "beauty", "electronics")
- `keyword`: product-specific terms
- `country`: target market
- `query_type`: focus on "comparison" and "recommendation" types

Analyze the returned prompts to identify:
- Common question patterns consumers use with AI engines
- Key comparison criteria (price, quality, features)
- Decision factors for the product category
- Language and phrasing patterns

## Step 3: Generate FAQ Q&A pairs

Create **8-12 FAQ items** following these rules:

### Question guidelines:
- Mirror real AI engine query patterns from Step 2
- Use natural, conversational phrasing
- Include specific product/category terms
- Cover the full purchase funnel: awareness → consideration → decision
- Mix question types: "What is...", "How does... compare to...", "Is... worth it for...", "What are the best... for..."

### Answer guidelines:
- Keep answers 2-4 sentences each
- Mention the brand/product naturally (not forced)
- Include specific, factual details
- Address the question directly in the first sentence
- Add one differentiating detail that AI engines can quote
- Do NOT make up specifications or claims — use `[VERIFY]` for uncertain facts

### Required topic coverage:
1. What the product is / does (awareness)
2. Key features or ingredients (consideration)
3. Comparison with alternatives (consideration)
4. Best use cases / who it's for (consideration)
5. Price / value proposition (decision)
6. Shipping / availability for target market (decision)
7. How to use / care instructions (post-purchase)
8. Return policy / warranty (trust)

## Step 4: Generate FAQPage JSON-LD

Convert the FAQ pairs into schema.org `FAQPage` markup:

```json
{
  "@context": "https://schema.org",
  "@type": "FAQPage",
  "mainEntity": [
    {
      "@type": "Question",
      "name": "...",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "..."
      }
    }
  ]
}
```

## Step 5: Output

Present the results in three formats:

1. **Readable Markdown** — the FAQ as a formatted list for content review
2. **FAQPage JSON-LD** — wrapped in `<script type="application/ld+json">` for pasting
3. **HTML snippet** — semantic HTML with `<details>/<summary>` tags for direct page embedding

If the user's target market is Korea (KR), also generate a Korean-language version alongside the English version.

## Step 6: Report completion

- If this task was triggered by an AEKO suggestion, call `aeko_complete_suggestion` with the suggestion's `key` to mark it as done in the dashboard.
- Common key patterns: `product_page_faq_{source_id}`.
