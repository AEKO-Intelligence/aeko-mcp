"""AEKO source-content MCP tool.

Thin wrapper over ``GET /api/sources/content?url=...`` — fetches the
previously-crawled text for a source URL so Claude can draft by mirroring
real competitor / reference page structure instead of hallucinating.

Extracted from ``content_recommendations.py`` when the campaign surface
was retired; the endpoint itself has no campaign coupling and remains
useful for any drafting workflow.
"""

from ..server import mcp, client
from ._annotations import READ_ONLY


def _safe(method, *args, **kwargs) -> tuple[dict | None, str | None]:
    try:
        return method(*args, **kwargs), None
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


@mcp.tool(annotations=READ_ONLY)
def aeko_fetch_source_content(url: str) -> str:
    """Fetch the full content of a previously-crawled source URL.

    Read the actual page text for a reference/competitor URL AEKO has
    already crawled, so Claude can mirror its structure when drafting.
    Capped at 12KB per source to keep the MCP payload sane.

    Returns a not-found note if the URL has not been crawled (no on-demand
    fetch). Growth+ tier-gated at the backend.

    Args:
        url: Canonical URL of the source.

    Returns:
        Markdown with the page's title, headings, JSON-LD types, and
        extracted text (capped at 12KB).
    """
    resp, err = _safe(client.get, "/api/sources/content", params={"url": url})
    if err:
        return f"# Source content\n\nCould not fetch `{url}`: {err}"

    if not resp:
        return f"# Source content\n\nNot found: `{url}`"

    lines = [f"# Source: {resp.get('title') or url}", ""]
    lines.append(f"- **URL**: {resp.get('url', url)}")
    if resp.get("meta_description"):
        lines.append(f"- **Description**: {resp['meta_description']}")
    if resp.get("crawled_at"):
        lines.append(f"- **Crawled at**: {resp['crawled_at']}")
    if resp.get("jsonld_types"):
        lines.append(f"- **JSON-LD types**: {', '.join(resp['jsonld_types'])}")
    if resp.get("truncated"):
        lines.append(
            "- **Note**: Content was truncated to 12KB. Full page is longer."
        )
    lines.append("")

    headings = resp.get("headings") or []
    if headings:
        lines.append("## Structure")
        for h in headings[:30]:
            lines.append(f"- {h}")
        lines.append("")

    text = resp.get("extracted_text") or ""
    if text:
        lines.append("## Extracted text")
        lines.append("```")
        lines.append(text)
        lines.append("```")
    return "\n".join(lines)
