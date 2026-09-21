"""Read-only OpenAI Ads reporting reads: account selection, product pages, stored conversions.

Kept apart from ``marketing`` so reporting stays additive. Each tool is exactly one GET to a
dual-auth ``/api/marketing/*`` route — no auto-pagination, retries, refreshes, dispatches or
writes. Backend payloads are returned verbatim so ``null`` (not reported) never becomes ``0`` and
page, coverage, freshness and attribution metadata reach the skill intact.

Product and conversion reads require an explicit ``ad_account_id``: the backend would otherwise
pick a default account, which a multi-account report must never do silently.
"""
import datetime
import json
import re
import uuid
from typing import Any, Optional

from ..client import legacy_error_name
from ..server import client, mcp
from ._annotations import READ_ONLY

# Mirrors GET /api/marketing/product-insights (routes/marketing.py, product_insights.py).
PRODUCT_SCOPES = ("account", "campaign")
PRODUCT_INSIGHTS_DEFAULT_LIMIT = 25
PRODUCT_INSIGHTS_MAX_LIMIT = 50
PRODUCT_INSIGHTS_MAX_DAYS = 93
PRODUCT_INSIGHTS_MAX_CURSOR_LENGTH = 512
# Mirrors GET /api/marketing/conversion-insights (conversion_reporting.MAX_REPORT_RANGE_DAYS).
CONVERSION_INSIGHTS_MAX_DAYS = 92
# Account fields needed to choose and label an account. SFTP, pixel and credential
# configuration stay out of reporting output even though the backend never returns secrets.
AD_ACCOUNT_FIELDS = (
    "id",
    "domain_id",
    "connected",
    "status",
    "openai_ad_account_id",
    "account_name",
    "currency_code",
    "timezone",
    "openai_product_feed_id",
    "connected_at",
    "verified_at",
    "disconnected_at",
    "last_sync_attempted_at",
    "last_sync_succeeded_at",
    "last_sync_status",
    "last_sync_error_code",
)

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _safe(method, *args, **kwargs) -> tuple[Any, Optional[str]]:
    try:
        return method(*args, **kwargs), None
    except Exception as e:  # noqa: BLE001
        return None, f"{legacy_error_name(e)}: {e}"


def _json_block(title: str, payload: Any, notes: list[str] | None = None) -> str:
    bullets = "".join(f"- {note}\n" for note in notes or [])
    if bullets:
        bullets += "\n"
    block = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    return f"# {title}\n\n{bullets}```json\n{block}\n```"


def _invalid(title: str, message: str) -> str:
    return f"# {title}\n\n{message}\n\nNo request was sent."


def _uuid_error(name: str, value: Any) -> Optional[str]:
    if not isinstance(value, str) or not value.strip():
        return f"`{name}` is required: pass the local AEKO UUID."
    try:
        uuid.UUID(value.strip())
    except ValueError:
        return f"`{name}` must be a local AEKO UUID, got `{value}`."
    return None


def _window_error(date_from: Any, date_to: Any, max_days: int) -> Optional[str]:
    parsed: dict[str, datetime.date] = {}
    for name, value in (("date_from", date_from), ("date_to", date_to)):
        if not isinstance(value, str) or not _ISO_DATE.match(value):
            return f"`{name}` must be an ISO date (YYYY-MM-DD), got `{value}`."
        try:
            parsed[name] = datetime.date.fromisoformat(value)
        except ValueError:
            return f"`{name}` is not a real calendar date: `{value}`."
    days = (parsed["date_to"] - parsed["date_from"]).days + 1
    if days < 1:
        return "`date_to` must be on or after `date_from`."
    if days > max_days:
        return f"The window covers {days} inclusive days; this report allows at most {max_days}."
    return None


