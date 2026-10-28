"""The 캠페인 page for agents: campaign -> product -> ad overview, stored numbers and 확인 필요.

Reads wrap ``/api/marketing/campaign-overview*``; ``aeko_answer_open_placement`` is the one
write. Numbers are the stored daily collection, never live provider data: a number the
backend does not report stays null here, never 0.
"""

from typing import Any, Optional

import httpx
from pydantic import BaseModel, ConfigDict

from ..client import AekoAPIError
from ..server import client, mcp
from ._annotations import DESTRUCTIVE_EXTERNAL, READ_ONLY, tool_spec
from ._paging import MAX_PAGE_CHARS
from ._structured import (
    AekoToolError,
    AekoToolInputError,
    api_error,
    read_boundary,
    text_bytes,
    uuid_arg,
)

BASE = "/api/marketing/campaign-overview"
MAX_REJECTED_SHOWN = 20
MAX_TEXT = 300
MAX_REJECTED_TEXT = 120
# (ads per product, products per campaign, campaigns, rejected ads) tried in order until the
# page fits. Korean text is about 3 UTF-8 bytes a character, so ads shrink one at a time first.
_LADDER = (
    (None, None, None, MAX_REJECTED_SHOWN), (3, None, None, MAX_REJECTED_SHOWN),
    (2, None, None, MAX_REJECTED_SHOWN), (1, None, None, MAX_REJECTED_SHOWN), (1, None, None, 5),
    (1, 5, None, 5), (0, None, None, 5), (0, 5, 10, 5), (0, 2, 3, 0), (0, 0, 1, 0), (0, 0, 0, 0),
)


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Numbers(_Model):
    """Stored delivery sums; a metric that has no number is null, never 0."""

    impressions: Optional[int] = None
    clicks: Optional[int] = None
    spend_micros: Optional[int] = None


class OverviewAd(_Model):
    id: str
    name: Optional[str] = None
    status: Optional[str] = None
    review_status: Optional[str] = None
    title: Optional[str] = None
    body: Optional[str] = None
    auto_added: bool = False
    numbers: Optional[Numbers] = None
    mention_rate: Optional[float] = None
    mention_responses: Optional[int] = None


class OverviewAdGroup(_Model):
    id: str
    name: Optional[str] = None
    status: Optional[str] = None


class OverviewProduct(_Model):
    store_product_id: Optional[str] = None
    title: Optional[str] = None
    ad_count: int = 0
    added_today: int = 0
    ad_groups: list[OverviewAdGroup]
    numbers: Optional[Numbers] = None
    ads: list[OverviewAd]
    ads_omitted: int = 0


class OverviewCampaign(_Model):
    id: str
    name: Optional[str] = None
    status: Optional[str] = None
    kind: Optional[str] = None
    display_state: Optional[str] = None
    bidding_type: Optional[str] = None
    countries: list[str]
    ad_group_count: int = 0
    ad_count: int = 0
    product_count: int = 0
    numbers: Optional[Numbers] = None
    products: list[OverviewProduct]
    products_omitted: int = 0


class RejectedAd(_Model):
    ad_id: str
    campaign_id: Optional[str] = None
    campaign_name: Optional[str] = None
    product_title: Optional[str] = None
    ad_name: Optional[str] = None
    reason: Optional[str] = None


class Attention(_Model):
    total: int
    rejected_total: int
    rejected_ads: list[RejectedAd]
    rejected_ads_omitted: int
    open_placements: int
    saved_drafts: int


class CampaignOverview(_Model):
    account: Optional[dict[str, Any]] = None
    capacity: Optional[dict[str, Any]] = None
    archived_campaigns: int
    numbers_note: str
    numbers_as_of: Optional[str] = None
    numbers_collecting: bool
    numbers_window: Optional[dict[str, Any]] = None
    account_numbers: Optional[Numbers] = None
    attention: Attention
    campaigns: list[OverviewCampaign]
    campaigns_omitted: int = 0
    output_limited: bool = False


class ProductAdsPage(_Model):
    ads: list[OverviewAd]
    total: int
    offset: int
    limit: int
    returned_count: int
    next_offset: Optional[int]
    has_more: bool
    output_limited: bool


class OpenPlacementOption(_Model):
    campaign_id: str
    ad_group_id: str
    label: Optional[str] = None
    score: Optional[int] = None


