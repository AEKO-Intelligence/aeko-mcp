"""MCP tools for agentic OpenAI-Ads ad ops — the thin layer under the aeko-plugin ad skills.

These wrap the AEKO backend's ``/api/marketing/*`` routes (and the domain-wide contextual-reviews +
manual-review-inject routes under ``/api/review-integrations/*``) so a plugin skill can:

  - pull contextual reviews across a whole domain and compose broader, cross-product ad groups
    (``aeko_list_contextual_reviews`` -> ``aeko_create_ad_group_from_context``),
  - inject real reviews it gathered for merchants without a review app (``aeko_inject_reviews``),
  - read ad performance and reallocate budget by performance (``aeko_get_ad_insights`` +
    ``aeko_update_campaign_budget``), and pause wasteful ads/campaigns (``aeko_set_ad_state`` /
    ``aeko_set_campaign_state``).

Design rules (mirror the skill/tool split):
  - Reasoning (clustering, ranking, deciding) lives in the SKILL; these tools stay thin (~1:1 to a
    backend route).
  - Tools that feed a later tool call return a machine-parseable JSON block (explicit IDs), not just
    prose, so a skill can chain list -> create.
  - Every OpenAI-Ads WRITE route requires an ``Idempotency-Key`` header; write tools take a stable,
    caller-supplied ``idempotency_key`` (the skill mints ONE per logical action, reused on retries)
    so a re-run never double-creates or double-charges.
  - Spend is real: ``aeko_update_campaign_budget`` defaults to dry-run and enforces an absolute
    ceiling + max per-call delta at the TOOL layer (the backend only enforces a floor).
  - v1 state changes are limited to ``pause`` (activate/archive deferred).

All routes are Pro+ gated server-side; an under-tier account surfaces the backend 403 verbatim.
"""
import json
from typing import Any, Optional

from ..server import client, mcp
from ._annotations import READ_ONLY, WRITE, WRITE_ONCE

# Backend enforces this floor on campaign budgets (schemas/marketing.py MarketingBudget).
MIN_BUDGET_MICROS = 1_000_000
# Backend caps one inject request at 200 reviews (schemas/review.py ReviewInjectRequest).
INJECT_REVIEWS_BATCH_SIZE = 200
# Backend caps ads per ad group at 100 (schemas/marketing.py MarketingAdGroupFromContextRequest).
MAX_ADS_PER_AD_GROUP = 100
# Backend requires >= 3 chars for new campaign / ad-group names (schemas/marketing.py).
MIN_NAME_LENGTH = 3


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
def aeko_list_campaigns(domain_id: str) -> str:
    """List a domain's OpenAI-Ads campaigns (id, name, status, budget). Use the returned
    ``id`` as ``campaign_id`` for ad-group listing, budget updates, or pausing."""
    result, err = _safe(client.get, "/api/marketing/campaigns", params={"domain_id": domain_id})
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
    result, err = _safe(client.get, "/api/marketing/insights", params=params)
    if err:
        return f"# Failed to get insights\n\n```\n{err}\n```"
    return _json_block(f"Insights ({scope}, {date_from} → {date_to})", result)


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
) -> str:
    """Create ONE ad group with a broader, agent-composed ``context_hints`` set and MULTIPLE product
    ads under it (created PAUSED for review). This is how a cluster of reviews across products becomes
    a single ad group — e.g. mask-pack + serum reviews sharing '민감성 피부' → hints
    ['민감성 피부에 좋은 제품'] with one ad per product.

    Placement: pass EITHER ``campaign_id`` (existing) OR both ``new_campaign_name`` +
    ``new_campaign_budget_micros`` (>= 1_000_000). ``ads`` = list of dicts (max 100 per ad group —
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
    if new_campaign_name:
        if len(new_campaign_name.strip()) < MIN_NAME_LENGTH:
            return (
                f"# `new_campaign_name` must be at least {MIN_NAME_LENGTH} characters "
                "(after trimming whitespace)."
            )
        if not new_campaign_budget_micros or new_campaign_budget_micros < MIN_BUDGET_MICROS:
            return f"# `new_campaign_budget_micros` is required and must be >= {MIN_BUDGET_MICROS}."
        placement = {
            "new_campaign": {
                "name": new_campaign_name,
                "budget": {"lifetime_spend_limit_micros": int(new_campaign_budget_micros)},
            }
        }
    else:
        placement = {"campaign_id": campaign_id}

    payload = {
        "domain_id": domain_id,
        "placement": placement,
        "ad_group": {
            "new": {
                "name": ad_group_name,
                "bidding_config": {
                    "billing_event_type": "impression",
                    "max_bid_micros": int(max_bid_micros),
                },
                "context_hints": [h for h in (context_hints or []) if h and h.strip()] or None,
            }
        },
        "ads": ads,
    }
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


@mcp.tool(title="Pause campaign", annotations=WRITE)
def aeko_set_campaign_state(campaign_id: str, action: str, idempotency_key: str) -> str:
    """Change a campaign's state. v1 supports ``action='pause'`` only (activate/archive deferred).
    Use to stop a whole under-performing campaign; reallocate its budget with
    ``aeko_update_campaign_budget`` instead of pausing when you only want to trim spend."""
    if action != "pause":
        return "# Only `action='pause'` is supported in v1 (activate/archive are deferred)."
    result, err = _safe(
        client.post,
        f"/api/marketing/campaigns/{campaign_id}/pause",
        headers=_idem_headers(idempotency_key),
    )
    if err:
        return f"# Failed to pause campaign\n\n```\n{err}\n```"
    return _json_block("Campaign paused", result)


@mcp.tool(title="Pause ad", annotations=WRITE)
def aeko_set_ad_state(ad_id: str, action: str, idempotency_key: str) -> str:
    """Change an ad's state. v1 supports ``action='pause'`` only. Use for budget hygiene — pause an
    ad that spends with ~0 clicks / runaway CPC (identify it via ``aeko_get_ad_insights`` scope='ad')."""
    if action != "pause":
        return "# Only `action='pause'` is supported in v1 (activate/archive are deferred)."
    result, err = _safe(
        client.post,
        f"/api/marketing/ads/{ad_id}/pause",
        headers=_idem_headers(idempotency_key),
    )
    if err:
        return f"# Failed to pause ad\n\n```\n{err}\n```"
    return _json_block("Ad paused", result)
