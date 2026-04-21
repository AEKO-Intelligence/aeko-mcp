from ..server import mcp, client
from ._annotations import READ_ONLY


def _format_pages(data: dict) -> str:
    pages = data if isinstance(data, list) else data.get("pages", [])

    if not pages:
        return "No store page analyses found for this domain."

    lines = ["# Store Page Analysis", ""]
    lines.append(f"Found {len(pages)} analyzed page(s).")
    lines.append("")

    for i, page in enumerate(pages[:20], 1):
        url = page.get("url") or page.get("product_url", "N/A")
        title = page.get("title") or page.get("product_title", "Untitled")
        status = page.get("status", "unknown")
        lines.append(f"## {i}. {title}")
        lines.append(f"- **URL**: {url}")
        lines.append(f"- **Status**: {status}")

        result = page.get("analysis_result")
        if result and isinstance(result, dict):
            score = result.get("overall_score") or result.get("score")
            if score is not None:
                lines.append(f"- **AI-Readiness Score**: {score}/100")

            issues = result.get("issues") or result.get("recommendations", [])
            if issues:
                lines.append("- **Issues/Recommendations**:")
                for issue in issues[:5]:
                    if isinstance(issue, str):
                        lines.append(f"  - {issue}")
                    elif isinstance(issue, dict):
                        lines.append(f"  - {issue.get('message', issue.get('description', str(issue)))}")

        lines.append("")

    if len(pages) > 20:
        lines.append(f"*...and {len(pages) - 20} more pages not shown.*")
        lines.append("")

    return "\n".join(lines)


def _format_cited_pages(cited_pages: list) -> str:
    if not cited_pages:
        return "No cited pages found. AI engines have not yet cited any pages from your domain as sources."

    lines = ["# Pages Cited by AI Engines", ""]
    lines.append(f"Found {len(cited_pages)} page(s) from your domain cited as sources by AI engines.")
    lines.append("")

    lines.append("| # | Page | Citations | Title |")
    lines.append("|---|------|-----------|-------|")
    for i, page in enumerate(cited_pages[:25], 1):
        url = page.get("url", "/")
        full_url = page.get("full_url", url)
        count = page.get("count", 0)
        title = page.get("title") or "Untitled"
        lines.append(f"| {i} | {full_url} | {count} | {title} |")
    lines.append("")

    # Show which prompts triggered citations for the top pages
    for page in cited_pages[:5]:
        prompts = page.get("prompts", [])
        if prompts:
            lines.append(f"### Citations for {page.get('full_url', page.get('url', '/'))}")
            lines.append("")
            for p in prompts[:5]:
                ai_model = p.get("ai_model", "Unknown")
                prompt_text = p.get("prompt_en") or p.get("text", "")
                lines.append(f"- **{ai_model}**: {prompt_text[:120]}{'...' if len(prompt_text) > 120 else ''}")
            lines.append("")

    return "\n".join(lines)


@mcp.tool(annotations=READ_ONLY)
def aeko_get_page_analysis(domain_id: str) -> str:
    """Get AI-readiness analysis for store pages.

    Shows how well store product pages are optimized for AI engine understanding,
    including scores and specific improvement recommendations.

    Args:
        domain_id: UUID of the domain.
    """
    data = client.get("/api/store-pages/analysis", params={"domain_id": domain_id})
    return _format_pages(data)


@mcp.tool(annotations=READ_ONLY)
def aeko_get_cited_sources(domain_id: str) -> str:
    """Get pages from your domain that AI engines cite as sources.

    Shows which of your pages are being referenced by ChatGPT, Claude, Gemini,
    and Perplexity when they answer user questions, along with citation counts
    and the prompts that triggered those citations.

    Args:
        domain_id: UUID of the domain.
    """
    data = client.get("/api/visibility/summary", params={"domain_id": domain_id})
    return _format_cited_pages(data.get("cited_pages", []))
