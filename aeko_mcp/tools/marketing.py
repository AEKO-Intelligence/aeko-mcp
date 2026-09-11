"""MCP tools for agentic OpenAI-Ads ad ops — the thin layer under the aeko-plugin ad skills.

These wrap the AEKO backend's ``/api/marketing/*`` routes (and the domain-wide contextual-reviews +
manual-review-inject routes under ``/api/review-integrations/*``) so a plugin skill can:

  - pull contextual reviews across a whole domain and compose broader, cross-product ad groups
    (``aeko_list_contextual_reviews`` -> ``aeko_create_ad_group_from_context``),
  - inject real reviews it gathered for merchants without a review app (``aeko_inject_reviews``),
  - read ad performance and reallocate budget by performance (``aeko_get_ad_insights`` +
    ``aeko_update_campaign_budget``), and pause wasteful ads/campaigns (``aeko_set_ad_state`` /
    ``aeko_set_campaign_state``),
  - validate, preview, explicitly arm, audit, and globally stop automated pacing rules.

Design rules (mirror the skill/tool split):
  - Reasoning (clustering, ranking, deciding) lives in the SKILL; these tools stay thin (~1:1 to a
    backend route).
  - Tools that feed a later tool call return a machine-parseable JSON block (explicit IDs), not just
    prose, so a skill can chain list -> create.
  - Direct OpenAI-Ads entity/feed WRITE routes that support replay protection take a stable,
    caller-supplied ``idempotency_key`` (the skill mints ONE per logical action, reused on retries).
    The pacing-rule routes instead expose idempotent state transitions and a separately explicit
    enable step, matching their backend contract without an idempotency header.
  - Spend is real: ``aeko_update_campaign_budget`` defaults to dry-run and enforces an absolute
    ceiling + max per-call delta at the TOOL layer (the backend only enforces a floor).
  - State changes can pause, confirm-gated resume, or confirm-gated archive.

All routes are Pro+ gated server-side; an under-tier account surfaces the backend 403 verbatim.
"""
import json
from typing import Any, Optional

from ..server import client, mcp
from ._annotations import DESTRUCTIVE, READ_ONLY, WRITE, WRITE_ONCE

# Backend enforces this floor on campaign budgets (schemas/marketing.py MarketingBudget).
MIN_BUDGET_MICROS = 1_000_000
# Backend bidding schema accepts 1..100_000_000 micros per billing event.
MIN_BID_MICROS = 1
MAX_BID_MICROS = 100_000_000
# Backend caps one inject request at 200 reviews (schemas/review.py ReviewInjectRequest).
INJECT_REVIEWS_BATCH_SIZE = 200
# Backend caps ads per ad group at 100 (schemas/marketing.py MarketingAdGroupFromContextRequest).
MAX_ADS_PER_AD_GROUP = 100
# Backend requires >= 3 chars for new campaign / ad-group names (schemas/marketing.py).
MIN_NAME_LENGTH = 3
CAMPAIGN_BILLING_EVENT = {
    "impressions": "impression",
    "clicks": "click",
    "conversions": "click",
}


def _safe(method, *args, **kwargs) -> tuple[Any, Optional[str]]:
    """Wrap client errors into ``(None, message)`` for graceful tool output (mirrors reviews._safe)."""
    try:
        return method(*args, **kwargs), None
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


def _json_block(title: str, payload: Any) -> str:
    """Render a result as a short header + a fenced JSON block a skill can parse."""
    return f"# {title}\n\n```json\n{json.dumps(payload, ensure_ascii=False, indent=2, default=str)}\n```"


def _idem_headers(idempotency_key: str) -> dict[str, str]:
    return {"Idempotency-Key": idempotency_key}


def _ad_rule_payload(
    *,
    domain_id: str,
    name: str,
    scope_level: str,
    scope_filter: dict,
    match: str,
    conditions: list[dict],
    action: str,
    guards: dict,
    cooldown_minutes: int,
    max_actions_per_day: int,
    max_entities_per_run: int,
    description: Optional[str],
) -> dict[str, Any]:
    """Build the shared create/validate rule body with MCP-safe fixed fields."""
    return {
        "domain_id": domain_id,
        "name": name,
        "description": description,
        "enabled": False,
        "scope_level": scope_level,
        "scope_filter": scope_filter,
        "match": match,
        "conditions": conditions,
        "guards": guards,
        "action": action,
        "cooldown_minutes": int(cooldown_minutes),
        "max_actions_per_day": int(max_actions_per_day),
        "max_entities_per_run": int(max_entities_per_run),
        "created_by": "mcp",
    }


# --- Reviews: domain-wide pull + inject -------------------------------------------


@mcp.tool(title="List contextual reviews (domain-wide)", annotations=READ_ONLY)
def aeko_list_contextual_reviews(
    domain_id: str,
    min_context_score: int = 60,
    limit: int = 200,
) -> str:
    """Pull every contextual review across a WHOLE domain (all products + review sources) as one
    flat, structured list — the pull-then-cluster input for composing cross-product ad groups.

    Each item carries stable IDs (``review_id``, ``store_product_id``, ``external_product_ref``),
    the product title/image, the ``context_score``, the PRE-purchase facets (``customer_state``,
    ``recent_concern``, ``occasion``, ``recipient``, ``product_experience``), and the precomputed
    ad creative (``ad_body``, ``ad_context_hints``). Cluster reviews by a shared shopper-situation
    facet (e.g. several products all matching ``customer_state='민감성 피부'`` or ``occasion='선물'``),
    then pass the cluster's ``store_product_id``s + a broader composed hint to
    ``aeko_create_ad_group_from_context``.
    """
    capped_score = max(0, min(int(min_context_score), 100))
    capped_limit = max(1, min(int(limit), 1000))
    result, err = _safe(
        client.get,
        "/api/review-integrations/contextual-reviews",
        params={"domain_id": domain_id, "min_context_score": capped_score, "limit": capped_limit},
    )
    if err:
        return f"# Failed to list contextual reviews\n\n```\n{err}\n```"
    items = result if isinstance(result, list) else []
    if not items:
        return (
            f"# No contextual reviews (score >= {capped_score}) for domain `{domain_id}`.\n\n"
            "Connect a review source or inject reviews (aeko_inject_reviews), then wait for "
            "classification to populate the context facets."
        )
    return _json_block(f"{len(items)} contextual reviews for domain `{domain_id}`", items)


