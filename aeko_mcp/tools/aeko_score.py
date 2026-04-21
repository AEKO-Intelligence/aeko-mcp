from ..server import mcp, client
from ._annotations import READ_ONLY


@mcp.tool(annotations=READ_ONLY)
def aeko_get_score(domain_id: str) -> str:
    """Get composite AEKO Score for a domain. Combines 5 components: AI Mention Frequency (30%), Citation Rate (20%), Content Citability (20%), Technical Readiness (20%), Sentiment (10%). Weights redistribute dynamically when a component lacks data. Returns overall score (0-100), letter grade (A-F), component breakdown, and top competitors.

    Args:
        domain_id: UUID of the domain to analyze.
    """
    data = client.get("/api/geo-score", params={"domain_id": domain_id})

    overall = data.get("overall", 0)
    grade = data.get("grade", "F")
    components = data.get("components", {})
    top_competitors = data.get("top_competitors", [])

    lines = [f"## AEKO Score: {overall}/100 (Grade: {grade})\n"]
    lines.append("| Component | Score | Weight | Has Data | Detail |")
    lines.append("|-----------|-------|--------|----------|--------|")

    comp_labels = {
        "ai_mention_frequency": "AI Mention Frequency",
        "citation_rate": "Citation Rate",
        "content_citability": "Content Citability",
        "technical_readiness": "Technical Readiness",
        "sentiment": "Sentiment",
    }

    for key, label in comp_labels.items():
        c = components.get(key, {})
        score = c.get("score", 0)
        weight = int(c.get("weight", 0) * 100)
        has_data = "Yes" if c.get("has_data", False) else "No"
        raw = c.get("raw", {})
        detail_parts = [f"{k}: {v}" for k, v in raw.items()]
        detail = ", ".join(detail_parts) if detail_parts else "—"
        lines.append(f"| {label} | {score}/100 | {weight}% | {has_data} | {detail} |")

    if top_competitors:
        lines.append("")
        lines.append("### Top Competitors")
        lines.append("")
        lines.append("| Competitor | Mentions |")
        lines.append("|------------|----------|")
        for comp in top_competitors:
            lines.append(f"| {comp.get('name', 'Unknown')} | {comp.get('mentions', 0)} |")

    return "\n".join(lines)
