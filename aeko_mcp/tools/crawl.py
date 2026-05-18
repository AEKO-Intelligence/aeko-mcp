"""Live URL inspection for the content-creation skill.

The tracked-prompt payload (`aeko_get_tracked_prompt`) carries a snapshot of
each cited source crawled at response-collection time, which can be days or
weeks stale by the time a skill drafts content. This module exposes a
first-class crawl primitive that re-fetches a URL on demand and returns the
title, meta description, OG fields, heading hierarchy, paragraph / list /
image stats, and raw JSON-LD blocks — i.e., everything a content skill needs
to mimic a winning source's structure and emit matching schema.

Prefer this over `WebFetch` for forensics: WebFetch returns markdown
(JSON-LD `<script>` blocks are stripped during HTML→markdown conversion),
which is fine for human reading but useless for schema mirroring.
"""

import json
from typing import Any

from ..server import mcp, client
from ._annotations import READ_ONLY


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def _coerce_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _heading_summary(headings: Any) -> tuple[int, int]:
    """Return (count, max_depth) for a list of heading dicts."""
    if not isinstance(headings, list):
        return 0, 0
    count = 0
    max_depth = 0
    for h in headings:
        if not isinstance(h, dict):
            continue
        count += 1
        level = _coerce_int(h.get("level"))
        if level is not None and level > max_depth:
            max_depth = level
    return count, max_depth


def _format_crawl(data: dict) -> str:
    """Render the crawl payload as compact markdown for skill consumption."""

    url = data.get("url") or "(unknown)"
    final_url = data.get("final_url") or url
    status = data.get("status")
    cached = data.get("cached")
    fetched_at = data.get("fetched_at")

    lines: list[str] = []
    lines.append(f"# Crawl: {url}")
    lines.append("")

    header_bits: list[str] = []
    if status is not None:
        header_bits.append(f"status={status}")
    if cached is not None:
        header_bits.append(f"cached={'yes' if cached else 'no'}")
    if fetched_at:
        header_bits.append(f"fetched_at={fetched_at}")
    if final_url and final_url != url:
        header_bits.append(f"final_url={final_url}")
    if header_bits:
        lines.append(f"- {' · '.join(header_bits)}")

    title = data.get("title")
    meta_description = data.get("meta_description")
    canonical = data.get("canonical_url")
    language = data.get("language")
    if title:
        lines.append(f"- **Title**: {title}")
    if meta_description:
        lines.append(f"- **Meta description**: {meta_description}")
    if canonical and canonical != final_url:
        lines.append(f"- **Canonical**: {canonical}")
    if language:
        lines.append(f"- **Language**: {language}")

    og = data.get("og")
    if isinstance(og, dict) and any(og.values()):
        og_bits: list[str] = []
        for key in ("title", "description", "image", "type", "site_name"):
            val = og.get(key)
            if val:
                og_bits.append(f"{key}={val}")
        if og_bits:
            lines.append(f"- **OG**: {' · '.join(og_bits)}")

    citability = _coerce_float(data.get("citability_score"))
    if citability is not None:
        lines.append(f"- **Citability score**: {citability:.2f}")

    lines.append("")
    lines.append("## Structure")
    lines.append("")

    headings = data.get("headings")
    h_count, h_depth = _heading_summary(headings)
    depth_str = f"h{h_depth}" if h_depth else "none"
    lines.append(f"- Headings: count={h_count} · max_depth={depth_str}")
    if isinstance(headings, list) and headings:
        sample = []
        for h in headings[:8]:
            if isinstance(h, dict):
                lvl = h.get("level")
                txt = h.get("text") or ""
                if lvl and txt:
                    sample.append(f"h{lvl}: {txt[:80]}")
        if sample:
            lines.append("  - " + "\n  - ".join(sample))

    paragraphs = data.get("paragraphs") or {}
    if isinstance(paragraphs, dict):
        p_count = _coerce_int(paragraphs.get("count")) or 0
        p_total = _coerce_int(paragraphs.get("total_word_count")) or 0
        p_avg = _coerce_float(paragraphs.get("avg_word_count"))
        p_med = _coerce_float(paragraphs.get("median_word_count"))
        bits = [f"count={p_count}", f"total_words={p_total}"]
        if p_avg is not None:
            bits.append(f"avg_words={p_avg:.0f}")
        if p_med is not None:
            bits.append(f"median_words={p_med:.0f}")
        lines.append(f"- Paragraphs: {' · '.join(bits)}")

    lists = data.get("lists") or {}
    if isinstance(lists, dict):
        ul = _coerce_int(lists.get("ul_count")) or 0
        ol = _coerce_int(lists.get("ol_count")) or 0
        items = _coerce_int(lists.get("total_items")) or 0
        lines.append(f"- Lists: ul={ul} · ol={ol} · items={items}")

    images = data.get("images") or {}
    if isinstance(images, dict):
        i_count = _coerce_int(images.get("count")) or 0
        with_alt = _coerce_int(images.get("with_alt")) or 0
        lines.append(f"- Images: count={i_count} · with_alt={with_alt}")
        alts = images.get("alt_examples")
        if isinstance(alts, list):
            shown = [str(a)[:80] for a in alts[:3] if a]
            if shown:
                lines.append("  - alt examples: " + " | ".join(shown))

    links = data.get("links") or {}
    if isinstance(links, dict):
        internal = _coerce_int(links.get("internal")) or 0
        external = _coerce_int(links.get("external")) or 0
        lines.append(f"- Links: internal={internal} · external={external}")

    lines.append("")
    lines.append("## JSON-LD")
    lines.append("")

    json_ld = data.get("json_ld")
    if not isinstance(json_ld, list) or not json_ld:
        lines.append("_No JSON-LD blocks found._")
    else:
        types_seen: list[str] = []
        for block in json_ld:
            if isinstance(block, dict):
                t = block.get("@type")
                if isinstance(t, str):
                    types_seen.append(t)
                elif isinstance(t, list):
                    types_seen.extend(x for x in t if isinstance(x, str))
        if types_seen:
            lines.append(f"- @types present: {', '.join(sorted(set(types_seen)))}")
        lines.append(f"- Block count: {len(json_ld)}")
        # Emit each block as a fenced code block so skills can copy-paste
        # JSON-LD wholesale into their own HTML output without re-deriving
        # the schema. Truncate any single block over ~4 KB to keep payloads
        # bounded; the skill can re-fetch with `force_refresh=true` if it
        # needs the full block.
        for i, block in enumerate(json_ld, 1):
            try:
                rendered = json.dumps(block, ensure_ascii=False, indent=2)
            except (TypeError, ValueError):
                rendered = repr(block)
            cap = 4000
            if len(rendered) > cap:
                rendered = rendered[: cap - 20] + "\n  ...(truncated)"
            lines.append("")
            lines.append(f"### Block {i}")
            lines.append("```json")
            lines.append(rendered)
            lines.append("```")

    microdata_types = data.get("microdata_types")
    if isinstance(microdata_types, list) and microdata_types:
        lines.append("")
        lines.append(f"- Microdata `itemtype`s: {', '.join(microdata_types[:10])}")

    return "\n".join(lines)


