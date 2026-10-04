"""MCP tools for AEKO measurement and analytics reads."""

import json
from typing import Any, Optional

from ..server import client, mcp
from ._annotations import READ_ONLY


def _json_block(title: str, payload: Any) -> str:
    return f"# {title}\n\n```json\n{json.dumps(payload, ensure_ascii=False, indent=2, default=str)}\n```"


def _prompt_ids_param(prompt_ids: Optional[list[str]]) -> Optional[str]:
    if not prompt_ids:
        return None
    return ",".join(str(pid) for pid in prompt_ids if str(pid).strip())


PER_PROMPT_MAX = 10


def _cell(text: Any, limit: Optional[int] = None) -> str:
    """Text for a markdown table cell or list line: one line, no pipes, optionally clipped."""
    value = " ".join(str(text if text is not None else "").split()).replace("|", "/")
    if limit is not None and len(value) > limit:
        value = value[: limit - 3] + "..."
    return value or "-"


def _num(value: Any, places: int) -> str:
    return "-" if value is None else f"{float(value):.{places}f}"


def _count(value: Any) -> str:
    return f"{int(value or 0):,}"


def _range_line(range_: Optional[dict]) -> str:
    if not range_:
        return "Range: all time"
    return f"Range: {range_.get('from') or '?'} ~ {range_.get('to') or '?'}"


def _format_share_of_voice(data: dict, limit: int, show_per_prompt: bool) -> str:
    brands = data.get("brands") or []
    brands_total = data.get("brands_total") or 0
    lines = ["# Share of Voice", "", _range_line(data.get("range")), ""]

    if brands:
        lines.append("| rank | brand | share % | mentions | avg visibility | avg position | cited responses / responses |")
        lines.append("|---|---|---|---|---|---|---|")
        for index, brand in enumerate(brands):
            # Rows past `limit` are the own brand or configured competitors the backend appends
            # from below the top page, so their place in the list is not their rank.
            rank = str(index + 1) if index < limit else "-"
            name = _cell(brand.get("name"))
            if brand.get("is_own_brand"):
                name = f"★ {name}"
            lines.append(
                f"| {rank} | {name} | {_num(brand.get('mention_share_pct'), 1)} | {_count(brand.get('total_mentions'))}"
                f" | {_num(brand.get('avg_visibility'), 2)} | {_num(brand.get('avg_position'), 2)}"
                f" | {_count(brand.get('cited_response_count'))} / {_count(brand.get('response_count'))} |"
            )
        lines.append("")
        lines.append(
            "★ = your brand. Share % = the brand's mentions / all brand mentions in this scope and range."
        )
        if len(brands) > limit:
            lines.append("Unranked rows (`-`) are your brand or configured competitors from below the top list.")
    else:
        lines.append("No brand mentions in this scope and range.")
    showing = f"showing {len(brands):,} of {brands_total:,} brands"
    if len(brands) < brands_total and limit < 50:
        showing += " (raise `limit`, max 50, to see more)"
    lines.extend(["", showing, ""])

    lines.append("## Top brands per prompt")
    lines.append("")
    if not show_per_prompt:
        lines.append(
            f"Per-prompt detail is shown for views of {PER_PROMPT_MAX} prompts or fewer:"
            f" pass up to {PER_PROMPT_MAX} `prompt_ids` to see it."
        )
        return "\n".join(lines)
    per_prompt = data.get("per_prompt") or []
    if not per_prompt:
        lines.append("No prompts with responses in this scope and range.")
    for row in per_prompt:
        top = row.get("top_brands") or []
        if top:
            listed = ", ".join(f"{_cell(b.get('name'))} ({_count(b.get('mention_count'))})" for b in top)
            more = (row.get("brands_total") or 0) - len(top)
            if more > 0:
                listed += f" (+{more:,} more)"
        else:
            listed = "no brands"
        lines.append(
            f"- {_cell(row.get('prompt_text'), 60)} · {_cell(row.get('ai_platform'))} · {_cell(row.get('country'))}"
            f" → {listed}"
        )
    return "\n".join(lines)


@mcp.tool(title="Get share of voice", annotations=READ_ONLY)
def aeko_get_share_of_voice(
    domain_id: str,
    prompt_ids: Optional[list[str]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    limit: int = 25,
) -> str:
    """Read Share of Voice for a domain across tracked prompt responses.

    Starter+ feature server-side. Returns a brand table ranked by mentions
    (share %, mentions, average visibility and position, cited responses) with
    "showing N of M brands", your brand marked ★. All time unless a range is
    given: `from_date`/`to_date` (`YYYY-MM-DD`, inclusive; `start_date`/`end_date`
    are the same). `limit` brands (1-50, default 25). Optional `prompt_ids`
    scope the read; with 10 or fewer, each prompt's top brands are listed too.
    """
    limit = max(1, min(int(limit), 50))
    params: dict[str, Any] = {"domain_id": domain_id}
    encoded_prompt_ids = _prompt_ids_param(prompt_ids)
    if encoded_prompt_ids:
        params["prompt_ids"] = encoded_prompt_ids
    range_from = from_date or start_date
    range_to = to_date or end_date
    if range_from:
        params["from"] = range_from
    if range_to:
        params["to"] = range_to
    params["limit"] = limit
    prompt_count = len(encoded_prompt_ids.split(",")) if encoded_prompt_ids else 0
    show_per_prompt = 0 < prompt_count <= PER_PROMPT_MAX
    params["per_prompt_limit"] = prompt_count if show_per_prompt else 1
    data = client.get("/api/monitoring/sov", params=params)
    return _format_share_of_voice(data, limit, show_per_prompt)


@mcp.tool(title="Get answer drift", annotations=READ_ONLY)
def aeko_get_answer_drift(
    domain_id: str,
    days: int = 30,
    prompt_ids: Optional[list[str]] = None,
) -> str:
    """Read answer drift for a domain over a recent lookback window."""
    params: dict[str, Any] = {
        "domain_id": domain_id,
        "days": max(1, min(int(days), 365)),
    }
    encoded_prompt_ids = _prompt_ids_param(prompt_ids)
    if encoded_prompt_ids:
        params["prompt_ids"] = encoded_prompt_ids
    data = client.get("/api/monitoring/drift", params=params)
    return _json_block("GET /api/monitoring/drift", data)


@mcp.tool(title="Get measure dashboard", annotations=READ_ONLY)
def aeko_get_measure(
    domain_id: str,
    view: str = "readiness",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> str:
    """Read AEKO Measure views: readiness, discovery, or impact."""
    normalized_view = view.strip().lower()
    if normalized_view not in {"readiness", "discovery", "impact"}:
        return "Invalid `view`. Use one of: readiness, discovery, impact."
    params: dict[str, Any] = {"domain_id": domain_id}
    if normalized_view in {"discovery", "impact"}:
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
    path = f"/api/measure/{normalized_view}"
    data = client.get(path, params=params)
    return _json_block(f"GET {path}", data)

