---
name: "generate-jsonld"
description: "Generate Product or related schema.org JSON-LD for a page using AEKO context and explicit verification markers for missing data."
---

# Generate JSON-LD

Use this skill when the user wants production-ready structured data.

## Workflow

1. Resolve inputs:
- domain ID
- page URL
- schema type, defaulting to `Product` for PDP work

2. Gather the brief.
- Use `aeko_prepare_json_ld(domain_id, schema_type, page_url)` when domain context is available.
- Use page details supplied by the user for any missing values.

3. Generate the JSON-LD:
- include only real fields you can support
- use `[VERIFY: ...]` for missing but important values
- never invent reviews, GTINs, prices, or return policies

4. For `Product` schema, prioritize:
- `name`
- `description`
- `brand`
- `image`
- `offers`
- `availability`
- `shippingDetails`
- `hasMerchantReturnPolicy`
- `aggregateRating` only when real data exists

5. Output:
- a `<script type="application/ld+json">` block
- a brief completeness assessment
- missing fields grouped by impact

## Output rules

- Prefer schema.org-valid structures over decorative verbosity.
- If the page is missing critical inputs, say exactly what the user needs to verify.