@mcp.tool(title="Inject reviews", annotations=WRITE_ONCE)
def aeko_inject_reviews(domain_id: str, reviews: list[dict]) -> str:
    """Inject REAL reviews the skill gathered (from the web/marketplaces) or the merchant provided
    into a domain's credential-less ``manual`` source, so merchants without a cre.ma/Judge.me app
    still get review-grounded context + ads. Real reviews only — NEVER fabricate.

    Each review dict: ``external_review_id`` (a STABLE deterministic id you derive, e.g.
    sha256(source_url+body) — makes re-injection idempotent), ``external_product_ref`` (the store's
    external product id it belongs to), ``body`` (required), and optional ``rating`` (1-5),
    ``title``, ``author_name``, ``lang``, ``review_created_at`` (ISO8601), ``source_url``,
    ``source_method`` ('web_gather' | 'merchant_paste'). Reviews bind to a currently-SELLING product
    by ``external_product_ref``; unmatched refs are skipped and reported back. Requires a connected
    store (Cafe24/Shopify). Classification (facets + ad creative) runs automatically after insert.
    The backend caps one request at 200 reviews — larger lists are chunked into <=200 batches here
    and the results aggregated into a single summary.
    """
    if not reviews:
        return "# No reviews to inject — pass a non-empty `reviews` list."
    if len(reviews) <= INJECT_REVIEWS_BATCH_SIZE:
        result, err = _safe(
            client.post,
            "/api/review-integrations/inject",
            json={"domain_id": domain_id, "reviews": reviews},
        )
        if err:
            return f"# Failed to inject reviews\n\n```\n{err}\n```"
        return _json_block("Reviews injected", result)
    # Over the backend's per-request cap — chunk, call per batch, and aggregate the counts.
    batches = [
        reviews[i : i + INJECT_REVIEWS_BATCH_SIZE]
        for i in range(0, len(reviews), INJECT_REVIEWS_BATCH_SIZE)
    ]
    combined: dict[str, Any] = {
        "requested": len(reviews),
        "batches": len(batches),
        "batches_completed": 0,
        "inserted": 0,
        "updated": 0,
        "skipped_unmatched": 0,
        "unmatched_refs": [],
        "classification_enqueued": False,
    }
    seen_refs: set[str] = set()
    for batch_no, batch in enumerate(batches, start=1):
        result, err = _safe(
            client.post,
            "/api/review-integrations/inject",
            json={"domain_id": domain_id, "reviews": batch},
        )
        if err:
            return (
                f"# Failed to inject reviews (batch {batch_no}/{len(batches)} — "
                f"earlier batches were already applied)\n\n```\n{err}\n```\n\n"
                + _json_block("Partial progress before the failure", combined)
            )
        data = result if isinstance(result, dict) else {}
        combined["batches_completed"] = batch_no
        combined["inserted"] += int(data.get("inserted") or 0)
        combined["updated"] += int(data.get("updated") or 0)
        combined["skipped_unmatched"] += int(data.get("skipped_unmatched") or 0)
        for ref in data.get("unmatched_refs") or []:
            if ref not in seen_refs:
                seen_refs.add(ref)
                combined["unmatched_refs"].append(ref)
        combined["classification_enqueued"] = combined["classification_enqueued"] or bool(
            data.get("classification_enqueued")
        )
        if data.get("integration_id") is not None:
            combined["integration_id"] = data.get("integration_id")
    return _json_block(f"Reviews injected ({len(batches)} batches)", combined)


# --- Campaign / ad group / ad reads -----------------------------------------------


@mcp.tool(title="List ad campaigns", annotations=READ_ONLY)
def aeko_list_campaigns(domain_id: str, ad_account_id: Optional[str] = None) -> str:
    """List a domain's OpenAI-Ads campaigns, including each campaign's ``bidding_type``,
    ``conversion_event_setting_ids``, and ``product_feed_id``. Pass ``ad_account_id`` when the
    domain has more than one ad account. Use the returned ``id`` for child reads or updates."""
    params = {"domain_id": domain_id}
    if ad_account_id:
        params["ad_account_id"] = ad_account_id
    result, err = _safe(client.get, "/api/marketing/campaigns", params=params)
    if err:
        return f"# Failed to list campaigns\n\n```\n{err}\n```"
    items = result if isinstance(result, list) else []
    return _json_block(f"{len(items)} campaigns for domain `{domain_id}`", items)


@mcp.tool(title="List ad groups", annotations=READ_ONLY)
def aeko_list_ad_groups(campaign_id: str) -> str:
    """List the ad groups under a campaign (id, name, status, context_hints)."""
    result, err = _safe(client.get, "/api/marketing/ad-groups", params={"campaign_id": campaign_id})
    if err:
        return f"# Failed to list ad groups\n\n```\n{err}\n```"
    items = result if isinstance(result, list) else []
    return _json_block(f"{len(items)} ad groups for campaign `{campaign_id}`", items)


@mcp.tool(title="List ads", annotations=READ_ONLY)
def aeko_list_ads(ad_group_id: str) -> str:
    """List the ads under an ad group (id, name, status, creative). Use an ``id`` as ``ad_id``
    to pause a wasteful ad with ``aeko_set_ad_state``."""
    result, err = _safe(client.get, "/api/marketing/ads", params={"ad_group_id": ad_group_id})
    if err:
        return f"# Failed to list ads\n\n```\n{err}\n```"
    items = result if isinstance(result, list) else []
    return _json_block(f"{len(items)} ads for ad group `{ad_group_id}`", items)


@mcp.tool(title="Get ad performance insights", annotations=READ_ONLY)
def aeko_get_ad_insights(
    domain_id: str,
    date_from: str,
    date_to: str,
    scope: str = "account",
    scope_id: Optional[str] = None,
    segment: Optional[str] = None,
    limit: int = 200,
    ad_account_id: Optional[str] = None,
) -> str:
    """Pull performance metrics (impressions, clicks, spend_micros, ctr, cpc_micros, cpm_micros) for
    reporting or budget decisions. ``scope`` = account | campaign | ad_group | ad (non-account needs
    ``scope_id``); ``segment`` = product | country | device (optional). ``date_from``/``date_to`` are
    ISO dates (YYYY-MM-DD). The API does NOT rank — sort/aggregate in the skill.

    NOTE: conversions/ROAS are not yet ingested; rank on efficiency proxies (CTR, CPC, spend, clicks)."""
    params: dict[str, Any] = {
        "domain_id": domain_id,
        "scope": scope,
        "date_from": date_from,
        "date_to": date_to,
        "limit": max(1, min(int(limit), 2000)),
    }
    if scope_id:
        params["scope_id"] = scope_id
    if segment:
        params["segment"] = segment
    if ad_account_id:
        params["ad_account_id"] = ad_account_id
    result, err = _safe(client.get, "/api/marketing/insights", params=params)
    if err:
        return f"# Failed to get insights\n\n```\n{err}\n```"
    return _json_block(f"Insights ({scope}, {date_from} → {date_to})", result)


