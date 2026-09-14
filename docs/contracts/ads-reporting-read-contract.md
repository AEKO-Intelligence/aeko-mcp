# OpenAI Ads reporting read contract

Module: `aeko_mcp/tools/marketing_reporting.py`. Backend authority: `aeko_backend/api/routes/marketing.py`
(`/ad-accounts`, `/product-insights`, `/conversion-insights`), `api/schemas/marketing.py`, and
`api/services/openai_ads/{product_insights,conversion_reporting}.py`. All three routes use
`require_dual_auth_with_rate_limit` and are Pro+ gated.

| Tool | Route | Contract |
| --- | --- | --- |
| `aeko_list_ad_accounts(domain_id)` | `GET /api/marketing/ad-accounts` | Every recorded account with selection fields (`id`, status, `connected`, name, provider IDs, currency, timezone, latest feed sync). SFTP, pixel and credential configuration are dropped. |
| `aeko_get_product_insights(domain_id, ad_account_id, date_from, date_to, scope="account", scope_id=None, limit=25, after=None)` | `GET /api/marketing/product-insights` | One live provider page sorted by product impressions. |
| `aeko_get_conversion_insights(domain_id, ad_account_id, date_from, date_to)` | `GET /api/marketing/conversion-insights` (`scope=campaign`) | Stored facts only; no provider call, no collection dispatch. |

## Invariants

- `ad_account_id` is required on product and conversion reads. The backend would otherwise choose a
  default account; the tools never let that happen silently.
- Local validation before any request: UUID IDs; strict `YYYY-MM-DD` dates with `date_to >= date_from`;
  product windows at most 93 inclusive days, conversion windows at most 92; product `scope` is
  `account` (no `scope_id`) or `campaign` (requires `scope_id`); `limit` 1..50; `after` 1..512 chars.
  Account-local completion (`MARKETING_PRODUCT_INSIGHTS_DATE_INCOMPLETE`), timezone (409) and campaign
  ownership (404) stay backend decisions and surface as returned.
- Exactly one GET per call. No auto-pagination, retry loop, refresh, dispatch or write.
- Payloads are returned verbatim inside a JSON block, with short notes above it. `null` metrics remain
  `null`; carousel card counts remain separate from billable impressions/clicks; `page.paging_blocked`
  and `blocked_reason` mean completeness is unknown.
- Conversion reports keep `state`, `state_reasons`, `blocked_reason`, coverage, refresh times,
  latest attempt/success, per-day status and attribution. Click-through and view-through are separate;
  event and click window stay `null`; view window is 1 day. Totals cover `reported_days` only.
- Errors use the shared client formatting (`[CODE] message` for structured details). The bearer token is
  never included in tool output.

Tests: `tests/test_marketing_reporting_tools.py` drives the registered tools through an `httpx.MockTransport`.