@mcp.tool(title="List OpenAI Ads accounts", annotations=READ_ONLY)
def aeko_list_ad_accounts(domain_id: str) -> str:
    """List every OpenAI Ads account recorded for an owned domain, so a report can pin one
    ``ad_account_id`` explicitly. Each account carries ``id`` (use as ``ad_account_id``), status,
    ``connected``, provider account/feed IDs, name, ``currency_code``, ``timezone`` and latest feed
    sync status. Credential and SFTP/pixel configuration are not returned.

    Auto-select only when exactly one account is connected; with several, the user or the scheduled
    job must name the account. Read-only: never connects, creates or changes an account."""
    title = "Failed to list ad accounts"
    problem = _uuid_error("domain_id", domain_id)
    if problem:
        return _invalid(title, problem)
    result, err = _safe(client.get, "/api/marketing/ad-accounts", params={"domain_id": domain_id})
    if err:
        return f"# {title}\n\n```\n{err}\n```"
    items = result if isinstance(result, list) else []
    accounts = [
        {field: item.get(field) for field in AD_ACCOUNT_FIELDS}
        for item in items
        if isinstance(item, dict)
    ]
    connected = sum(1 for account in accounts if account.get("connected") is True)
    return _json_block(
        f"{len(accounts)} ad accounts for domain `{domain_id}` ({connected} connected)",
        {
            "domain_id": domain_id,
            "count": len(accounts),
            "connected_count": connected,
            "accounts": accounts,
        },
    )


@mcp.tool(title="Get OpenAI Ads product insights page", annotations=READ_ONLY)
def aeko_get_product_insights(
    domain_id: str,
    ad_account_id: str,
    date_from: str,
    date_to: str,
    scope: str = "account",
    scope_id: Optional[str] = None,
    limit: int = PRODUCT_INSIGHTS_DEFAULT_LIMIT,
    after: Optional[str] = None,
) -> str:
    """Read ONE live page of OpenAI Ads product rows for one explicit ad account, sorted by product
    ad impressions over the whole window (``sort=product_impressions_desc``).

    - ``domain_id`` and ``ad_account_id`` are required local AEKO UUIDs; no default account is used.
    - ``scope`` = account | campaign. ``campaign`` requires ``scope_id`` (a local campaign UUID that
      belongs to the account); ``account`` takes no ``scope_id``.
    - ``date_from``/``date_to`` are completed account-local ISO dates (<= 93 inclusive days). The
      backend refuses dates after the account's latest completed day and a missing account timezone.
    - ``limit`` 1..50 (default 25). ``after`` is the opaque ``page.next_cursor`` of a previous page.

    Returns the backend payload verbatim: account currency/timezone, provider scope ID, ``page``
    (``has_more``, ``next_cursor``, ``paging_blocked``, ``blocked_reason``), ``carousel`` status, and
    rows with feed/item ``identity``, ``key``, nullable ``impressions``/``clicks``/``spend_micros``
    and separate ``carousel_card_impressions``/``carousel_card_clicks``. ``null`` means not reported,
    never zero. Carousel card counts are not billable impressions/clicks and must not be added to
    them. A page is a subset, not a complete account ranking. This tool never follows cursors itself."""
    title = "Failed to get product insights"
    problem = _uuid_error("domain_id", domain_id) or _uuid_error("ad_account_id", ad_account_id)
    if not problem and scope not in PRODUCT_SCOPES:
        problem = f"`scope` must be one of {', '.join(PRODUCT_SCOPES)}, got `{scope}`."
    if not problem and scope == "campaign":
        problem = _uuid_error("scope_id", scope_id)
    if not problem and scope == "account" and scope_id is not None:
        problem = "`scope_id` applies only to `scope=\"campaign\"`; omit it for the account scope."
    if not problem and (
        isinstance(limit, bool)
        or not isinstance(limit, int)
        or not 1 <= limit <= PRODUCT_INSIGHTS_MAX_LIMIT
    ):
        problem = f"`limit` must be an integer from 1 to {PRODUCT_INSIGHTS_MAX_LIMIT}, got `{limit}`."
    if not problem and after is not None and (
        not isinstance(after, str) or not after.strip() or len(after) > PRODUCT_INSIGHTS_MAX_CURSOR_LENGTH
    ):
        problem = (
            "`after` must be the non-empty `page.next_cursor` from a previous page "
            f"(at most {PRODUCT_INSIGHTS_MAX_CURSOR_LENGTH} characters)."
        )
    if not problem:
        problem = _window_error(date_from, date_to, PRODUCT_INSIGHTS_MAX_DAYS)
    if problem:
        return _invalid(title, problem)

    params: dict[str, Any] = {
        "domain_id": domain_id,
        "ad_account_id": ad_account_id,
        "scope": scope,
        "date_from": date_from,
        "date_to": date_to,
        "limit": limit,
    }
    if scope_id is not None:
        params["scope_id"] = scope_id
    if after is not None:
        params["after"] = after
    result, err = _safe(client.get, "/api/marketing/product-insights", params=params)
    if err:
        return f"# {title}\n\n```\n{err}\n```"

    payload = result if isinstance(result, dict) else {}
    page = payload.get("page") if isinstance(payload.get("page"), dict) else {}
    carousel = payload.get("carousel") if isinstance(payload.get("carousel"), dict) else {}
    rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
    notes = [
        f"One page of {len(rows)} product rows ranked by product impressions; a subset, not a complete "
        "account ranking. Null metrics are unreported, not zero."
    ]
    if page.get("paging_blocked"):
        notes.append(
            f"Paging blocked (`{page.get('blocked_reason')}`): whether more rows exist is unknown."
        )
    elif page.get("has_more"):
        notes.append("More rows exist: pass `page.next_cursor` as `after` only within the caller's page budget.")
    elif page.get("has_more") is False:
        notes.append("The provider reported no further rows for this scope and window.")
    notes.append(
        f"Carousel card metrics: `{carousel.get('status')}`. Card counts are separate and never billable "
        "impressions or clicks."
    )
    return _json_block(
        f"Product insights ({scope}, {date_from} → {date_to}, account `{ad_account_id}`)", result, notes
    )