@mcp.tool(title="Get ad account status", annotations=READ_ONLY)
def aeko_get_ad_account_status(
    domain_id: str, ad_account_id: Optional[str] = None
) -> str:
    """Read OpenAI Ads account connection/feed credential status for a domain.

    Pro+ gated server-side. Secrets are never returned by the backend.
    """
    params = {"domain_id": domain_id}
    if ad_account_id:
        params["ad_account_id"] = ad_account_id
    result, err = _safe(client.get, "/api/marketing/ad-account", params=params)
    if err:
        return f"# Failed to get ad account status\n\n```\n{err}\n```"
    return _json_block("Ad account status", result)


@mcp.tool(title="Get feed status", annotations=READ_ONLY)
def aeko_get_feed_status(domain_id: str, ad_account_id: Optional[str] = None) -> str:
    """Read OpenAI Ads product-feed readiness and latest sync status."""
    params = {"domain_id": domain_id}
    if ad_account_id:
        params["ad_account_id"] = ad_account_id
    result, err = _safe(client.get, "/api/marketing/feed", params=params)
    if err:
        return f"# Failed to get feed status\n\n```\n{err}\n```"
    return _json_block("Feed status", result)


@mcp.tool(title="Sync product feed", annotations=WRITE)
def aeko_sync_feed(
    domain_id: str,
    idempotency_key: str,
    ad_account_id: Optional[str] = None,
) -> str:
    """Queue an OpenAI Ads product-feed sync for a connected ad account."""
    params = {"domain_id": domain_id}
    if ad_account_id:
        params["ad_account_id"] = ad_account_id
    result, err = _safe(
        client.post,
        "/api/marketing/feed/sync",
        params=params,
        headers=_idem_headers(idempotency_key),
    )
    if err:
        return f"# Failed to sync feed\n\n```\n{err}\n```"
    return _json_block("Feed sync queued", result)


@mcp.tool(title="List OpenAI Ads conversion event settings", annotations=READ_ONLY)
def aeko_list_conversion_event_settings(
    domain_id: str,
    ad_account_id: Optional[str] = None,
    limit: int = 20,
    after: Optional[str] = None,
    before: Optional[str] = None,
    order: str = "desc",
) -> str:
    """List the current ad account's conversion event settings before creating an oCPC campaign.

    Choose one row where ``eligible_for_optimization`` is true and pass its ``id`` as the sole item
    in ``conversion_event_setting_ids``. Rows include event type, source, attribution window, and a
    reason when ineligible. Pass ``ad_account_id`` for an explicit account. Pagination accepts one
    of ``after`` or ``before`` and an ``order`` of ``asc`` or ``desc``.
    """
    if after and before:
        return "# Choose either `after` or `before` pagination, not both."
    normalized_order = (order or "").strip().lower()
    if normalized_order not in {"asc", "desc"}:
        return "# `order` must be `asc` or `desc`."
    params: dict[str, Any] = {
        "domain_id": domain_id,
        "limit": max(1, min(int(limit), 500)),
        "order": normalized_order,
    }
    if ad_account_id:
        params["ad_account_id"] = ad_account_id
    if after:
        params["after"] = after
    if before:
        params["before"] = before
    result, err = _safe(
        client.get, "/api/marketing/conversions/event-settings", params=params
    )
    if err:
        return f"# Failed to list conversion event settings\n\n```\n{err}\n```"
    return _json_block("Conversion event settings", result)


@mcp.tool(title="Look up OpenAI Ads locations", annotations=READ_ONLY)
def aeko_lookup_ad_locations(
    domain_id: str,
    q: str,
    ad_account_id: Optional[str] = None,
    limit: int = 10,
) -> str:
    """Search the current ad account's location catalog. Use returned location ``id`` values in
    campaign ``targeting.locations.include`` entries such as ``[{\"id\": \"geo_123\"}]``.
    Pass ``ad_account_id`` for an explicit account. The search text must contain at least 2 chars.
    """
    query = (q or "").strip()
    if len(query) < 2:
        return "# `q` must contain at least 2 characters."
    params: dict[str, Any] = {
        "domain_id": domain_id,
        "q": query,
        "limit": max(1, min(int(limit), 50)),
    }
    if ad_account_id:
        params["ad_account_id"] = ad_account_id
    result, err = _safe(client.get, "/api/marketing/geo-lookup", params=params)
    if err:
        return f"# Failed to look up ad locations\n\n```\n{err}\n```"
    return _json_block(f"Ad locations matching `{query}`", result)


# --- Automated pacing / guardrail rules -------------------------------------------


@mcp.tool(title="List OpenAI Ads pacing rules", annotations=READ_ONLY)
def aeko_list_ad_rules(domain_id: str, include_disabled: bool = False) -> str:
    """List non-deleted pacing rules for a domain.

    By default only enabled rules are returned. Set ``include_disabled=True`` to include drafts and
    disabled rules. Each response includes the complete saved definition, enabled state, version,
    account currency/timezone snapshot, evaluation timestamps, and trigger count.
    """
    result, err = _safe(
        client.get,
        "/api/marketing/rules",
        params={
            "domain_id": domain_id,
            "include_disabled": bool(include_disabled),
        },
    )
    if err:
        return f"# Failed to list ad rules\n\n```\n{err}\n```"
    items = result if isinstance(result, list) else []
    return _json_block(f"{len(items)} ad rules for domain `{domain_id}`", items)


@mcp.tool(title="Get OpenAI Ads pacing rule", annotations=READ_ONLY)
def aeko_get_ad_rule(rule_id: str) -> str:
    """Get one non-deleted pacing rule by its AEKO rule UUID."""
    result, err = _safe(client.get, f"/api/marketing/rules/{rule_id}")
    if err:
        return f"# Failed to get ad rule\n\n```\n{err}\n```"
    return _json_block("Ad rule", result)


