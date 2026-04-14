---
name: aeko-update-pdp
description: >
  Own Store · Product Detail Update. Rewrites a product page's description,
  regenerates JSON-LD, and generates an FAQ block using an AEKO v2 suggestion
  brief. Opens a browser preview and marks the suggestion complete.
argument-hint: <suggestion-key>
allowed-tools: Read, Write, Bash(open *), Bash(xdg-open *)
---

# AEKO · Update Product Detail Page

You are executing a single `pdp_update` suggestion from AEKO v2.

## Step 1: Load the brief

Call `aeko_get_pdp_brief(suggestion_key)`. This returns:
- The suggestion's rich brief (`target_url`, `structure`, `topics`, `persona`, `tone`, `required_jsonld`, `must_include`)
- The suggestion's `domain_id` (needed for JSON-LD generation in Step 3)
- Current page analysis (AI-readiness score, issues)
- Current citability score and top improvements
- Competitor source evidence (which structures won the cited spots)

If the suggestion isn't a `pdp_update`, stop and tell the user which skill to use instead.

**Resolving domain_id**: the tool surfaces `domain_id` from the brief payload. If it is missing (the backend did not include it), ask the user for the domain UUID — do not guess. Then re-call `aeko_get_pdp_brief(suggestion_key, domain_id="<uuid>")` so the current-page-analysis extras section populates.

## Step 1b: Mirror competitor evidence structure

Before drafting, list the headings from every `source_evidence[].structure` in the brief. **Your draft's H2/H3 spine must be a superset of those headings.** This is the load-bearing step — `source_evidence` ships so you can mirror what's already winning AI citations. Do not skip it.

## Step 2: Draft the optimized PDP

Write a new product description that:
1. Mirrors the brief's `structure` exactly (H2s, tables, FAQ block, etc.)
2. Covers every topic in `brief.topics`
3. Matches `brief.persona` and `brief.tone`
4. Meets `brief.word_count_target` if present
5. Addresses the issues from the current page analysis
6. Fixes the top citability improvements

**Bilingual by default**: if the domain is Korean (check `aeko_get_domain_info` for `ko_name` or the base URL TLD), output both KO and EN versions side-by-side. Korean cross-border sellers need both for Naver/Google/ChatGPT coverage.

## Step 3: Generate JSON-LD

For every schema type in `brief.required_jsonld`, call `aeko_prepare_json_ld(domain_id, schema_type, page_url=target_url)` and generate complete JSON-LD. Include every field in `brief.must_include`.

## Step 4: Generate FAQ block

Call `aeko_search_research_prompts(scope=<domain scope from aeko_get_domain_info>, keyword=<first topic from brief.topics>)`. If a `group_id` was selected in `/aeko-action-center`, prefer narrowing by the group scope. Use the returned prompts to generate 6-10 FAQ Q&As that match real AI queries. Output as both visible HTML and FAQPage JSON-LD.

## Step 5: Preview

Call `aeko_preview_optimized_page(...)` to generate the side-by-side HTML preview (Original / Optimized / Diff / JSON-LD). Open it in the browser.

## Step 6: Save and complete

1. `aeko_save_content("pdp/<slug>.html", <full optimized HTML>)`
2. `aeko_save_content("pdp/<slug>.jsonld.json", <JSON-LD>)`
3. `aeko_complete_suggestion(suggestion_key)` — if this fails, surface the exact error message to the user instead of silently moving on.

Report: file paths saved, key wins (score delta estimate, structure changes, schema added), and what the user should do next to publish — match the CMS to the domain:
- **Shopify**: admin → Products → paste HTML + upload JSON-LD snippet
- **Cafe24**: 상품관리 → 상품수정 → 상세설명 (paste HTML) + 검색엔진최적화(SEO) for JSON-LD
- **Naver Smartstore**: 상품관리 → 상품등록/수정 → 상세설명
- Generic: paste HTML into the product description editor and add JSON-LD via the theme's `<head>` injection point.
