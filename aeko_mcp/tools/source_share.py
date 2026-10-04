"""Citation share of the domains AI answers cite, from the Source Analysis read model."""

from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import quote

from ..server import client, mcp
from ._annotations import READ_ONLY

DOMAIN_LIMIT = 25
URL_LIMIT = 20
DEFAULT_DAYS = 90


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()


def _cell(text: Any, limit: Optional[int] = None) -> str:
    """Text for a markdown table cell: one line, no pipes, optionally clipped."""
    value = " ".join(str(text if text is not None else "").split()).replace("|", "/")
    if limit is not None and len(value) > limit:
        value = value[: limit - 3] + "..."
    return value or "-"


def _count(value: Any) -> str:
    return f"{int(value or 0):,}"


def _parse_day(value: str, name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{name} must be a YYYY-MM-DD date, got {value!r}") from None


def _resolve_window(from_date: Optional[str], to_date: Optional[str]) -> tuple[date, date]:
    to_day = _parse_day(to_date, "to_date") if to_date else _utc_today()
    from_day = _parse_day(from_date, "from_date") if from_date else to_day - timedelta(days=DEFAULT_DAYS - 1)
    if from_day > to_day:
        raise ValueError(f"from_date {from_day} is after to_date {to_day}")
    return from_day, to_day


def _scope_params(domain_id: str, prompt_ids: Optional[list[str]], ai_platform: Optional[str]) -> dict[str, Any]:
    params: dict[str, Any] = {"domain_id": domain_id}
    encoded = ",".join(str(pid) for pid in (prompt_ids or []) if str(pid).strip())
    if encoded:
        params["prompt_ids"] = encoded
    if ai_platform:
        params["ai_platform"] = ai_platform
    return params


def _platform_lines(domains: list[dict], more_pages: bool) -> list[str]:
    totals: dict[str, int] = {}
    for row in domains:
        for platform in row.get("platforms") or []:
            name = _cell(platform.get("platform"))
            totals[name] = totals.get(name, 0) + int(platform.get("citations") or 0)
    cited = sum(totals.values())
    heading = "## Share by platform"
    if more_pages:
        heading += f" (over the top {len(domains)} domains)"
    lines = [heading, ""]
    if not cited:
        return lines + ["No platform citations in the listed domains."]
    lines += ["| platform | share % | citations |", "|---|---|---|"]
    for name, citations in sorted(totals.items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"| {name} | {citations / cited * 100:.1f} | {citations:,} |")
    return lines


def _format_domain_share(current: dict, previous: dict, window: tuple[date, date], previous_window: tuple[date, date]) -> str:
    domains = current.get("domains") or []
    totals = current.get("totals") or {}
    range_ = current.get("range") or {}
    lines = [
        "# Source share",
        "",
        f"Range: {range_.get('from') or window[0].isoformat()} ~ {range_.get('to') or window[1].isoformat()}",
        f"Previous period: {previous_window[0].isoformat()} ~ {previous_window[1].isoformat()}",
        f"Total citations: {_count(totals.get('citations'))} across {_count(totals.get('domains'))} domains",
        "",
    ]
    if not domains:
        lines.append("No citations in this scope and range.")
        return "\n".join(lines)

    lines += _platform_lines(domains, bool(current.get("cursor")))
    lines += ["", "## Share by domain", ""]
    previous_share = {
        row.get("domain"): row.get("share_pct") for row in previous.get("domains") or [] if row.get("share_pct") is not None
    }
    lines += [
        "| rank | domain | share % | citations | urls | Δ vs previous period (pp) |",
        "|---|---|---|---|---|---|",
    ]
    for index, row in enumerate(domains):
        share = row.get("share_pct")
        before = previous_share.get(row.get("domain"))
        delta = "—" if share is None or before is None else f"{float(share) - float(before):+.1f}"
        share_text = "-" if share is None else f"{float(share):.1f}"
        lines.append(
            f"| {index + 1} | {_cell(row.get('domain'))} | {share_text} | {_count(row.get('citations'))}"
            f" | {_count(row.get('url_count'))} | {delta} |"
        )
    lines += [
        "",
        "Share % = the domain's citations / all citations in this scope and range."
        f" Δ `—` = not among the previous period's top {DOMAIN_LIMIT} domains.",
        "",
        f"showing {len(domains):,} of {_count(totals.get('domains'))} domains",
    ]
    return "\n".join(lines)


def _format_domain_urls(domain: str, data: dict) -> str:
    urls = data.get("urls") or []
    lines = [f"# Top URLs of {_cell(domain)}", ""]
    if not urls:
        lines.append(f"No citations of {_cell(domain)} in this scope (all time).")
        return "\n".join(lines)
    lines += ["| url | title | citations | last cited |", "|---|---|---|---|"]
    for row in urls:
        last_cited = _cell(str(row.get("last_cited_at") or "")[:10])
        lines.append(
            f"| {_cell(row.get('url'))} | {_cell(row.get('title'), 80)} | {_count(row.get('citations'))} | {last_cited} |"
        )
    lines += ["", f"showing {len(urls):,} of {_count(data.get('total'))} URLs"]
    return "\n".join(lines)


@mcp.tool(title="Get source share", annotations=READ_ONLY)
def aeko_get_source_share(
    domain_id: str,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    prompt_ids: Optional[list[str]] = None,
    ai_platform: Optional[str] = None,
    domain: Optional[str] = None,
) -> str:
    """Read which domains AI answers cite for a domain's tracked prompts, as shares.

    Starter+ feature server-side. Without `domain`: total citations, the share
    by AI platform, and the top 25 cited domains (share %, citations, distinct
    URLs, change in share vs the previous period of the same length, in
    percentage points). The range is `from_date`/`to_date` (`YYYY-MM-DD`, UTC
    days, inclusive); it defaults to the last 90 UTC days ending today.

    With `domain` (a cited domain such as `news.naver.com`, as listed in the
    domain table): the top 20 URLs of that domain (title, citations, last
    cited). The URL list counts all time; `from_date`/`to_date` do not apply.

    Optional `prompt_ids` and `ai_platform` narrow the scope of either read.
    Only these capped summaries are available here: raw citation rows are not
    served through MCP; the dashboard's Source Analysis export has them.
    """
    params = _scope_params(domain_id, prompt_ids, ai_platform)
    if domain:
        data = client.get(
            f"/api/monitoring/sources/domains/{quote(domain, safe='')}/urls",
            params={**params, "limit": URL_LIMIT},
        )
        return _format_domain_urls(domain, data)

    window = _resolve_window(from_date, to_date)
    length = window[1] - window[0] + timedelta(days=1)
    previous_window = (window[0] - length, window[0] - timedelta(days=1))
    current = client.get(
        "/api/monitoring/sources/domains",
        params={**params, "from": window[0].isoformat(), "to": window[1].isoformat(), "limit": DOMAIN_LIMIT},
    )
    previous = client.get(
        "/api/monitoring/sources/domains",
        params={
            **params,
            "from": previous_window[0].isoformat(),
            "to": previous_window[1].isoformat(),
            "limit": DOMAIN_LIMIT,
        },
    )
    return _format_domain_share(current, previous, window, previous_window)