@mcp.tool(title="Create OpenAI Ads pacing rule", annotations=WRITE_ONCE)
def aeko_create_ad_rule(
    domain_id: str,
    name: str,
    scope_level: str,
    scope_filter: dict,
    match: str,
    conditions: list[dict],
    action: str,
    guards: dict,
    cooldown_minutes: int,
    max_actions_per_day: int,
    max_entities_per_run: int,
    description: Optional[str] = None,
) -> str:
    """Create a pacing rule draft. New rules are ALWAYS disabled; preview it, then explicitly enable.

    Call ``aeko_get_ad_rule_capabilities`` first instead of inventing combinations. ``scope_level`` is
    ``campaign | ad_group | ad``. ``scope_filter`` is ``{"target":"all","ids":[]}`` or
    ``{"target":"ids","ids":[<AEKO entity UUID>, ...]}`` (max 5000 IDs).

    ``conditions`` contains 1-5 condition objects, optionally with one nested group
    ``{"match":"all|any","conditions":[...]}`` at one level. A condition has ``metric`` (spend,
    impressions, clicks, cpm, cpc, ctr, pace_ratio, or budget_utilization), ``operator``
    (gt/gte/lt/lte), exactly one of ``threshold_micros`` or ``threshold_value``, and ``window``.
    Window kinds are last_n_hours (requires hours 1-24), this_completed_hour, today_so_far,
    rolling_24h, last_complete_day, rolling_days (requires days 2-30), or campaign_to_date. Money
    metrics spend/cpm/cpc use ``threshold_micros``; other metrics use ``threshold_value``.

    ``guards`` has min_impressions, min_clicks, min_spend_micros, min_elapsed_fraction (0-1), and
    min_hours_observed (1-24). ``action`` is pause, notify_only, decrease_budget, or decrease_bid;
    the shipped evaluator currently applies only pause (the latter two are capability-reserved).
    Cooldown is 15-10080 minutes; daily actions 1-200; entities per run 1-100, further tier-capped.
    """
    payload = _ad_rule_payload(
        domain_id=domain_id,
        name=name,
        description=description,
        scope_level=scope_level,
        scope_filter=scope_filter,
        match=match,
        conditions=conditions,
        action=action,
        guards=guards,
        cooldown_minutes=cooldown_minutes,
        max_actions_per_day=max_actions_per_day,
        max_entities_per_run=max_entities_per_run,
    )
    result, err = _safe(client.post, "/api/marketing/rules", json=payload)
    if err:
        return f"# Failed to create ad rule\n\n```\n{err}\n```"
    return _json_block("Ad rule created (disabled)", result)


@mcp.tool(title="Update OpenAI Ads pacing rule", annotations=WRITE)
def aeko_update_ad_rule(
    rule_id: str,
    name: Optional[str] = None,
    scope_level: Optional[str] = None,
    scope_filter: Optional[dict] = None,
    match: Optional[str] = None,
    conditions: Optional[list[dict]] = None,
    action: Optional[str] = None,
    guards: Optional[dict] = None,
    cooldown_minutes: Optional[int] = None,
    max_actions_per_day: Optional[int] = None,
    max_entities_per_run: Optional[int] = None,
    description: Optional[str] = None,
) -> str:
    """Patch the supplied fields on a saved pacing rule and increment its version.

    Omitted/``None`` arguments are left unchanged. The backend re-validates the fully merged
    definition, refreshes the account currency/timezone snapshot, and clears per-entity rule state.
    Pass an empty string to clear the optional description.
    """
    fields = {
        "name": name,
        "description": description,
        "scope_level": scope_level,
        "scope_filter": scope_filter,
        "match": match,
        "conditions": conditions,
        "guards": guards,
        "action": action,
        "cooldown_minutes": (
            int(cooldown_minutes) if cooldown_minutes is not None else None
        ),
        "max_actions_per_day": (
            int(max_actions_per_day) if max_actions_per_day is not None else None
        ),
        "max_entities_per_run": (
            int(max_entities_per_run) if max_entities_per_run is not None else None
        ),
    }
    payload = {key: value for key, value in fields.items() if value is not None}
    result, err = _safe(
        client.patch,
        f"/api/marketing/rules/{rule_id}",
        json=payload,
    )
    if err:
        return f"# Failed to update ad rule\n\n```\n{err}\n```"
    return _json_block("Ad rule updated", result)


@mcp.tool(title="Delete OpenAI Ads pacing rule", annotations=DESTRUCTIVE)
def aeko_delete_ad_rule(rule_id: str) -> str:
    """Soft-delete a pacing rule. The backend disables it and retains its audit history."""
    result, err = _safe(client.delete, f"/api/marketing/rules/{rule_id}")
    if err:
        return f"# Failed to delete ad rule\n\n```\n{err}\n```"
    return _json_block("Ad rule deleted (soft delete)", result)


@mcp.tool(title="Enable or disable OpenAI Ads pacing rule", annotations=DESTRUCTIVE)
def aeko_set_ad_rule_enabled(
    rule_id: str,
    enabled: bool,
    acknowledge_broad_match: bool = False,
) -> str:
    """Enable or disable a saved pacing rule.

    Enabling can pause live ad entities. Preview first. If the latest successful preview matched
    more than half its targets, the backend returns ``MARKETING_RULE_BROAD_MATCH_ACK_REQUIRED``;
    inspect the blast radius and re-call with ``acknowledge_broad_match=True`` only when intended.
    Disabling is immediate and ignores ``acknowledge_broad_match``.
    """
    if enabled:
        result, err = _safe(
            client.post,
            f"/api/marketing/rules/{rule_id}/enable",
            params={"acknowledge_broad_match": bool(acknowledge_broad_match)},
        )
    else:
        result, err = _safe(
            client.post,
            f"/api/marketing/rules/{rule_id}/disable",
        )
    if err:
        if "MARKETING_RULE_BROAD_MATCH_ACK_REQUIRED" in err:
            return (
                "# Broad-match acknowledgement required\n\n"
                "The latest preview matched more than half of the targeted entities. Review "
                "`target_count` and `matched_count`, then re-call "
                "`aeko_set_ad_rule_enabled` with `acknowledge_broad_match=True` only if this blast "
                f"radius is intended.\n\n```\n{err}\n```"
            )
        return f"# Failed to set ad rule enabled state\n\n```\n{err}\n```"
    return _json_block(f"Ad rule {'enabled' if enabled else 'disabled'}", result)


@mcp.tool(title="Get OpenAI Ads pacing rule capabilities", annotations=READ_ONLY)
def aeko_get_ad_rule_capabilities(domain_id: str) -> str:
    """Get the authoritative rule grammar for a domain before drafting a rule.

    Returns metrics, operators, windows, scopes, actions, the metric×window×scope compatibility
    matrix, account currency/timezone, the account-wide automation kill switch, tier, and tier caps.
    """
    result, err = _safe(
        client.get,
        "/api/marketing/rules/capabilities",
        params={"domain_id": domain_id},
    )
    if err:
        return f"# Failed to get ad rule capabilities\n\n```\n{err}\n```"
    return _json_block("Ad rule capabilities", result)


@mcp.tool(title="Validate OpenAI Ads pacing rule", annotations=WRITE)
def aeko_validate_ad_rule(
    domain_id: str,
    name: str,
    scope_level: str,
    scope_filter: dict,
    match: str,
    conditions: list[dict],
    action: str,
    guards: dict,
    cooldown_minutes: int,
    max_actions_per_day: int,
    max_entities_per_run: int,
    description: Optional[str] = None,
) -> str:
    """Validate and normalize an unsaved rule body without fetching Ads insights or saving a rule.

    The body grammar is identical to ``aeko_create_ad_rule``. A successful response contains
    ``valid=true``, the normalized definition, and warnings; invalid combinations return the
    backend's field-level validation error.
    """
    payload = _ad_rule_payload(
        domain_id=domain_id,
        name=name,
        description=description,
        scope_level=scope_level,
        scope_filter=scope_filter,
        match=match,
        conditions=conditions,
        action=action,
        guards=guards,
        cooldown_minutes=cooldown_minutes,
        max_actions_per_day=max_actions_per_day,
        max_entities_per_run=max_entities_per_run,
    )
    result, err = _safe(
        client.post,
        "/api/marketing/rules/validate",
        json=payload,
    )
    if err:
        return f"# Failed to validate ad rule\n\n```\n{err}\n```"
    return _json_block("Ad rule validation", result)


