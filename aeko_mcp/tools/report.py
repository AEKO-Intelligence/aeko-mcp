from ..server import mcp, client
from ._annotations import READ_ONLY


@mcp.tool(annotations=READ_ONLY)
def aeko_prepare_report(domain_id: str) -> str:
    """Gather all AEKO data needed to generate a visibility report.

    Aggregates visibility metrics, page analyses, suggestions, domain
    infrastructure status, and product analyses into a single structured
    brief that Claude can format into any report format.

    Args:
        domain_id: UUID of the domain.

    Returns:
        Comprehensive data brief for report generation.
    """
    # Gather all data from backend endpoints
    domain = client.get(f"/api/domains/{domain_id}")
    visibility = client.get("/api/visibility/summary", params={"domain_id": domain_id})
    pages_data = client.get("/api/store-pages/analysis", params={"domain_id": domain_id})
    suggestions = client.get("/api/suggestions", params={"domain_id": domain_id})

    # Product analyses (may not exist for all domains)
    product_analyses = []
    try:
        product_analyses = client.get("/api/product-analyses", params={"domain_id": domain_id})
        if isinstance(product_analyses, dict):
            product_analyses = product_analyses.get("analyses", [])
    except Exception:
        pass

    pages = pages_data if isinstance(pages_data, list) else pages_data.get("pages", [])
    suggestion_list = suggestions if isinstance(suggestions, list) else suggestions.get("suggestions", [])

    lines = ["# AEKO Visibility Report Data", ""]

    # ── Section 1: Domain Overview ──
    lines.append("## 1. Domain Overview")
    lines.append(f"- **Name**: {domain.get('name', 'N/A')}")
    lines.append(f"- **URL**: {domain.get('base_url', 'N/A')}")
    scope = domain.get("scope") or {}
    if scope:
        lines.append(f"- **Industry**: {scope.get('industry', 'N/A')}")
        lines.append(f"- **Vertical**: {scope.get('vertical', 'N/A')}")
    lines.append("")

    # Infrastructure status
    lines.append("### Infrastructure Status")
    lines.append(f"- robots.txt blocks AI: {domain.get('robots_blocks_ai', 'unknown')}")
    lines.append(f"- Has JSON-LD: {domain.get('has_json_ld', 'unknown')}")
    lines.append(f"- Has sitemap: {domain.get('has_sitemap', 'unknown')}")
    lines.append(f"- Has llms.txt: {domain.get('has_llms_txt', 'unknown')}")
    lines.append("")

    # ── Section 2: AI Visibility Metrics ──
    lines.append("## 2. AI Visibility Metrics")

    if isinstance(visibility, dict):
        metrics = visibility.get("metrics") or visibility
        lines.append(f"- **Total mentions**: {metrics.get('total_mentions', 'N/A')}")
        lines.append(f"- **Mention trend**: {metrics.get('mention_trend', 'N/A')}")
        lines.append(f"- **Citation count**: {metrics.get('citation_count', 'N/A')}")
        lines.append(f"- **Citation rate**: {metrics.get('citation_rate', 'N/A')}")
        lines.append(f"- **Average sentiment**: {metrics.get('avg_sentiment', 'N/A')}")

        # Platform breakdown if available
        platform_data = metrics.get("by_platform") or visibility.get("by_platform")
        if platform_data:
            lines.append("")
            lines.append("### By Platform")
            for platform, data in (platform_data.items() if isinstance(platform_data, dict) else []):
                if isinstance(data, dict):
                    lines.append(f"- **{platform}**: {data.get('mentions', 0)} mentions, {data.get('citations', 0)} citations")
                else:
                    lines.append(f"- **{platform}**: {data}")

        # Trends if available
        trends = metrics.get("trends") or visibility.get("trends")
        if trends and isinstance(trends, list):
            lines.append("")
            lines.append("### Recent Trends")
            for t in trends[-5:]:
                if isinstance(t, dict):
                    lines.append(f"- {t.get('period', 'N/A')}: {t.get('mentions', 0)} mentions")

        # Cited pages
        cited = visibility.get("cited_pages") or visibility.get("cited_sources")
        if cited and isinstance(cited, list):
            lines.append("")
            lines.append("### Pages Cited by AI Engines")
            for c in cited[:20]:
                if isinstance(c, dict):
                    lines.append(f"- {c.get('url', c.get('title', 'N/A'))} — {c.get('citation_count', '?')} citations")
    else:
        lines.append("- No visibility data available yet")
    lines.append("")

    # ── Section 3: Page Analysis ──
    lines.append(f"## 3. Page Analysis ({len(pages)} pages scanned)")
    lines.append("")

    if pages:
        # Summary stats
        scores = [p.get("ai_readiness_score") for p in pages if p.get("ai_readiness_score") is not None]
        if scores:
            avg_score = sum(scores) / len(scores)
            lines.append(f"- **Average AI readiness score**: {avg_score:.1f}/100")
            lines.append(f"- **Highest score**: {max(scores)}/100")
            lines.append(f"- **Lowest score**: {min(scores)}/100")
            lines.append("")

        # Pages with JSON-LD
        with_jsonld = sum(1 for p in pages if p.get("has_product_jsonld") or p.get("has_article_jsonld"))
        lines.append(f"- **Pages with JSON-LD**: {with_jsonld}/{len(pages)}")
        lines.append("")

        lines.append("### Page Details")
        for p in pages[:30]:
            url = p.get("url", "N/A")
            title = p.get("title", "")
            score = p.get("ai_readiness_score", "?")
            types = []
            if p.get("has_product_jsonld"):
                types.append("Product")
            if p.get("has_article_jsonld"):
                types.append("Article")
            type_str = f" [{', '.join(types)}]" if types else ""
            lines.append(f"- **{title or url}** — Score: {score}/100{type_str}")
            if title and url:
                lines.append(f"  URL: {url}")

            # Include analysis details if available
            analysis = p.get("source_analysis") or {}
            if analysis:
                issues = analysis.get("issues") or []
                if issues:
                    for issue in issues[:3]:
                        if isinstance(issue, dict):
                            lines.append(f"  - Issue: {issue.get('message', issue.get('type', ''))}")
                        elif isinstance(issue, str):
                            lines.append(f"  - Issue: {issue}")
    else:
        lines.append("No pages have been scanned yet.")
    lines.append("")

    # ── Section 4: Suggestions ──
    lines.append(f"## 4. Optimization Suggestions ({len(suggestion_list)} total)")
    lines.append("")

    if suggestion_list:
        # Group by category
        by_category: dict[str, list] = {}
        for s in suggestion_list:
            cat = s.get("category", "other")
            by_category.setdefault(cat, []).append(s)

        for cat, items in by_category.items():
            lines.append(f"### {cat.replace('_', ' ').title()} ({len(items)})")
            for s in items[:10]:
                priority = s.get("priority", "")
                title = s.get("title", s.get("message", "N/A"))
                priority_marker = f" [{priority.upper()}]" if priority else ""
                lines.append(f"- {title}{priority_marker}")
                desc = s.get("description", "")
                if desc:
                    lines.append(f"  {desc[:200]}")
            lines.append("")
    else:
        lines.append("No suggestions available yet.")
    lines.append("")

    # ── Section 5: Product Analyses ──
    if product_analyses:
        lines.append(f"## 5. Product Analyses ({len(product_analyses)} products)")
        lines.append("")
        for pa in product_analyses[:20]:
            product_url = pa.get("product_url", "N/A")
            country = pa.get("country", "")
            lines.append(f"### {pa.get('product_name', product_url)}")
            if country:
                lines.append(f"- **Market**: {country}")
            lines.append(f"- **URL**: {product_url}")

            # Competitive data
            competitors = pa.get("competitors") or pa.get("competitive_data") or {}
            if competitors:
                lines.append("- **Competitors found**: " + str(len(competitors) if isinstance(competitors, list) else "yes"))

            positioning = pa.get("positioning") or pa.get("analysis") or {}
            if isinstance(positioning, dict):
                strengths = positioning.get("strengths") or positioning.get("competitive_advantages")
                if strengths:
                    lines.append(f"- **Strengths**: {strengths if isinstance(strengths, str) else ', '.join(strengths[:5])}")
                weaknesses = positioning.get("weaknesses") or positioning.get("gaps")
                if weaknesses:
                    lines.append(f"- **Gaps**: {weaknesses if isinstance(weaknesses, str) else ', '.join(weaknesses[:5])}")
            lines.append("")
    else:
        lines.append("## 5. Product Analyses")
        lines.append("No product analyses available yet.")
        lines.append("")

    # ── Instructions for Report Generation ──
    lines.append("---")
    lines.append("## Report Generation Instructions")
    lines.append("")
    lines.append("Use the data above to create a professional visibility report with these sections:")
    lines.append("")
    lines.append("1. **Executive Summary** — Overall assessment (2-3 sentences), key score, biggest win + biggest risk")
    lines.append("2. **AI Visibility Metrics** — Mentions, citations, sentiment trends across platforms")
    lines.append("3. **Page-by-Page Analysis** — AI readiness scores, structured data coverage")
    lines.append("4. **Infrastructure Status** — robots.txt, llms.txt, JSON-LD, sitemap")
    lines.append("5. **Prioritized Action Items** — Critical → Low severity, estimated effort")
    lines.append("6. **Competitive Insights** — From product analyses (if available)")
    lines.append("")
    lines.append("The user can save the output via `aeko_save_content` in whatever format they prefer.")

    return "\n".join(lines)
