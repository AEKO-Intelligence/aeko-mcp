from ..server import mcp, client


@mcp.tool()
def aeko_get_citability(source_id: str) -> str:
    """Get AI citability score for a specific page. Shows how well the page content can be cited by AI engines across 5 dimensions: Answer Block Quality (30%), Self-Containment (25%), Structural Readability (20%), Statistical Density (15%), Uniqueness Signals (10%).

    Args:
        source_id: UUID of the source (page) to analyze.
    """
    data = client.get("/api/citability/page", params={"source_id": source_id})

    overall = data.get("overall", 0)
    dims = data.get("dimensions", {})
    improvements = data.get("top_improvements", [])

    lines = [f"## Citability Score: {overall}/100\n"]
    lines.append("| Dimension | Score | Weight |")
    lines.append("|-----------|-------|--------|")

    dim_labels = {
        "answer_block_quality": "Answer Block Quality",
        "self_containment": "Self-Containment",
        "structural_readability": "Structural Readability",
        "statistical_density": "Statistical Density",
        "uniqueness_signals": "Uniqueness Signals",
    }

    for key, label in dim_labels.items():
        d = dims.get(key, {})
        lines.append(f"| {label} | {d.get('score', 0)}/100 | {int(d.get('weight', 0) * 100)}% |")

    if improvements:
        lines.append("\n### Top Improvements")
        for imp in improvements:
            lines.append(f"- {imp}")

    return "\n".join(lines)


@mcp.tool()
def aeko_score_text(text: str, language: str = "") -> str:
    """Score arbitrary text for AI citability. Useful for testing content before publishing. Returns scores across 5 dimensions.

    Args:
        text: The text content to score for citability.
        language: Optional ISO language code (e.g. 'en', 'ko') for language-specific analysis.
    """
    payload = {"text": text}
    if language:
        payload["language"] = language
    data = client.post("/api/citability/score", json=payload)

    overall = data.get("overall", 0)
    dims = data.get("dimensions", {})
    improvements = data.get("top_improvements", [])

    lines = [f"## Citability Score: {overall}/100\n"]
    lines.append("| Dimension | Score | Weight |")
    lines.append("|-----------|-------|--------|")

    dim_labels = {
        "answer_block_quality": "Answer Block Quality",
        "self_containment": "Self-Containment",
        "structural_readability": "Structural Readability",
        "statistical_density": "Statistical Density",
        "uniqueness_signals": "Uniqueness Signals",
    }

    for key, label in dim_labels.items():
        d = dims.get(key, {})
        lines.append(f"| {label} | {d.get('score', 0)}/100 | {int(d.get('weight', 0) * 100)}% |")

    if improvements:
        lines.append("\n### Top Improvements")
        for imp in improvements:
            lines.append(f"- {imp}")

    return "\n".join(lines)