@mcp.tool(title="Preview OpenAI Ads pacing rule", annotations=WRITE)
def aeko_preview_ad_rule(
    rule_id: Optional[str] = None,
    rule: Optional[dict] = None,
) -> str:
    """Dry-run exactly one saved or unsaved pacing rule against completed Ads insights.

    Pass either ``rule_id`` for ``/rules/{id}/preview`` or a full create-shaped ``rule`` dict for
    ``/rules/preview``. The preview never changes ad state. It returns run_id, dry_run,
    data_through_hour, target_count, matched_count, matched_entities (remote ID, name, metrics), and
    warnings. Preview calls are hourly tier-capped and are retained in rule-run history.
    """
    if bool(rule_id) == bool(rule):
        return "# Pass exactly one of `rule_id` (saved rule) or `rule` (full unsaved rule body)."
    if rule_id:
        result, err = _safe(
            client.post,
            f"/api/marketing/rules/{rule_id}/preview",
        )
    else:
        result, err = _safe(
            client.post,
            "/api/marketing/rules/preview",
            json=rule,
        )
    if err:
        return f"# Failed to preview ad rule\n\n```\n{err}\n```"
    return _json_block("Ad rule preview (dry run)", result)


@mcp.tool(title="List OpenAI Ads rule executions", annotations=READ_ONLY)
def aeko_list_ad_rule_executions(
    domain_id: str,
    rule_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
) -> str:
    """List newest-first per-entity rule execution/audit records for a domain.

    Optionally filter by rule UUID and exact execution status. Records include action/status,
    skip_reason, matched metrics, condition snapshot, rule version, error details, and revert data.
    """
    params: dict[str, Any] = {
        "domain_id": domain_id,
        "limit": max(1, min(int(limit), 200)),
    }
    if rule_id:
        params["rule_id"] = rule_id
    if status:
        params["status"] = status
    result, err = _safe(
        client.get,
        "/api/marketing/rule-executions",
        params=params,
    )
    if err:
        return f"# Failed to list ad rule executions\n\n```\n{err}\n```"
    items = result if isinstance(result, list) else []
    return _json_block(f"{len(items)} ad rule executions", items)


@mcp.tool(title="List OpenAI Ads rule runs", annotations=READ_ONLY)
def aeko_list_ad_rule_runs(domain_id: str, limit: int = 20) -> str:
    """List newest-first rule evaluation runs for a domain.

    Each run reports trigger/dry-run/status, data-through hour, counts for evaluated/matched/actioned
    entities and all verdicts, insights usage, partial reason, and error details.
    """
    result, err = _safe(
        client.get,
        "/api/marketing/rule-runs",
        params={
            "domain_id": domain_id,
            "limit": max(1, min(int(limit), 200)),
        },
    )
    if err:
        return f"# Failed to list ad rule runs\n\n```\n{err}\n```"
    items = result if isinstance(result, list) else []
    return _json_block(f"{len(items)} ad rule runs", items)


@mcp.tool(title="Set OpenAI Ads automation kill switch", annotations=DESTRUCTIVE)
def aeko_set_ad_automation_enabled(domain_id: str, enabled: bool) -> str:
    """Set the connected ad account's global rules kill switch.

    ``enabled=False`` stops all scheduled rule evaluation/actions without changing individual rule
    enabled states. Re-enabling resumes evaluation of every individually enabled rule.

    Targets the narrow ``/ad-account/automation`` endpoint rather than ``PATCH /ad-account``:
    the latter also writes the SFTP password and conversions API token and stays dashboard-only,
    so calling it from here returned 401 and left agents unable to stop automation they had armed.
    """
    result, err = _safe(
        client.post,
        "/api/marketing/ad-account/automation",
        json={
            "domain_id": domain_id,
            "enabled": bool(enabled),
        },
    )
    if err:
        return f"# Failed to set ad automation enabled state\n\n```\n{err}\n```"
    return _json_block(
        f"Ad automation {'enabled' if enabled else 'disabled'}",
        result,
    )


# --- Writes: compose ad group, budget, pause --------------------------------------


