---
name: aeko-draft-from-campaign
description: >
  Persona-driven content drafting from a Campaign. Picks one Content
  Recommendation, fetches the curated competitor source URLs as research
  material, drafts content grounded in those sources, saves locally, and
  marks the recommendation complete. Replaces the manual "find topics +
  WebSearch + draft" loop with a backend-curated brief.
argument-hint: <campaign-id-or-name>
allowed-tools: Read, Write
---

# AEKO · Draft from Campaign

You are drafting content for one persona-gap-driven Content Recommendation
within an AEKO Campaign. The backend has already done the hard work of:

1. Detecting which persona segments the brand is weak in
2. Clustering the user's tracked prompts by topic
3. Curating up to 5 competitor URLs that are currently winning AI citations
   for those exact prompts

Your job is to use those curated sources as research material, mirror their
winning structure, and produce a draft the user can publish.

## Step 1: List campaigns and pick one

If the user gave a campaign name, search:
```
aeko_list_campaigns(domain_id=<from context>)
```
Find the matching campaign by name. If they gave a UUID, use it directly.

If no campaign is specified, list all active campaigns and ask the user to
pick one. **Never** auto-pick a campaign without user confirmation.

## Step 2: List active recommendations for the campaign

```
aeko_get_content_recommendations(campaign_id)
```

This returns up to 10 active recommendations sorted by priority (worst gap
first). Each one has:
- `cluster_label` — the topical cluster (e.g., "mattress firmness · decision stage")
- `persona_label_en` — the persona segment the brand is weak in
- `weakness_signal` — brand_visibility vs top_3_competitor_visibility, gap %
- `suggested_channels` — primary channel + alternatives
- `curated_sources` — competitor URLs that are winning AI citations on this cluster

Present them to the user as a numbered list. Surface:
- The cluster label and persona
- The brand visibility gap ("Brand visibility 12 vs top-3 competitor avg 75 — 84% gap")
- The primary suggested channel ("blog_post" / "wikipedia_section" / etc.)
- The number of curated sources

Ask the user which one they want to draft. Do not auto-pick.

## Step 3: Load full detail for the chosen recommendation

```
aeko_get_content_recommendation(recommendation_id)
```

This gives you the complete `draft_brief` (structure spine, topics, tone,
word count target, required JSON-LD, must_include checklist) and the full
list of curated source URLs with key excerpts and headings.

## Step 4: Fetch each curated source's full content

For each `curated_sources[].url`, call:
```
aeko_fetch_source_content(url)
```

This returns the previously-crawled extracted text (capped at 12KB), the
page's headings, and JSON-LD types. **This is your primary research
material.** Do NOT do an independent WebSearch — the backend has already
filtered to the URLs that matter for this campaign's prompts.

If a fetch returns 404 ("URL not crawled"), skip that source and proceed
with the others.

## Step 5: Mirror the winning structure

Inspect the `headings` arrays from the curated sources. Your draft's H2/H3
spine must be a **superset** of the most common headings across the
competitor pages. If 3 of 5 competitors have an "h2: FAQ" section, yours
must too. This is the load-bearing differentiator — these sources are
literally the URLs that AI engines are citing for the user's tracked prompts.

Combine that with the `draft_brief.structure` array which gives you a
default spine for the primary channel. Use the longer/richer of the two.

## Step 6: Draft the content

Following the brief:
- Match the primary channel's tone (`draft_brief.tone`)
- Hit the `word_count_target`
- Cover every `draft_brief.topics` entry
- Tick every `draft_brief.must_include` item
- Open every H2 with an "answer-block" — first 2-3 sentences should be
  directly quotable by an AI engine
- High statistical density (concrete numbers, comparisons, tables)
- Self-contained sections (no "as mentioned above")
- Bilingual (KO + EN) if `draft_brief.target_domain` is a cross-border
  Korean store

For Wikipedia (`primary_channel == "wikipedia_section"`), use neutral POV
and cite at least 3 reliable third-party sources inline.

For Naver 블로그 (`primary_channel == "naver_blog"`), use conversational
Korean with first-person experience and H2/H3 structure.

For press release (`primary_channel == "press_release"`), follow the
headline → dateline → lead → quote → boilerplate → contact format.

## Step 7: Generate required JSON-LD

For each type in `draft_brief.required_jsonld`, produce complete schema.org
markup. Use the existing `aeko_prepare_json_ld(domain_id, schema_type)`
tool if you need a starter template.

## Step 8: Save locally

```
aeko_save_content("content/campaigns/<campaign-slug>/<recommendation-slug>.md", <full draft>)
aeko_save_content("content/campaigns/<campaign-slug>/<recommendation-slug>.jsonld.json", <json-ld>)
```

Use the cluster_label as the recommendation slug. Use the campaign name as
the campaign slug. Both slugified to lowercase-with-dashes.

## Step 9: Confirm and mark complete

Show the user the saved file paths and a summary of what you drafted.
**Ask for explicit confirmation** before marking the recommendation complete:

> "I've drafted a {channel} for the {persona_label_en} persona on the
> {cluster_label} topic, saved to {file_path}. Should I mark this
> recommendation complete? (This frees a slot for the next regeneration to
> surface a different gap.)"

If they confirm:
```
aeko_complete_content_recommendation(recommendation_id)
```

If they want to revise first, leave the recommendation active. The user can
mark it complete later via `aeko_complete_content_recommendation` directly.

## Notes

- **Tier gating**: This skill only works for Growth+ tier users. If
  `aeko_get_content_recommendations` returns "Content Recommendations
  require Growth tier or above", politely tell the user to upgrade and
  fall back to the older `/aeko-create-own-content` skill which works on
  all paid tiers.
- **No campaign yet?** If the user has no active campaigns, suggest
  creating one with `aeko_create_campaign` first.
- **Empty recommendations?** If `aeko_get_content_recommendations` returns
  an empty list, suggest one of: (a) wait for the next AI prompt refresh,
  (b) call `aeko_regenerate_content_recommendations` (rate-limited 1/hour),
  (c) confirm the campaign has at least 3 tracked prompts.
- **Cap full?** If `aeko_regenerate_content_recommendations` reports
  `skipped_cap_full > 0`, the campaign has hit the 10-active-recommendations
  cap. Suggest dismissing or completing some existing ones first.
