---
name: competitive-research
description: >
  Research a competitor's AI visibility strategy. Analyzes competitor
  content, structured data, and citation patterns to identify gaps and
  opportunities. Returns a structured competitive brief with actionable
  recommendations. Use when a user wants to understand how competitors
  are performing in AI engine results.
argument-hint: <competitor-name-or-url> [--domain-id <uuid>]
allowed-tools: aeko_get_suggestions, aeko_search_research_prompts, aeko_get_product_analysis, aeko_get_visibility_summary, aeko_get_score, aeko_get_metrics, WebFetch, WebSearch
---

# Competitive Research — AI Visibility Gap Analysis

You are performing competitive research to help the user understand and outperform a competitor in AI engine visibility.

## Step 1: Parse input

Extract from the user's input:
- **Competitor name** and/or **URL**
- **Domain ID** (optional — if provided, pull AEKO context for the user's own domain)
- **Product category** or **market** (if mentioned)

If only a name is given, construct the likely URL. If only a URL is given, extract the brand name.

## Step 2: Gather AEKO context (if domain-id provided)

If the user provided their own domain-id, gather internal context:

1. Call `aeko_get_score` for the user's domain — establishes baseline AEKO Score
2. Call `aeko_get_metrics` — get 7-day trends to show trajectory
3. Call `aeko_get_visibility_summary` — detailed mentions, citations, sentiment
4. Call `aeko_get_suggestions` — check for any existing competitive gap suggestions
5. Call `aeko_search_research_prompts` with the competitor name — find prompts where the competitor appears

This gives you the user's current position and trajectory to compare against.

## Step 3: Research competitor's web presence

Use `WebSearch` to find:
- Competitor's main website and key product pages
- Competitor mentions in AI engine contexts (e.g., "best [product category]" queries)
- Competitor reviews, press coverage, and third-party mentions
- Competitor's social media presence and authority signals

Use `WebFetch` to analyze the competitor's key pages:

### Homepage / Main product page
- Check for JSON-LD structured data (Product, Organization, FAQ schemas)
- Note content structure: headings, FAQ sections, comparison tables
- Look for `robots.txt` AI crawler directives
- Check for `llms.txt`

### Product pages (2-3 examples)
- Content depth and citability patterns
- Pricing transparency
- Review/rating structured data
- Shipping and return policy structured data

## Step 4: Analyze competitor strengths

Assess the competitor across these dimensions:

| Dimension | What to check |
|-----------|--------------|
| **Structured Data** | JSON-LD types present, completeness, speakable markup |
| **Content Citability** | Answer blocks, self-contained passages, statistical density |
| **Entity Recognition** | Wikipedia/Wikidata presence, brand sameAs links |
| **Infrastructure** | robots.txt AI access, llms.txt, sitemap |
| **Content Strategy** | Blog/resource depth, FAQ coverage, comparison content |
| **Authority Signals** | Third-party mentions, review presence, press coverage |

Rate each dimension: Strong / Moderate / Weak / Not Found

## Step 5: Gap analysis

Compare the competitor's profile against the user's position (if domain-id was provided) or against AEO best practices.

Create a gap table:

```
| Dimension | User | Competitor | Gap | Opportunity |
|-----------|------|------------|-----|-------------|
| Product Schema | Basic | Complete | High | Add shipping, reviews, speakable |
| FAQ Content | None | 8 FAQs | Critical | Generate FAQ schema |
| Blog Content | 2 posts | 15+ posts | High | Content creation campaign |
```

Highlight:
- **Competitor advantages** — where they're ahead and what's working
- **User advantages** — where the user is already stronger
- **Untapped opportunities** — gaps neither party has filled

## Step 6: Structured competitive brief

Present findings as a structured brief:

### Competitor Profile
- Brand, URL, industry positioning
- Estimated content volume and freshness
- Key strengths (2-3 bullet points)

### AI Visibility Assessment
Rate the competitor's overall AEO readiness (A-F scale) with justification.

### Strategic Gaps (prioritized)

For each gap, provide:
1. **Gap**: What the competitor has that the user doesn't
2. **Impact**: How this affects AI engine recommendations (High/Medium/Low)
3. **Effort**: How hard it is to close the gap (Low/Medium/High)
4. **Action**: Specific step to take

### Content Opportunities

Identify 3-5 content pieces the user should create based on:
- Topics where the competitor ranks but the user doesn't
- Questions AI engines ask that neither party answers well
- Comparison queries where the user could win

## Step 7: Suggest follow-up actions

Based on findings, recommend specific AEKO skills:

- `/aeo-optimize` — if specific pages need optimization
- `/create-blog-article` — if content gaps were identified
- `/generate-jsonld` — if structured data is missing
- `/generate-faq` — if FAQ content would close a gap
- `/aeo-audit` — if the user wants to audit their own pages for comparison

Frame recommendations as a prioritized action plan with estimated impact.