@mcp.tool(title="Create ad group from context", annotations=WRITE_ONCE)
def aeko_create_ad_group_from_context(
    domain_id: str,
    ad_group_name: str,
    context_hints: list[str],
    ads: list[dict],
    idempotency_key: str,
    max_bid_micros: int = 1_000_000,
    campaign_id: Optional[str] = None,
    new_campaign_name: Optional[str] = None,
    new_campaign_budget_micros: Optional[int] = None,
    ad_account_id: Optional[str] = None,
    bidding_type: Optional[str] = None,
    conversion_event_setting_ids: Optional[list[str]] = None,
    targeting: Optional[dict] = None,
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
) -> str:
    """Create ONE ad group with a broader, agent-composed ``context_hints`` set and MULTIPLE product
    ads under it (created PAUSED for review). This is how a cluster of reviews across products becomes
    a single ad group — e.g. mask-pack + serum reviews sharing '민감성 피부' → hints
    ['민감성 피부에 좋은 제품'] with one ad per product.

    Placement: pass EITHER ``campaign_id`` (existing) OR both ``new_campaign_name`` +
    ``new_campaign_budget_micros`` (>= 1_000_000). New campaigns may set ``bidding_type`` to
    ``impressions`` (default), ``clicks``, or ``conversions``. A conversions campaign requires
    exactly one eligible event ID from ``aeko_list_conversion_event_settings``. ``targeting`` uses
    provider location IDs from ``aeko_lookup_ad_locations``; ``start_time`` and ``end_time`` are
    epoch seconds. These campaign fields are rejected with an existing ``campaign_id`` because a
    campaign's goal and conversion event are immutable.

    ``max_bid_micros`` is per billing event: 60,000 means $0.06 per impression ($60 CPM) for an
    impressions campaign, per click for a clicks campaign, and the target CPA bid for a conversions
    campaign (whose ad group is click-billed). ``ads`` = list of dicts (max 100 per ad group —
    OpenAI Ads cap; split a larger cluster into multiple ad groups), each:
    ``store_product_id`` (required), and optional ``source_review_id``, ``title``, ``body``,
    ``target_language`` (if title/body omitted, the backend composes clean creative from the review).
    ``idempotency_key`` MUST be stable for this logical action (reuse on retry).
    """
    if len(ads or []) > MAX_ADS_PER_AD_GROUP:
        return (
            f"# OpenAI Ads allows at most {MAX_ADS_PER_AD_GROUP} ads per ad group; split the "
            f"cluster into multiple ad groups (got {len(ads)})."
        )
    if len((ad_group_name or "").strip()) < MIN_NAME_LENGTH:
        return (
            f"# `ad_group_name` must be at least {MIN_NAME_LENGTH} characters "
            "(after trimming whitespace)."
        )
    if bool(campaign_id) == bool(new_campaign_name):
        return (
            "# Provide exactly one placement — either `campaign_id` (existing) OR "
            "`new_campaign_name` + `new_campaign_budget_micros` (new)."
        )
    if max_bid_micros < MIN_BID_MICROS or max_bid_micros > MAX_BID_MICROS:
        return (
            f"# Rejected — bid {max_bid_micros} must be between {MIN_BID_MICROS} and "
            f"{MAX_BID_MICROS} micros."
        )

    goal_fields_supplied = any(
        value is not None
        for value in (
            bidding_type,
            conversion_event_setting_ids,
            targeting,
            start_time,
            end_time,
        )
    )
    if campaign_id and goal_fields_supplied:
        return (
            "# `bidding_type`, `conversion_event_setting_ids`, `targeting`, `start_time`, and "
            "`end_time` apply only when creating a new campaign. Read the existing campaign's "
            "immutable goal instead."
        )

    if new_campaign_name:
        if len(new_campaign_name.strip()) < MIN_NAME_LENGTH:
            return (
                f"# `new_campaign_name` must be at least {MIN_NAME_LENGTH} characters "
                "(after trimming whitespace)."
            )
        if not new_campaign_budget_micros or new_campaign_budget_micros < MIN_BUDGET_MICROS:
            return f"# `new_campaign_budget_micros` is required and must be >= {MIN_BUDGET_MICROS}."
        normalized_goal = (bidding_type or "impressions").strip().lower()
        if normalized_goal not in CAMPAIGN_BILLING_EVENT:
            return "# `bidding_type` must be `impressions`, `clicks`, or `conversions`."
        event_ids = [item.strip() for item in (conversion_event_setting_ids or [])]
        if any(not item for item in event_ids):
            return "# `conversion_event_setting_ids` must not contain blank values."
        if normalized_goal == "conversions" and len(event_ids) != 1:
            return "# Conversions campaigns require exactly one `conversion_event_setting_ids` item."
        if normalized_goal != "conversions" and event_ids:
            return "# `conversion_event_setting_ids` are only valid for conversions campaigns."
        if start_time is not None and end_time is not None and int(end_time) <= int(start_time):
            return "# `end_time` must be later than `start_time`."
        new_campaign: dict[str, Any] = {
            "name": new_campaign_name,
            "budget": {"lifetime_spend_limit_micros": int(new_campaign_budget_micros)},
            "bidding_type": normalized_goal,
        }
        if conversion_event_setting_ids is not None:
            new_campaign["conversion_event_setting_ids"] = event_ids
        if targeting is not None:
            new_campaign["targeting"] = targeting
        if start_time is not None:
            new_campaign["start_time"] = int(start_time)
        if end_time is not None:
            new_campaign["end_time"] = int(end_time)
        placement = {"new_campaign": new_campaign}
    else:
        placement = {"campaign_id": campaign_id}
        campaign, err = _safe(client.get, f"/api/marketing/campaigns/{campaign_id}")
        if err:
            return f"# Failed to read existing campaign goal\n\n```\n{err}\n```"
        if not isinstance(campaign, dict):
            return "# Failed to read existing campaign goal — AEKO returned malformed campaign data."
        normalized_goal = str(campaign.get("bidding_type") or "").strip().lower()
        if normalized_goal not in CAMPAIGN_BILLING_EVENT:
            return (
                "# Failed to read existing campaign goal — AEKO did not return a supported "
                "`bidding_type`."
            )

    payload = {
        "domain_id": domain_id,
        "placement": placement,
        "ad_group": {
            "new": {
                "name": ad_group_name,
                "bidding_config": {
                    "billing_event_type": CAMPAIGN_BILLING_EVENT[normalized_goal],
                    "max_bid_micros": int(max_bid_micros),
                },
                "context_hints": [h for h in (context_hints or []) if h and h.strip()] or None,
            }
        },
        "ads": ads,
    }
    if ad_account_id:
        payload["ad_account_id"] = ad_account_id
    result, err = _safe(
        client.post,
        "/api/marketing/ad-groups/from-context",
        json=payload,
        headers=_idem_headers(idempotency_key),
    )
    if err:
        return f"# Failed to create ad group\n\n```\n{err}\n```"
    return _json_block("Ad group created (paused)", result)


@mcp.tool(title="Update campaign budget", annotations=WRITE)
def aeko_update_campaign_budget(
    campaign_id: str,
    lifetime_spend_limit_micros: int,
    idempotency_key: str,
    dry_run: bool = True,
    current_budget_micros: Optional[int] = None,
    max_budget_micros: Optional[int] = None,
    max_delta_pct: float = 25.0,
) -> str:
    """Set a campaign's lifetime budget (the lowest budget lever — ad groups only carry bidding).
    Spend is real, so guardrails are enforced HERE, not just in skill prose:

      - defaults to ``dry_run=True`` — returns a before→after preview and writes NOTHING;
      - rejects budgets below the backend floor (1_000_000 micros);
      - rejects budgets above ``max_budget_micros`` (absolute ceiling) if provided — does NOT clamp;
      - rejects a change larger than ``max_delta_pct`` vs ``current_budget_micros`` if provided.

    Pass ``current_budget_micros`` (from ``aeko_list_campaigns``) so the delta guard is active. Only
    a call with ``dry_run=false`` that passes all guards writes to OpenAI Ads.
    """
    new = int(lifetime_spend_limit_micros)
    if new < MIN_BUDGET_MICROS:
        return f"# Rejected — budget {new} is below the minimum {MIN_BUDGET_MICROS} micros."
    # HARD guard: a real write must carry both caps, else the delta + ceiling checks below are
    # skippable and only the backend's tiny floor applies. Dry-run has no such requirement.
    if not dry_run and (current_budget_micros is None or max_budget_micros is None):
        return (
            "# Rejected — a real write (dry_run=false) requires BOTH `current_budget_micros` (for the "
            "delta guard) AND `max_budget_micros` (the ceiling). Dry-run first, then re-call with both."
        )
    if max_budget_micros is not None and new > int(max_budget_micros):
        return (
            f"# Rejected — budget {new} exceeds the ceiling {int(max_budget_micros)} micros. "
            "Raise `max_budget_micros` deliberately if this is intended."
        )
    delta_note = ""
    if current_budget_micros is not None and int(current_budget_micros) > 0:
        current = int(current_budget_micros)
        delta_pct = abs(new - current) / current * 100.0
        delta_note = f"{'+' if new >= current else '-'}{abs(new - current)} micros ({delta_pct:.1f}%)"
        if delta_pct > float(max_delta_pct):
            return (
                f"# Rejected — change {delta_note} exceeds max_delta_pct {max_delta_pct}%. "
                "Split into smaller steps or raise the cap deliberately."
            )
    if dry_run:
        return _json_block(
            "DRY RUN — no write performed",
            {
                "campaign_id": campaign_id,
                "current_budget_micros": current_budget_micros,
                "proposed_budget_micros": new,
                "delta": delta_note or "n/a (pass current_budget_micros to compute)",
                "note": "Re-call with dry_run=false to apply.",
            },
        )
    result, err = _safe(
        client.post,
        f"/api/marketing/campaigns/{campaign_id}",
        json={"budget": {"lifetime_spend_limit_micros": new}},
        headers=_idem_headers(idempotency_key),
    )
    if err:
        return f"# Failed to update budget\n\n```\n{err}\n```"
    return _json_block(f"Budget updated (Δ {delta_note or 'n/a'})", result)


