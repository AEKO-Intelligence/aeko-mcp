---
name: generate-jsonld
description: >
  Generate JSON-LD structured data (schema.org) for a product page.
  Use when a user needs Product, Brand, or FAQPage schema markup
  for AI engine discoverability.
argument-hint: <product-name-or-url>
allowed-tools: Read, Write
---

# Generate JSON-LD — Structured Data for Products

You are generating production-ready JSON-LD structured data for a product page.

## Step 1: Gather product information

From the user's input, collect:
- **Product name**
- **Brand**
- **Price** and currency
- **Description**
- **Image URL(s)**
- **SKU / GTIN / MPN** (if available)
- **Category**
- **Availability**
- **Review / rating data** (if available)

If the user provides a URL, use `WebFetch` to extract product details from the page. If they provide a product name, ask for any missing critical fields.

## Step 2: Generate Product JSON-LD

Create a complete `Product` schema with all recommended fields:

```json
{
  "@context": "https://schema.org",
  "@type": "Product",
  "name": "...",
  "description": "...",
  "image": ["..."],
  "brand": {
    "@type": "Brand",
    "name": "..."
  },
  "offers": {
    "@type": "Offer",
    "price": "...",
    "priceCurrency": "...",
    "availability": "https://schema.org/InStock",
    "url": "...",
    "shippingDetails": {
      "@type": "OfferShippingDetails",
      "shippingDestination": {
        "@type": "DefinedRegion",
        "addressCountry": "..."
      },
      "shippingRate": {
        "@type": "MonetaryAmount",
        "value": "...",
        "currency": "..."
      },
      "deliveryTime": {
        "@type": "ShippingDeliveryTime",
        "handlingTime": {
          "@type": "QuantitativeValue",
          "minValue": 1,
          "maxValue": 3,
          "unitCode": "d"
        },
        "transitTime": {
          "@type": "QuantitativeValue",
          "minValue": 3,
          "maxValue": 7,
          "unitCode": "d"
        }
      }
    },
    "hasMerchantReturnPolicy": {
      "@type": "MerchantReturnPolicy",
      "applicableCountry": "...",
      "returnPolicyCategory": "https://schema.org/MerchantReturnFiniteReturnWindow",
      "merchantReturnDays": 30,
      "returnMethod": "https://schema.org/ReturnByMail",
      "returnFees": "https://schema.org/FreeReturn"
    }
  },
  "aggregateRating": {
    "@type": "AggregateRating",
    "ratingValue": "...",
    "reviewCount": "..."
  },
  "sku": "...",
  "gtin13": "...",
  "mpn": "...",
  "weight": {
    "@type": "QuantitativeValue",
    "value": "...",
    "unitCode": "GRM"
  },
  "material": "...",
  "color": "...",
  "sameAs": [
    "https://en.wikipedia.org/wiki/...",
    "https://www.wikidata.org/wiki/Q...",
    "https://www.linkedin.com/company/...",
    "https://www.youtube.com/...",
    "https://twitter.com/..."
  ],
  "speakable": {
    "@type": "SpeakableSpecification",
    "cssSelector": [".product-description", ".product-title"]
  }
}
```

### Field guidelines:
- `description`: 50-300 characters, keyword-rich but natural
- `image`: Use absolute URLs, include multiple angles if available
- `offers.availability`: Use full schema.org URL (e.g., `https://schema.org/InStock`)
- `aggregateRating`: Only include if real review data exists — never fabricate
- Include `sku`, `gtin13`, or `mpn` if the seller has them

### E-Commerce fields (high impact for cross-border sellers):
- `shippingDetails`: Include for each destination country. Use ISO 3166 country codes. AI engines use this to answer "does X ship to Y?"
- `hasMerchantReturnPolicy`: Include return window, method, and fees. AI engines cite this in purchase-decision answers.
- `weight` / `material` / `color`: Use `QuantitativeValue` for weight. These help AI engines make product comparisons.
- `gtin13` / `gtin14`: Critical for product matching across platforms. Include barcode numbers if the seller has them.

### AI citation fields:
- `speakable`: Mark the product description and title for voice assistant extraction. Uses CSS selectors pointing to the actual page elements.
- `sameAs`: Link to authoritative brand pages in priority order:
  1. Wikipedia article (strongest entity signal)
  2. Wikidata entity
  3. LinkedIn company page
  4. YouTube channel
  5. X/Twitter profile

## Step 3: Completeness scoring

Score the generated JSON-LD on this 12-point rubric:

| # | Check | Points | Impact |
|---|-------|--------|--------|
| 1 | `@type: Product` present | 1 | Required |
| 2 | `name` + `description` | 1 | Required |
| 3 | `brand` with `@type: Brand` | 1 | High |
| 4 | `offers` with price + currency + availability | 1 | High |
| 5 | `image` (1+ absolute URL) | 1 | High |
| 6 | `aggregateRating` (real data only) | 1 | High |
| 7 | `sku` or `gtin13` or `mpn` | 1 | Medium |
| 8 | `shippingDetails` | 1 | High (cross-border) |
| 9 | `hasMerchantReturnPolicy` | 1 | High (cross-border) |
| 10 | `sameAs` (2+ links) | 1 | Medium |
| 11 | `speakable` | 1 | Medium |
| 12 | `weight` / `material` / `color` (any 1+) | 1 | Low |

Report the score as **X/12** and list missing fields by impact level.

## Step 4: Flag missing high-value fields

After generation, list any fields that are missing but would improve AI engine visibility:

- **[HIGH]** `aggregateRating` — increases trust signals in AI responses
- **[HIGH]** `shippingDetails` — AI engines answer "does this ship to [country]?"
- **[HIGH]** `hasMerchantReturnPolicy` — AI engines cite return policies in purchase comparisons
- **[MEDIUM]** `gtin13` — helps AI engines match products across sources
- **[MEDIUM]** `sameAs` — strengthens brand entity recognition
- **[MEDIUM]** `speakable` — enables voice assistant extraction
- **[LOW]** `weight` / `material` / `color` — helps with product comparison queries

## Step 5: Preview (optional)

If the user wants to see how it renders, call `aeko_preview_optimized_page` with the JSON-LD data.

## Step 6: Output

Present the final JSON-LD in two formats:

1. **Ready-to-paste HTML** — wrapped in `<script type="application/ld+json">`
2. **Validation link** — suggest testing at Google Rich Results Test

Include the completeness score and list of missing fields.

Note any `[VERIFY]` placeholders that the user needs to fill in with actual data.

## Step 7: Report completion

- If this task was triggered by an AEKO suggestion, call `aeko_complete_suggestion` with the suggestion's `key` to mark it as done in the dashboard.
- Common key patterns: `infra_json_ld`, `product_page_jsonld_{source_id}`, `content_blog_jsonld_{source_id}`.