@mcp.tool(title="Crawl a URL", annotations=READ_ONLY)
def aeko_crawl_url(url: str, force_refresh: bool = False) -> str:
    """Re-fetch a URL and return its title / meta / structure / JSON-LD.

    Calls AEKO's backend crawler so the skill sees the same structural
    signal AEKO uses for citability scoring — title, meta description,
    canonical URL, OG fields, heading hierarchy, paragraph / list / image
    stats, raw `<script type="application/ld+json">` blocks, and microdata
    `itemtype` values. Backed by the same crawl pipeline that populates
    `aeko_get_tracked_prompt`'s per-citation `crawl` payload, exposed here
    against an arbitrary URL so content skills can re-verify cited sources
    at draft time and copy a target page's schema into their own HTML.

    Prefer this over `WebFetch` whenever you need JSON-LD or schema parity:
    `WebFetch` strips `<script>` blocks during HTML→markdown conversion,
    which is fine for human reading but useless for schema mirroring.

    Args:
        url: The full URL to crawl (must include scheme).
        force_refresh: When false (default), the backend may serve a cached
            crawl result up to 24h old. Pass true to force a fresh fetch —
            use this when the underlying page has likely changed since the
            cache TTL, e.g., a competitor just updated their PDP.
    """
    params: dict[str, Any] = {"url": url}
    if force_refresh:
        params["force_refresh"] = "true"
    data = client.get("/api/crawl", params=params)
    return _format_crawl(data)