@mcp.tool(title="Update ad group", annotations=WRITE)
def aeko_update_ad_group(
    ad_group_id: str,
    idempotency_key: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    context_hints: Optional[list[str]] = None,
    max_bid_micros: Optional[int] = None,
    dry_run: bool = True,
    current_max_bid_micros: Optional[int] = None,
    max_bid_ceiling_micros: Optional[int] = None,
    max_delta_pct: float = 25.0,
) -> str:
    """Update ad-group copy, Context hints, or the maximum bid while preserving its billing event.

    Bid is spend, so the same tool-level safety pattern as campaign budgets is
    enforced: the call defaults to ``dry_run=True``; a real bid write requires
    both ``current_max_bid_micros`` and ``max_bid_ceiling_micros``; values above
    the ceiling or beyond ``max_delta_pct`` are rejected, never clamped.
    Non-bid-only edits skip those bid guards but still honor ``dry_run``.

    Status and product-set changes are deliberately excluded. Use
    ``aeko_set_ad_group_state`` for pause/resume/archive so its confirmation
    gates cannot be bypassed. Read the current bidding value from
    ``aeko_list_ad_groups`` before changing it. The tool also fetches the exact ad group before a
    bid preview or write and reuses its ``impression`` or ``click`` billing event. Bid micros are per
    impression for CPM (60,000 = $0.06 per impression = $60 CPM), per click for clicks campaigns,
    and the target CPA bid for conversions campaigns. Pro+ is enforced server-side.
    """
    payload: dict[str, Any] = {}
    if name is not None:
        normalized_name = name.strip()
        if len(normalized_name) < MIN_NAME_LENGTH:
            return f"# `name` must be at least {MIN_NAME_LENGTH} characters (after trimming whitespace)."
        if len(normalized_name) > 1000:
            return "# `name` must be at most 1000 characters."
        payload["name"] = normalized_name
    if description is not None:
        if len(description) > 5000:
            return "# `description` must be at most 5000 characters."
        payload["description"] = description
    if context_hints is not None:
        payload["context_hints"] = context_hints

    delta_note = ""
    if max_bid_micros is not None:
        new_bid = int(max_bid_micros)
        if new_bid < MIN_BID_MICROS or new_bid > MAX_BID_MICROS:
            return (
                f"# Rejected — bid {new_bid} must be between {MIN_BID_MICROS} and "
                f"{MAX_BID_MICROS} micros."
            )
        if not dry_run and (
            current_max_bid_micros is None or max_bid_ceiling_micros is None
        ):
            return (
                "# Rejected — a real bid write (dry_run=false) requires BOTH "
                "`current_max_bid_micros` (for the delta guard) AND "
                "`max_bid_ceiling_micros` (the ceiling). Dry-run first, then "
                "re-call with both."
            )
        if (
            max_bid_ceiling_micros is not None
            and new_bid > int(max_bid_ceiling_micros)
        ):
            return (
                f"# Rejected — bid {new_bid} exceeds the ceiling "
                f"{int(max_bid_ceiling_micros)} micros. Raise "
                "`max_bid_ceiling_micros` deliberately if this is intended."
            )
        if current_max_bid_micros is not None and int(current_max_bid_micros) > 0:
            current_bid = int(current_max_bid_micros)
            delta_pct = abs(new_bid - current_bid) / current_bid * 100.0
            delta_note = (
                f"{'+' if new_bid >= current_bid else '-'}{abs(new_bid - current_bid)} "
                f"micros ({delta_pct:.1f}%)"
            )
            if delta_pct > float(max_delta_pct):
                return (
                    f"# Rejected — bid change {delta_note} exceeds max_delta_pct "
                    f"{max_delta_pct}%. Split into smaller steps or raise the cap deliberately."
                )
        current_group, err = _safe(
            client.get, f"/api/marketing/ad-groups/{ad_group_id}"
        )
        if err:
            return f"# Failed to read current ad-group billing\n\n```\n{err}\n```"
        bidding = current_group.get("bidding") if isinstance(current_group, dict) else None
        billing_event_type = (
            bidding.get("billing_event_type") if isinstance(bidding, dict) else None
        )
        if billing_event_type not in {"impression", "click"}:
            return (
                "# Failed to read current ad-group billing — AEKO did not return a supported "
                "`billing_event_type`."
            )
        payload["bidding_config"] = {
            "billing_event_type": billing_event_type,
            "max_bid_micros": new_bid,
        }

    if not payload:
        return "# Provide at least one ad-group field to update."
    if dry_run:
        return _json_block(
            "DRY RUN — no write performed",
            {
                "ad_group_id": ad_group_id,
                "proposed_changes": payload,
                "current_max_bid_micros": current_max_bid_micros,
                "max_bid_ceiling_micros": max_bid_ceiling_micros,
                "bid_delta": delta_note or "n/a",
                "note": "Re-call with dry_run=false to apply.",
            },
        )

    result, err = _safe(
        client.post,
        f"/api/marketing/ad-groups/{ad_group_id}",
        json=payload,
        headers=_idem_headers(idempotency_key),
    )
    if err:
        return f"# Failed to update ad group\n\n```\n{err}\n```"
    return _json_block(
        f"Ad group updated (bid Δ {delta_note or 'n/a'})"
        if max_bid_micros is not None
        else "Ad group updated",
        result,
    )