class OpenPlacement(_Model):
    ad_set_item_id: str
    store_product_id: Optional[str] = None
    product_title: Optional[str] = None
    title: Optional[str] = None
    body: Optional[str] = None
    created_at: Optional[str] = None
    why: Optional[str] = None
    options: list[OpenPlacementOption]


class OpenPlacements(_Model):
    items: list[OpenPlacement]
    total: int
    returned_count: int
    output_limited: bool


class PlacementAnswer(_Model):
    status: str
    ad_set_item_id: str
    campaign_id: Optional[str] = None
    ad_group_id: Optional[str] = None
    label: Optional[str] = None
    ad_id: Optional[str] = None


def _bad(message: str = "AEKO returned an unexpected response.") -> AekoToolError:
    return AekoToolError("INVALID_BACKEND_RESPONSE", message)


def _dict(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _bad()
    return value


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise _bad()
    return value


def _str(value: Any, limit: int = MAX_TEXT) -> Optional[str]:
    if value is None:
        return None
    return str(value)[:limit]


def _int(value: Any) -> Optional[int]:
    return value if type(value) is int else None


def _numbers(value: Any) -> Optional[Numbers]:
    """Backend totals -> Numbers; an absent entry stays None (no number), not zeros."""
    if not isinstance(value, dict):
        return None
    return Numbers(
        impressions=_int(value.get("impressions")),
        clicks=_int(value.get("clicks")),
        spend_micros=_int(value.get("spend_micros")),
    )


def _ad(raw: Any, numbers: dict[str, Any], mention: dict[str, Any]) -> OverviewAd:
    raw = _dict(raw)
    creative = raw.get("creative") if isinstance(raw.get("creative"), dict) else {}
    ad_id = str(raw.get("id") or "")
    rate = mention.get(ad_id) if isinstance(mention.get(ad_id), dict) else None
    rate_value = rate.get("rate") if rate else None
    return OverviewAd(
        id=ad_id,
        name=_str(raw.get("name")),
        status=_str(raw.get("status"), 40),
        review_status=_str(raw.get("review_status"), 40),
        title=_str(creative.get("title")),
        body=_str(creative.get("body")),
        auto_added=raw.get("auto_added") is True,
        numbers=_numbers(numbers.get(ad_id)),
        mention_rate=float(rate_value) if isinstance(rate_value, (int, float)) and not isinstance(rate_value, bool) else None,
        mention_responses=_int(rate.get("responses")) if rate else None,
    )


def _overview(
    data: dict[str, Any], numbers: dict[str, Any], attention: dict[str, Any], caps: tuple
) -> CampaignOverview:
    ad_cap, product_cap, campaign_cap, rejected_cap = caps
    campaign_numbers = _dict(numbers.get("campaigns") or {})
    product_numbers = _dict(numbers.get("products") or {})
    ad_numbers = _dict(numbers.get("ads") or {})
    mention = _dict(numbers.get("mention") or {})
    rows = _list(data.get("campaigns"))
    campaigns: list[OverviewCampaign] = []
    for raw_campaign in rows[:campaign_cap]:
        campaign = _dict(raw_campaign)
        campaign_id = str(campaign.get("id") or "")
        raw_products = _list(campaign.get("products"))
        products: list[OverviewProduct] = []
        for raw_product in raw_products[:product_cap]:
            product = _dict(raw_product)
            product_id = product.get("store_product_id")
            raw_ads = _list(product.get("ads"))
            shown = raw_ads[:ad_cap]
            products.append(OverviewProduct(
                store_product_id=_str(product_id),
                title=_str(product.get("title")),
                ad_count=_int(product.get("ad_count")) or 0,
                added_today=_int(product.get("added_today")) or 0,
                ad_groups=[
                    OverviewAdGroup(id=str(g.get("id") or ""), name=_str(g.get("name")), status=_str(g.get("status"), 40))
                    for g in map(_dict, _list(product.get("ad_groups")))
                ],
                numbers=_numbers(product_numbers.get(f"{campaign_id}:{product_id if product_id is not None else 'none'}")),
                ads=[_ad(ad, ad_numbers, mention) for ad in shown],
                ads_omitted=max((_int(product.get("ad_count")) or len(raw_ads)) - len(shown), 0),
            ))
        campaigns.append(OverviewCampaign(
            id=campaign_id,
            name=_str(campaign.get("name")),
            status=_str(campaign.get("status"), 40),
            kind=_str(campaign.get("kind"), 40),
            display_state=_str(campaign.get("display_state"), 40),
            bidding_type=_str(campaign.get("bidding_type"), 40),
            countries=[str(c)[:8] for c in _list(campaign.get("countries"))[:30]],
            ad_group_count=_int(campaign.get("ad_group_count")) or 0,
            ad_count=_int(campaign.get("ad_count")) or 0,
            product_count=_int(campaign.get("product_count")) or 0,
            numbers=_numbers(campaign_numbers.get(campaign_id)),
            products=products,
            products_omitted=max(len(raw_products) - len(products), 0),
        ))
    rejected = [_dict(item) for item in _list(attention.get("rejected_ads"))]
    shown_rejected = rejected[:rejected_cap]
    window = numbers.get("window")
    return CampaignOverview(
        account=data.get("account") if isinstance(data.get("account"), dict) else None,
        capacity=data.get("capacity") if isinstance(data.get("capacity"), dict) else None,
        archived_campaigns=_int(data.get("archived_campaigns")) or 0,
        numbers_note=(
            "Numbers are the stored daily collection (one collection per account per day), not live "
            "provider data. null means no number yet; it is not zero."
        ),
        numbers_as_of=_str(numbers.get("as_of"), 40),
        numbers_collecting=numbers.get("collecting") is True,
        numbers_window=window if isinstance(window, dict) else None,
        account_numbers=_numbers(numbers.get("account")),
        attention=Attention(
            total=_int(attention.get("total")) or 0,
            rejected_total=_int(attention.get("rejected_total")) or 0,
            rejected_ads=[
                RejectedAd(
                    ad_id=str(_dict(item.get("ad")).get("id") or ""),
                    campaign_id=_str(item.get("campaign_id")),
                    campaign_name=_str(item.get("campaign_name"), MAX_REJECTED_TEXT),
                    product_title=_str(item.get("product_title"), MAX_REJECTED_TEXT),
                    ad_name=_str(_dict(item.get("ad")).get("name"), MAX_REJECTED_TEXT),
                    reason=_str(item.get("reason"), MAX_REJECTED_TEXT),
                )
                for item in shown_rejected
            ],
            rejected_ads_omitted=max((_int(attention.get("rejected_total")) or len(rejected)) - len(shown_rejected), 0),
            open_placements=len(_list(attention.get("pending_placements"))),
            saved_drafts=_int(_dict(attention.get("saved_drafts") or {}).get("count")) or 0,
        ),
        campaigns=campaigns,
        campaigns_omitted=max(len(rows) - len(campaigns), 0),
    )


def _shown(result: CampaignOverview) -> tuple[int, int, int, int]:
    """Campaigns, products, ads and rejected ads a result lists, to tell whether it was trimmed."""
    products = [p for c in result.campaigns for p in c.products]
    return (
        len(result.campaigns), len(products), sum(len(p.ads) for p in products),
        len(result.attention.rejected_ads),
    )


def _account_params(domain_id: str, ad_account_id: Optional[str]) -> dict[str, Any]:
    params: dict[str, Any] = {"domain_id": uuid_arg(domain_id, "domain_id")}
    if ad_account_id is not None:
        params["ad_account_id"] = uuid_arg(ad_account_id, "ad_account_id")
    return params


def _int_range(value: Any, name: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise AekoToolInputError("INVALID_ARGUMENT", f"{name} must be an integer from {low} to {high}.")
    return value


@mcp.tool(**tool_spec("Get campaign overview", READ_ONLY, structured_output=True))
def aeko_get_campaign_overview(
    domain_id: str,
    ad_account_id: Optional[str] = None,
    days: int = 30,
    ads_per_product: int = 3,
) -> CampaignOverview:
    """Read the 캠페인 page: campaigns -> products -> newest ads, with numbers and 확인 필요. Read-only.

    Shows each campaign's state, products, ad groups and up to ads_per_product (1-20) ads per
    product, plus stored delivery numbers over the last days (1-90) and what needs attention
    (rejected ads, open placements, unplaced saved drafts). Numbers are the stored daily
    collection (one per account per day), not live provider data; null means no number yet, not
    zero. Large accounts are trimmed to fit (see *_omitted); use aeko_list_product_ads for more
    ads and aeko_list_open_placements for the open placements. ad_account_id defaults to the
    domain's connected account.
    """
    with read_boundary():
        params = _account_params(domain_id, ad_account_id)
        days = _int_range(days, "days", 1, 90)
        per_product = _int_range(ads_per_product, "ads_per_product", 1, 20)
        data = _dict(client.get(BASE, params={**params, "ads_per_product": per_product}))
        numbers = _dict(client.get(f"{BASE}/numbers", params={**params, "days": days}))
        attention = _dict(client.get(f"{BASE}/attention", params=params))
        full = _overview(data, numbers, attention, _LADDER[0])
        for caps in _LADDER:
            result = full if caps == _LADDER[0] else _overview(data, numbers, attention, caps)
            if text_bytes(result) <= MAX_PAGE_CHARS:
                result.output_limited = _shown(result) != _shown(full)
                return result
        raise AekoToolError("OUTPUT_TOO_LARGE", "The campaign overview is too large to return.")


@mcp.tool(**tool_spec("List a product's ads in a campaign", READ_ONLY, structured_output=True))
def aeko_list_product_ads(
    domain_id: str,
    campaign_id: str,
    store_product_id: str,
    offset: int = 0,
    limit: int = 20,
) -> ProductAdsPage:
    """Read one page of a product's live ads inside one campaign, newest first. Read-only.

    Continues where aeko_get_campaign_overview stopped (offset=ads already shown). Pass
    store_product_id "none" for the ads that carry no product. Pages hold up to limit (1-100) ads
    and may hold fewer when large; continue at next_offset while has_more is true. Ad text is
    shown as saved; no numbers here (the overview carries them).
    """
    with read_boundary():
        domain = uuid_arg(domain_id, "domain_id")
        campaign = uuid_arg(campaign_id, "campaign_id")
        if not isinstance(store_product_id, str) or not 1 <= len(store_product_id) <= 64 or not store_product_id.strip():
            raise AekoToolInputError("INVALID_ARGUMENT", "store_product_id must be a product ID or none.")
        if type(offset) is not int or not 0 <= offset <= 2**31 - 1:
            raise AekoToolInputError("INVALID_ARGUMENT", "offset must be a nonnegative integer.")
        limit = _int_range(limit, "limit", 1, 100)
        data = _dict(client.get(f"{BASE}/ads", params={
            "domain_id": domain, "campaign_id": campaign,
            "store_product_id": store_product_id, "offset": offset, "limit": limit,
        }))
        raw = _list(data.get("ads"))
        total = data.get("total")
        if type(total) is not int or total < 0 or len(raw) > limit:
            raise _bad("AEKO returned inconsistent ad pagination.")
        ads = [_ad(ad, {}, {}) for ad in raw]

        def page(count: int) -> ProductAdsPage:
            next_offset = offset + count if offset + count < total and count else None
            return ProductAdsPage(
                ads=ads[:count], total=total, offset=offset, limit=limit, returned_count=count,
                next_offset=next_offset, has_more=next_offset is not None, output_limited=count < len(ads),
            )

        count = len(ads)
        result = page(count)
        while count > 1 and text_bytes(result) > MAX_PAGE_CHARS:
            count -= 1
            result = page(count)
        return result


@mcp.tool(**tool_spec("List open placements", READ_ONLY, structured_output=True))
def aeko_list_open_placements(domain_id: str, ad_account_id: Optional[str] = None) -> OpenPlacements:
    """List ads that 컨텍스트 광고 자동 추가 left open for a person to place (확인 필요). Read-only.

    Each item has the saved ad's copy, the product, why it is open, and the ad groups it may go
    into (options with campaign_id, ad_group_id, label, score). Newest first, up to 200 on the
    backend; if more are open, the rest appear once earlier ones are answered (no offset). Use ad_set_item_id and an options ad_group_id with aeko_answer_open_placement. An
    item with no options left can only be skipped. ad_account_id defaults to the connected account.
    """
    with read_boundary():
        data = _dict(client.get(f"{BASE}/placements", params=_account_params(domain_id, ad_account_id)))
        raw = _list(data.get("items"))
        items = []
        for entry in map(_dict, raw):
            items.append(OpenPlacement(
                ad_set_item_id=str(entry.get("ad_set_item_id") or ""),
                store_product_id=_str(entry.get("store_product_id")),
                product_title=_str(entry.get("product_title")),
                title=_str(entry.get("title")),
                body=_str(entry.get("body")),
                created_at=_str(entry.get("created_at"), 40),
                why=_str(entry.get("why"), 500),
                options=[
                    OpenPlacementOption(
                        campaign_id=str(o.get("campaign_id") or ""), ad_group_id=str(o.get("ad_group_id") or ""),
                        label=_str(o.get("label")), score=_int(o.get("score")),
                    )
                    for o in map(_dict, _list(entry.get("options")))
                ],
            ))
        count = len(items)

        def page(n: int) -> OpenPlacements:
            return OpenPlacements(items=items[:n], total=len(items), returned_count=n, output_limited=n < len(items))

        result = page(count)
        while count > 1 and text_bytes(result) > MAX_PAGE_CHARS:
            count -= 1
            result = page(count)
        return result


@mcp.tool(**tool_spec("Answer an open placement", DESTRUCTIVE_EXTERNAL, structured_output=True))
def aeko_answer_open_placement(
    domain_id: str,
    ad_set_item_id: str,
    ad_group_id: Optional[str] = None,
    skip: bool = False,
) -> PlacementAnswer:
    """WRITE: place one open ad into a chosen ad group, or skip it for good.

    Show the person the exact choice (ad copy plus the campaign > ad group label, or the skip)
    and get an explicit yes first. Give exactly one of ad_group_id (from that
    item's options in aeko_list_open_placements) or skip=true. Placing creates the ad at OpenAI
    now, always PAUSED; it does not follow the workflow's turn-on setting, and nothing delivers
    until the person turns it on. Skipping leaves the ad out for good. Repeating the identical
    answer returns the first result, so after mutation_state=unknown repeat the same call to
    recover; a different answer fails with PLACEMENT_NOT_PENDING. Pro+ only.
    """
    domain = uuid_arg(domain_id, "domain_id")
    item = uuid_arg(ad_set_item_id, "ad_set_item_id")
    if type(skip) is not bool:
        raise AekoToolInputError("INVALID_ARGUMENT", "skip must be true or false.")
    if skip == (ad_group_id is not None):
        raise AekoToolInputError("INVALID_ARGUMENT", "Give either ad_group_id or skip=true, not both or neither.")
    body: dict[str, Any] = {"skip": True} if skip else {"ad_group_id": uuid_arg(ad_group_id, "ad_group_id")}
    try:
        data = client.post(f"{BASE}/placements/{item}", json=body, params={"domain_id": domain})
    except AekoAPIError as exc:
        if not exc.request_sent:
            state = "not_attempted"
        elif exc.http_status is not None and exc.http_status < 500:
            state = "rejected"
        else:
            state = "unknown"
        raise api_error(exc, mutation_state=state) from None
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout):
        raise AekoToolError(
            "BACKEND_UNREACHABLE", "AEKO could not be reached, so the answer was not sent."
        ) from None
    except httpx.TimeoutException:
        raise AekoToolError(
            "WRITE_RESULT_UNKNOWN",
            "AEKO did not respond before the timeout. The answer may have been applied; repeat the "
            "identical call to learn the result.",
            mutation_state="unknown",
        ) from None
    except Exception:  # noqa: BLE001 - JSON decode errors and anything else after submission
        raise AekoToolError(
            "WRITE_RESULT_UNKNOWN",
            "The request failed after it may have reached AEKO. Repeat the identical call to "
            "learn the result.",
            mutation_state="unknown",
        ) from None
    try:
        data = _dict(data)
        if data.get("status") not in {"placed", "skipped"} or data.get("ad_set_item_id") != item:
            raise _bad()
        return PlacementAnswer(
            status=data["status"], ad_set_item_id=item,
            campaign_id=_str(data.get("campaign_id")), ad_group_id=_str(data.get("ad_group_id")),
            label=_str(data.get("label")), ad_id=_str(data.get("ad_id")),
        )
    except AekoToolError as exc:
        raise AekoToolError(exc.code, exc.error_message, mutation_state="unknown") from None