@mcp.tool(title="Get stored OpenAI Ads conversion insights", annotations=READ_ONLY)
def aeko_get_conversion_insights(
    domain_id: str,
    ad_account_id: str,
    date_from: str,
    date_to: str,
) -> str:
    """Read the STORED campaign-level conversion report for one explicit ad account. Reads facts
    AEKO already collected; never calls OpenAI Ads and never queues a refresh.

    - ``domain_id`` and ``ad_account_id`` are required local AEKO UUIDs; no default account is used.
    - ``date_from``/``date_to`` are account-local ISO dates, at most 92 inclusive days. Dates after
      the latest completed account-local day come back as ``pending``.

    Returns the backend payload verbatim: ``state`` (complete | partial | stale | not_synced),
    ``state_reasons``, ``blocked_reason``, freshness threshold, restatement days, refresh times,
    ``coverage`` day counts, ``latest_attempt``/``latest_success`` collection runs, ``attribution`` and
    per-campaign ``coverage``, nullable metric totals with ``reported_days``, and per-day ``status``
    (reported | omitted | not_confirmed | not_synced | pending).

    Click-through and view-through conversions are separate. The conversion event and click-through
    window are unknown (``null``); the view-through window is 1 day. Totals sum reported days only, so
    never derive CPA, ROAS or a complete conversion total from a partial, stale or unsynced report."""
    title = "Failed to get conversion insights"
    problem = (
        _uuid_error("domain_id", domain_id)
        or _uuid_error("ad_account_id", ad_account_id)
        or _window_error(date_from, date_to, CONVERSION_INSIGHTS_MAX_DAYS)
    )
    if problem:
        return _invalid(title, problem)

    params = {
        "domain_id": domain_id,
        "ad_account_id": ad_account_id,
        "scope": "campaign",
        "date_from": date_from,
        "date_to": date_to,
    }
    result, err = _safe(client.get, "/api/marketing/conversion-insights", params=params)
    if err:
        return f"# {title}\n\n```\n{err}\n```"

    payload = result if isinstance(result, dict) else {}
    reasons = payload.get("state_reasons") or []
    notes = [
        f"Stored report state: `{payload.get('state')}`"
        + (f" ({', '.join(str(reason) for reason in reasons)})" if reasons else "")
        + (f"; blocked: `{payload.get('blocked_reason')}`" if payload.get("blocked_reason") else "")
        + ". No refresh was requested.",
        "Click-through and view-through conversions are separate; event and click window are unknown, "
        "view window is 1 day. Null counts are unreported, not zero; no CPA/ROAS is derivable here.",
    ]
    return _json_block(
        f"Stored conversion insights (campaign, {date_from} → {date_to}, account `{ad_account_id}`)",
        result,
        notes,
    )
