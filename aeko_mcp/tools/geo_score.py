from ..server import mcp, client
from ._annotations import READ_ONLY


@mcp.tool(annotations=READ_ONLY)
def aeko_get_geo_score(domain_id: str) -> str:
    """Get composite GEO (Generative Engine Optimization) score for a domain. Combines 6 components: AI Mention Frequency (25%), Citation Rate (20%), Content Citability (20%), Technical Infrastructure (15%), Structured Data (10%), Sentiment (10%). Returns overall score, letter grade, and component breakdown.

    Args:
        domain_id: UUID of the domain to analyze.
    """
    data = client.get("/api/geo-score", params={"domain_id": domain_id})

    overall = data.get("overall", 0)
    grade = data.get("grade", "F")
    components = data.get("components", {})

    lines = [f"## GEO Score: {overall}/100 (Grade: {grade})\n"]
    lines.append("| Component | Score | Weight | Detail |")
    lines.append("|-----------|-------|--------|--------|")

    comp_labels = {
        "ai_mention_frequency": "AI Mention Frequency",
        "citation_rate": "Citation Rate",
        "content_citability": "Content Citability",
        "technical_infrastructure": "Technical Infrastructure",
        "structured_data": "Structured Data",
        "sentiment": "Sentiment",
    }

    for key, label in comp_labels.items():
        c = components.get(key, {})
        raw = c.get("raw", {})
        detail_parts = [f"{k}: {v}" for k, v in raw.items()]
        detail = ", ".join(detail_parts) if detail_parts else "—"
        lines.append(f"| {label} | {c.get('score', 0)}/100 | {int(c.get('weight', 0) * 100)}% | {detail} |")

    return "\n".join(lines)
