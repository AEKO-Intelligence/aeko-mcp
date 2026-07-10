# AEKO MCP And Plugin Capability Tables

Tier shorthand:

- `Starter`: Available on Starter, subject to active subscription and plan limits.
- `Starter limited`: Base tool works on Starter, but specific arguments or destinations require Pro+.
- `Pro+`: Requires Pro or Enterprise.
- `N/A`: Local or generic skill behavior; backend gates depend on the tools it calls.

## aeko-mcp Tools

| Tool | One-line description | Starter | Pro+ gate |
|---|---|---:|---:|
| `aeko_add_domain` | Add an owned or comparison domain. | Yes, domain cap | No |
| `aeko_list_domains` | List domains for the authenticated user. | Yes | No |
| `aeko_get_domain_info` | Read domain metadata and AI-readiness flags. | Yes | No |
| `aeko_get_visibility_summary` | Read visibility overview, cited pages, or tracked-prompt metrics with filters. | Yes | No |
| `aeko_get_citability` | Read page or domain AI citability scoring. | Yes | No |
| `aeko_search_research_prompts` | Search prompt library candidates. | Yes | No |
| `aeko_get_tracked_prompts` | List tracked prompts and angle metadata. | Yes | No |
| `aeko_resolve_prompts_by_text` | Resolve prompt text to prompt ids. | Yes | No |
| `aeko_track_prompt` | Track a prompt with platform, country, view, and context angles. | Starter limited | Context angle requires Pro+ |
| `aeko_get_quota` | Read tracked-prompt and account limit status. | Yes | No |
| `aeko_untrack_prompt` | Stop tracking one prompt. | Yes | No |
| `aeko_get_tracked_prompt` | Read one tracked prompt with response and citation details. | Yes | No |
| `aeko_generate_starter_prompts` | Generate starter prompt candidates for a domain. | Yes | No |
| `aeko_accept_starter_prompts` | Accept generated starter prompts into tracking. | Yes, quota/platform caps | No |
| `aeko_update_markets` | Update selected markets. | Yes, 1 market | Pro gets higher market cap |
| `aeko_list_views` | List saved prompt views. | Yes, view cap | Pro gets higher cap |
| `aeko_create_view` | Create a saved prompt view. | Yes, view cap | Pro gets higher cap |
| `aeko_add_prompts_to_view` | Add tracked prompts to a saved view. | Yes | No |
| `aeko_list_contexts` | List curated Context library memories. | No | Pro+ |
| `aeko_create_context` | Create a curated Context memory. | No | Pro+ |
| `aeko_update_context` | Update a curated Context memory. | No | Pro+ |
| `aeko_archive_context` | Archive a curated Context memory. | No | Pro+ |
| `aeko_create_contexts_from_reviews` | Promote review grounding into curated Context memories. | No | Pro+ |
| `aeko_list_review_integrations` | List connected review sources. | No | Pro+ |
| `aeko_list_review_products` | List products with review/context counts. | No | Pro+ |
| `aeko_get_product_reviews` | Read contextual reviews for one product. | No | Pro+ |
| `aeko_get_suggested_prompts` | Read review-derived suggested prompts. | No | Pro+ |
| `aeko_track_suggested_prompt` | Track one review-derived prompt with grounding. | No | Pro+ |
| `aeko_track_suggested_prompts` | Batch-track top review-derived prompts. | No | Pro+ |
| `aeko_dismiss_suggested_prompt` | Dismiss a review-derived prompt suggestion. | No | Pro+ |
| `aeko_inject_reviews` | Inject real reviews into a manual review source. | No | Pro+ |
| `aeko_connect_store` | Connect Cafe24 or Shopify store credentials. | Yes | No |
| `aeko_sync_store` | Sync connected store products. | Yes | No |
| `aeko_inject_products` | Inject manual/custom-store products. | Yes | No |
| `aeko_list_store_products` | List synced or injected store products. | Yes | No |
| `aeko_list_store_integrations` | List connected store integrations. | Yes | No |
| `aeko_get_product_description` | Read editable PDP HTML from a store. | Yes | No |
| `aeko_update_product_description` | Write PDP description HTML with audit trail. | Yes | No |
| `aeko_update_product_tags` | Write product tags. | Yes | No |
| `aeko_update_product_meta` | Write SEO meta fields. | Yes | No |
| `aeko_list_store_writes` | List store-write audit entries. | Yes | No |
| `aeko_revert_store_write` | Revert a prior store write. | Yes | No |
| `aeko_list_action_items` | List action-plan items. | Yes | No |
| `aeko_list_technical_items` | List technical-plan items. | Yes | No |
| `aeko_get_action_plan` | Fetch Plan.md for an item. | Yes | No |
| `aeko_create_action_item` | Create an action item and enqueue Plan.md generation. | Starter limited | Context grounding requires Pro+ |
| `aeko_dismiss_action_item` | Dismiss an action item. | Yes | No |
| `aeko_complete_action_item` | Mark an action item complete. | Yes | No |
| `aeko_save_content_variation` | Save a publishable content variation. | Yes | No |
| `aeko_update_content_variation` | Edit an unpublished saved variation. | Yes | No |
| `aeko_list_content_variations` | List saved variations for an action item. | Yes | No |
| `aeko_publish_content_variation` | Publish a saved variation to its destination. | Starter limited | `aeko_shop` publish requires Pro+ |
| `aeko_unpublish_content` | Unpublish an aeko.shop post. | No | Pro+ |
| `aeko_list_own_content` | List owned content records. | Yes | No |
| `aeko_request_media_upload` | Request backend media upload/presign flow. | Yes | No |
| `aeko_get_share_of_voice` | Read share-of-voice analytics. | Yes | No |
| `aeko_get_answer_drift` | Read answer drift analytics. | Yes | No |
| `aeko_get_measure` | Read Measure readiness, discovery, or impact. | Yes | No |
| `aeko_get_ga4_status` | Read GA4 connection/property status. | Yes | No |
| `aeko_list_ga4_properties` | List GA4 properties after browser OAuth connection. | Yes | No |
| `aeko_select_ga4_property` | Select the GA4 property for Measure. | Yes | No |
| `aeko_sync_ga4` | Trigger GA4 metrics sync. | Yes | No |
| `aeko_list_contextual_reviews` | Pull domain-wide contextual review pool for ads. | No | Pro+ |
| `aeko_list_campaigns` | List OpenAI Ads campaigns. | No | Pro+ |
| `aeko_list_ad_groups` | List OpenAI Ads ad groups. | No | Pro+ |
| `aeko_list_ads` | List OpenAI Ads ads. | No | Pro+ |
| `aeko_get_ad_insights` | Read OpenAI Ads performance metrics. | No | Pro+ |
| `aeko_get_ad_account_status` | Read OpenAI Ads account status. | No | Pro+ |
| `aeko_get_feed_status` | Read OpenAI Ads feed readiness. | No | Pro+ |
| `aeko_sync_feed` | Queue OpenAI Ads product-feed sync. | No | Pro+ |
| `aeko_create_ad_group_from_context` | Create a paused context-grounded ad group and ads. | No | Pro+ |
| `aeko_update_campaign_budget` | Guarded campaign budget update. | No | Pro+ |
| `aeko_set_campaign_state` | Pause, resume, or archive a campaign. | No | Pro+ |
| `aeko_set_ad_group_state` | Pause, resume, or archive an ad group. | No | Pro+ |
| `aeko_set_ad_state` | Pause, resume, or archive an ad. | No | Pro+ |

