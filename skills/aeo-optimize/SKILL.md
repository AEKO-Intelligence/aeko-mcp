---
name: aeo-optimize
description: >
  Full AEO optimization for a product page. Fetches AEKO suggestions,
  generates optimized description + JSON-LD + FAQ, and opens a browser
  preview. Use when a user wants to improve how AI engines recommend
  their product.
argument-hint: <product-url> [domain-id]
allowed-tools: Read, Write, Bash(open *), Bash(xdg-open *)
---

# AEO Optimize — Full Product Page Optimization

You are running the AEKO full-page optimization workflow. Follow these steps carefully.

## Step 1: Identify the product and domain

Parse the user's input for:
- **Product URL** — the page to optimize
- **Domain ID** — the AEKO domain UUID (ask the user if not provided; they can find it via `aeko_get_domain_info`)

If only a URL is provided, call `aeko_get_domain_info` to find the matching domain.

## Step 2: Gather AEKO data

Call these MCP tools to understand the current state:

1. **`aeko_get_suggestions(domain_id)`** — get prioritized optimization suggestions
2. **`aeko_get_page_analysis(domain_id)`** — get current page scores and issues

Review the results and identify:
- The current AEO readiness score for this page
- Top 3-5 issues to address (prioritize critical and high-priority suggestions)
- Missing structured data fields
- Content gaps that AI engines struggle with

## Step 3: Generate optimized product description

Write an AEO-optimized product description that:
- Addresses the top suggestions from Step 2
- Uses natural language that AI engines can parse and quote
- Includes specific product attributes (materials, dimensions, use cases)
- Mentions the brand name naturally 2-3 times
- Structures information with clear benefit statements
- Keeps the tone appropriate for the target market
- Preserves any factual claims from the original (don't invent specs)

### Citability guidelines

Apply these principles to make the description maximally citable by AI engines:

**Optimal passage structure:**
- Keep key passages 80-167 words (optimal for product descriptions)
- Blog/article content: aim for 134-167 words per section
- Each passage should be self-contained — extractable without surrounding context

**Self-containment principle:**
- Always name the subject explicitly (avoid starting with pronouns)
- Each paragraph should be understandable on its own
- Include specific facts, not vague claims
- Avoid "as mentioned above" or "see below" references

**Definition patterns (triggers AI citation):**
- Use "X is a Y that Z" structures for key claims
- Open sections with a direct 1-2 sentence answer
- Place the most important information in the first 40-60 words

**Statistical density:**
- Include specific numbers, percentages, and measurements
- Reference named sources where applicable
- Use year references for freshness ("2025", "2026")
- Compare with specific data: "30% more X than Y" rather than "significantly more"

**Before/after example:**

*Before (poor citability):*
> This product is really great and has many wonderful features. It's been very popular with our customers who love it for various reasons. The quality is excellent and it comes in many options.

*After (high citability):*
> The [Brand] [Product] is a [category] designed for [use case]. Made from [material], it weighs [X]g and measures [dimensions]. In 2025 customer testing, it scored 4.8/5.0 across 2,300+ reviews, with 94% of buyers recommending it for [specific purpose]. Available in [X] colors with free returns within 30 days.

**Important**: Do NOT make up product details. Use information from the existing page analysis. If details are missing, note them as `[VERIFY: ...]` placeholders.

## Step 4: Generate JSON-LD structured data

Create a complete `Product` schema.org JSON-LD block including:
- `@type`: "Product"
- `name`, `description`, `brand`, `image`
- `offers` with `price`, `priceCurrency`, `availability`
- `shippingDetails` with destination countries and delivery times
- `hasMerchantReturnPolicy` with return window and fees
- `aggregateRating` if review data is available
- `sku` / `gtin13` / `mpn` if available
- `weight` / `material` / `color` if applicable
- `speakable` with CSS selectors for key content
- `sameAs` links (Wikipedia > Wikidata > LinkedIn > YouTube > Twitter)

Use realistic placeholder values marked with `[VERIFY]` for fields you cannot determine from the data.

## Step 5: Generate FAQ items

Call **`aeko_search_research_prompts`** with relevant scope/keywords to find real consumer queries.

Generate 6-10 FAQ Q&A pairs that:
- Match patterns from actual AI engine queries in the research library
- Answer common purchase-decision questions
- Naturally mention the product/brand in answers
- Are factual and based on available product information

### Citability tips for FAQs:
- Start each answer with a direct 1-2 sentence response
- Keep answers 80-150 words (sweet spot for AI extraction)
- Include specific numbers, prices, or specs in answers
- Make each answer self-contained (no "as mentioned above")
- Use the product/brand name explicitly in each answer (not "it" or "this product")

## Step 6: Open the preview

Call **`aeko_preview_optimized_page`** with all generated content:
- `product_title`: the product name
- `original_description`: from the page analysis
- `optimized_description`: your generated description
- `json_ld`: the complete JSON-LD as a JSON string
- `aeo_score_before`: current score from page analysis
- `aeo_score_after`: your estimated improved score
- `product_url`: the product URL
- `faq_items`: JSON array of `{"question": "...", "answer": "..."}` objects
- `target_market` and `language`: from context

## Step 7: Output artifacts

After the preview opens, present the generated content as copyable code blocks:

1. **Optimized Description** — as plain text
2. **JSON-LD** — as a `<script type="application/ld+json">` block
3. **FAQ HTML** — as `FAQPage` JSON-LD + rendered HTML
4. **Implementation checklist** — numbered list of what to update on the actual page

Always note which values need verification with `[VERIFY]` markers.

## Step 8: Report completion

- If this task was triggered by an AEKO suggestion, call `aeko_complete_suggestion` with the suggestion's `key` to mark it as done in the dashboard.
- Common key patterns: `product_page_readiness_{source_id}`, `content_blog_readiness_{source_id}`.