@mcp.tool(title="Update ad creative", annotations=WRITE)
def aeko_update_ad_creative(
    ad_id: str,
    idempotency_key: str,
    name: Optional[str] = None,
    creative_type: Optional[str] = None,
    title: Optional[str] = None,
    body: Optional[str] = None,
    price: Optional[str] = None,
    target_url: Optional[str] = None,
    image_url: Optional[str] = None,
    file_id: Optional[str] = None,
) -> str:
    """Update an ad name and/or replace its complete creative object.

    The creative is a whole-object replacement, not a merge. Read the current
    creative from ``aeko_list_ads`` first and resend every field you want to
    keep. Supplying any creative field requires ``creative_type``, ``title``,
    and ``body``; ``chat_card`` additionally requires ``target_url`` and either
    ``file_id`` or ``image_url``, and forbids ``price``.

    Status is deliberately excluded. Use ``aeko_set_ad_state`` for
    pause/resume/archive so its confirmation gates cannot be bypassed.
    Pro+ is enforced server-side.
    """
    payload: dict[str, Any] = {}
    if name is not None:
        normalized_name = name.strip()
        if len(normalized_name) < MIN_NAME_LENGTH:
            return f"# `name` must be at least {MIN_NAME_LENGTH} characters (after trimming whitespace)."
        if len(normalized_name) > 1000:
            return "# `name` must be at most 1000 characters."
        payload["name"] = normalized_name

    creative_requested = any(
        value is not None
        for value in (
            creative_type,
            title,
            body,
            price,
            target_url,
            image_url,
            file_id,
        )
    )
    if creative_requested:
        missing = [
            field
            for field, value in (
                ("creative_type", creative_type),
                ("title", title),
                ("body", body),
            )
            if value is None or not str(value).strip()
        ]
        if missing:
            return (
                "# Creative replacement requires `creative_type`, `title`, and `body`; "
                f"missing: {', '.join(missing)}. Read `aeko_list_ads` first and resend "
                "every field you want to keep."
            )
        if creative_type not in {"chat_card", "product_ad_template"}:
            return "# `creative_type` must be `chat_card` or `product_ad_template`."

        normalized_title = str(title).strip()
        normalized_body = str(body).strip()
        if not 3 <= len(normalized_title) <= 50:
            return "# Creative `title` must be between 3 and 50 characters."
        if len(normalized_body) > 100:
            return "# Creative `body` must be at most 100 characters."
        for field_name, value, max_length in (
            ("price", price, 100),
            ("target_url", target_url, 2048),
            ("image_url", image_url, 2048),
            ("file_id", file_id, 255),
        ):
            if value is not None and len(value) > max_length:
                return f"# `{field_name}` must be at most {max_length} characters."
        for field_name, value in (("target_url", target_url), ("image_url", image_url)):
            if value is not None and value.strip() and not value.strip().startswith(
                ("https://", "http://")
            ):
                return f"# `{field_name}` must be an http(s) URL."

        if creative_type == "chat_card":
            if price is not None:
                return "# `chat_card` creative must not include `price`."
            if target_url is None or not target_url.strip():
                return "# `chat_card` creative requires `target_url`."
            has_file = file_id is not None and bool(file_id.strip())
            has_image = image_url is not None and bool(image_url.strip())
            if not has_file and not has_image:
                return "# `chat_card` creative requires `file_id` or `image_url`."

        creative: dict[str, Any] = {
            "type": creative_type,
            "title": normalized_title,
            "body": normalized_body,
        }
        for field_name, value in (
            ("price", price),
            ("target_url", target_url),
            ("image_url", image_url),
            ("file_id", file_id),
        ):
            if value is not None:
                creative[field_name] = value.strip()
        payload["creative"] = creative

    if not payload:
        return "# Provide `name` or a complete creative object to update."

    result, err = _safe(
        client.post,
        f"/api/marketing/ads/{ad_id}",
        json=payload,
        headers=_idem_headers(idempotency_key),
    )
    if err:
        return f"# Failed to update ad creative\n\n```\n{err}\n```"
    return _json_block("Ad creative updated", result)


_STATE_ENDPOINTS = {
    "pause": ("pause", "pause"),
    "paused": ("pause", "pause"),
    "active": ("activate", "active"),
    "activate": ("activate", "active"),
    "archive": ("archive", "archive"),
    "archived": ("archive", "archive"),
}


def _set_marketing_state(
    *,
    entity_label: str,
    path_prefix: str,
    entity_id: str,
    action: str,
    idempotency_key: str,
    confirm_active: bool,
    confirm_archive: bool,
) -> str:
    normalized = (action or "").strip().lower()
    if normalized not in _STATE_ENDPOINTS:
        return "# Allowed actions: `pause`, `active`, or `archive`."
    endpoint_action, result_label = _STATE_ENDPOINTS[normalized]
    if endpoint_action == "activate" and not confirm_active:
        return "# Resume requires `confirm_active=True` because it can restart ad spend."
    if endpoint_action == "archive" and not confirm_archive:
        return "# Archive requires `confirm_archive=True` because it is harder to undo than pause."
    result, err = _safe(
        client.post,
        f"/api/marketing/{path_prefix}/{entity_id}/{endpoint_action}",
        headers=_idem_headers(idempotency_key),
    )
    if err:
        return f"# Failed to set {entity_label.lower()} state\n\n```\n{err}\n```"
    return _json_block(f"{entity_label} {result_label}", result)


@mcp.tool(title="Set campaign state", annotations=DESTRUCTIVE)
def aeko_set_campaign_state(
    campaign_id: str,
    action: str,
    idempotency_key: str,
    confirm_active: bool = False,
    confirm_archive: bool = False,
) -> str:
    """Pause, resume (`active`), or archive a campaign.

    Resume requires `confirm_active=True` because it can restart spend.
    Archive requires `confirm_archive=True`; use `pause` for reversible
    budget hygiene unless the user explicitly wants archival.
    """
    return _set_marketing_state(
        entity_label="Campaign",
        path_prefix="campaigns",
        entity_id=campaign_id,
        action=action,
        idempotency_key=idempotency_key,
        confirm_active=confirm_active,
        confirm_archive=confirm_archive,
    )


@mcp.tool(title="Set ad group state", annotations=DESTRUCTIVE)
def aeko_set_ad_group_state(
    ad_group_id: str,
    action: str,
    idempotency_key: str,
    confirm_active: bool = False,
    confirm_archive: bool = False,
) -> str:
    """Pause, confirm-gated resume (`active`), or archive an ad group."""
    return _set_marketing_state(
        entity_label="Ad group",
        path_prefix="ad-groups",
        entity_id=ad_group_id,
        action=action,
        idempotency_key=idempotency_key,
        confirm_active=confirm_active,
        confirm_archive=confirm_archive,
    )


@mcp.tool(title="Set ad state", annotations=DESTRUCTIVE)
def aeko_set_ad_state(
    ad_id: str,
    action: str,
    idempotency_key: str,
    confirm_active: bool = False,
    confirm_archive: bool = False,
) -> str:
    """Pause, confirm-gated resume (`active`), or archive an ad."""
    return _set_marketing_state(
        entity_label="Ad",
        path_prefix="ads",
        entity_id=ad_id,
        action=action,
        idempotency_key=idempotency_key,
        confirm_active=confirm_active,
        confirm_archive=confirm_archive,
    )