## aeko-plugin Skills

| Skill | Expected behavior and outcome | Possible today | Beyond / gated |
|---|---|---|---|
| `/aeko-onboarding` | Confirms setup, explains available skills, and routes the user to the right next workflow. | Works for all tiers. | Pro-only workflows are described as gated. |
| `/aeko-setup-store` | Adds a domain, connects or injects products, generates starter prompts, and updates markets. | Starter can complete basic setup, manual products, starter prompts, and one market. | Review sources, Context library, ads, and aeko.shop publish are Pro+. |
| `/aeko-action-center` | Lists actionable Technical/PDP/Content items and dispatches to executor skills. | Starter can execute Starter-tier items. | Context-grounded content plans and Pro suggestions depend on Pro+. |
| `/aeko-update-pdp` | Uses Plan.md to draft PDP improvements and store-write artifacts. | Starter can run PDP items and store writes. | Shadow-product backend write is still not exposed; current backend stamps `preview_only`. |
| `/aeko-fix-technical` | Produces crawler/schema/site technical fixes from Plan.md. | Starter can run technical items. | None beyond normal site/file access. |
| `/aeko-create-content` | Drafts citation-ready content from Plan.md and saves backend content variations. | Starter can run content artifact items when created. | Context IDs and aeko.shop publish destination require Pro+. |
| `/aeko-publish-content` | Publishes saved content variations after confirmation. | Starter can use non-aeko.shop draft destinations. | Publishing/unpublishing live aeko.shop posts is Pro+. |
| `/aeko-find-prompts-to-track` | Finds prompt candidates and tracks selected prompts with supported angles. | Starter can add prompts within quota, one market, OpenAI platform. | Context angle and review-suggested prompt flows require Pro+. |
| `/aeko-manage-tracked-prompts` | Reviews tracked prompts by angle/quota and untracks when needed. | Starter can manage tracked prompts. | Context-related views only appear when available. |
| `/aeko-prompt-deep-dive` | Explains one tracked prompt's responses, citations, and next action. | Starter can inspect tracked prompt data. | Depends on having tracked prompts/responses. |
| `/aeko-visibility-report` | Produces a visibility report from summary, tracked prompts, and analytics. | Starter can run visibility/SOV/drift/Measure reads. | Broader platforms/countries depend on tier limits. |
| `/aeko-brand-competitor-analysis` | Compares a competitor's public positioning with AEKO citation data. | Starter can run with WebSearch/WebFetch and tracked prompt data. | Depth depends on available tracked prompt coverage. |
| `/aeko-product-competitor-analysis` | Compares one product against competitor PDPs. | Starter can run with store reads and web fetches. | Context reviews or richer ad/review data are Pro+. |
| `/aeko-refresh-jsonld` | Refreshes existing product JSON-LD facts and writes back with audit trail. | Starter can run store-write updates. | No create-from-scratch JSON-LD; it updates existing blocks. |
| `/aeo-audit` | Generic URL-level AEO/shopping readiness audit. | Works without AEKO backend data. | Not an AEKO-measured score. |
| `/aeko-inject-reviews` | Injects real reviews for stores without a review app. | Not available on Starter. | Pro+ only; real reviews only, no fabrication. |
| `/aeko-compose-ads` | Pulls contextual reviews and creates paused OpenAI Ads groups. | Not available on Starter. | Pro+ with connected OpenAI Ads account; live writes stay paused for review. |
| `/aeko-ad-report` | Generates OpenAI Ads performance report from efficiency metrics. | Not available on Starter. | Pro+; ROAS waits for conversion ingestion. |
| `/aeko-optimize-budget` | Dry-runs and confirms guarded campaign budget changes and pauses waste. | Not available on Starter. | Pro+; spend writes require confirmation and guardrails. |

## Starter Clarifications

- Starter can add and track prompts through MCP. Limits are 100 tracked prompts, 1 market, and OpenAI-only platform unless account limits are overridden.
- Starter can create basic action items for Starter-tier artifacts and execute PDP/content/technical workflows when those items exist.
- Starter cannot use Context Reviews, Context library, OpenAI Ads, or aeko.shop live publishing.
- Publishing to aeko.shop is Pro+ only. Saving a variation or producing an own-store draft is separate from live aeko.shop publish.
