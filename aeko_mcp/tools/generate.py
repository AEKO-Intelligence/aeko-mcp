import re

import httpx

from ..server import mcp, client
from ._annotations import LOCAL_READ_ONLY, READ_ONLY


@mcp.tool(annotations=READ_ONLY)
def aeko_prepare_llms_txt(domain_id: str) -> str:
    """Gather domain data needed to write an llms.txt file.

    Calls AEKO API to collect domain info and store page analyses,
    then returns a structured brief with site map, key pages,
    and product catalog for llms.txt generation.

    Args:
        domain_id: UUID of the domain.

    Returns:
        Structured brief for llms.txt content generation.
    """
    domain = client.get(f"/api/domains/{domain_id}")
    pages_data = client.get("/api/store-pages/analysis", params={"domain_id": domain_id})

    lines = ["# llms.txt Generation Brief", ""]

    # Domain info
    lines.append("## Domain Information")
    lines.append(f"- **URL**: {domain.get('base_url', 'N/A')}")
    lines.append(f"- **Name**: {domain.get('name', domain.get('base_url', 'N/A'))}")

    scope = domain.get("scope") or {}
    if scope:
        lines.append(f"- **Industry**: {scope.get('industry', 'N/A')}")
        lines.append(f"- **Vertical**: {scope.get('vertical', 'N/A')}")
    lines.append("")

    # Infrastructure status
    lines.append("## Infrastructure Status")
    lines.append(f"- robots_blocks_ai: {domain.get('robots_blocks_ai', 'unknown')}")
    lines.append(f"- has_json_ld: {domain.get('has_json_ld', 'unknown')}")
    lines.append(f"- has_sitemap: {domain.get('has_sitemap', 'unknown')}")
    lines.append("")

    # Scanned pages
    pages = pages_data if isinstance(pages_data, list) else pages_data.get("pages", [])
    if pages:
        lines.append(f"## Scanned Pages ({len(pages)} found)")
        lines.append("")
        for p in pages[:50]:
            url = p.get("url", "")
            title = p.get("title", "")
            score = p.get("ai_readiness_score")
            score_str = f" (AI score: {score})" if score is not None else ""
            has_product = p.get("has_product_jsonld")
            has_article = p.get("has_article_jsonld")
            types = []
            if has_product:
                types.append("Product")
            if has_article:
                types.append("Article")
            type_str = f" [{', '.join(types)}]" if types else ""
            lines.append(f"- {title or url}{score_str}{type_str}")
            if url:
                lines.append(f"  URL: {url}")
        lines.append("")

    lines.append("## Instructions for llms.txt")
    lines.append("Use the above data to generate an llms.txt file following the specification at https://llmstxt.org/.")
    lines.append("Include: site description, key product pages, content pages, and any FAQ/support pages found.")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# AI crawlers: name → platform mapping
# ---------------------------------------------------------------------------
AI_CRAWLERS = {
    "GPTBot": "OpenAI",
    "OAI-SearchBot": "OpenAI",
    "ChatGPT-User": "OpenAI",
    "Google-Extended": "Google",
    "GoogleOther": "Google",
    "Applebot-Extended": "Apple",
    "Claude-Web": "Anthropic",
    "ClaudeBot": "Anthropic",
    "Anthropic-AI": "Anthropic",
    "PerplexityBot": "Perplexity",
    "Bytespider": "ByteDance",
    "CCBot": "Common Crawl",
    "Cohere-ai": "Cohere",
}


def _parse_robots_txt(robots_txt: str) -> list[dict]:
    """Parse robots.txt and return per-crawler status for AI crawlers.

    Returns a list of dicts with keys: crawler, platform, status, detail.
    Status is one of: BLOCKED, PARTIALLY_BLOCKED, ALLOWED, NOT_MENTIONED.
    """
    lines_input = robots_txt.strip().split("\n")

    # Build a map of user-agent → list of (directive, path)
    agent_rules: dict[str, list[tuple[str, str]]] = {}
    current_agents: list[str] = []

    for line in lines_input:
        stripped = line.strip()
        # Skip comments and empty lines
        if not stripped or stripped.startswith("#"):
            continue

        if stripped.lower().startswith("user-agent:"):
            agent_name = stripped.split(":", 1)[1].strip()
            # New agent group — if previous line was also user-agent, accumulate
            current_agents.append(agent_name)
        else:
            if not current_agents:
                continue
            directive_match = re.match(r"^(allow|disallow|sitemap|crawl-delay)\s*:\s*(.*)", stripped, re.IGNORECASE)
            if directive_match:
                directive = directive_match.group(1).lower()
                value = directive_match.group(2).strip()
                if directive in ("allow", "disallow"):
                    for agent in current_agents:
                        agent_rules.setdefault(agent, []).append((directive, value))
            # Reset agent accumulation on non-user-agent directive
            if not stripped.lower().startswith("user-agent:"):
                current_agents = []

    # Extract sitemap URLs
    sitemaps = []
    for line in lines_input:
        stripped = line.strip()
        if stripped.lower().startswith("sitemap:"):
            sitemaps.append(stripped.split(":", 1)[1].strip())

    results = []
    for crawler, platform in AI_CRAWLERS.items():
        # Find matching rules: exact match (case-insensitive) or wildcard
        matched_rules = []
        for agent_key, rules in agent_rules.items():
            if agent_key.lower() == crawler.lower() or agent_key == "*":
                matched_rules.extend([(agent_key, d, p) for d, p in rules])

        if not matched_rules:
            results.append({
                "crawler": crawler,
                "platform": platform,
                "status": "NOT_MENTIONED",
                "detail": "Not referenced in robots.txt — allowed by default",
            })
            continue

        # Check for specific crawler rules first, then fall back to wildcard
        specific_rules = [(d, p) for ak, d, p in matched_rules if ak.lower() == crawler.lower()]
        wildcard_rules = [(d, p) for ak, d, p in matched_rules if ak == "*"]
        rules_to_check = specific_rules if specific_rules else wildcard_rules
        source = "specific rule" if specific_rules else "wildcard (*)"

        has_full_block = any(d == "disallow" and p == "/" for d, p in rules_to_check)
        has_partial_block = any(d == "disallow" and p and p != "/" for d, p in rules_to_check)
        has_allow = any(d == "allow" and p for d, p in rules_to_check)
        has_empty_disallow = any(d == "disallow" and not p for d, p in rules_to_check)

        if has_full_block and not has_allow:
            results.append({
                "crawler": crawler,
                "platform": platform,
                "status": "BLOCKED",
                "detail": f"Disallow: / via {source}",
            })
        elif has_full_block and has_allow:
            allowed_paths = [p for d, p in rules_to_check if d == "allow" and p]
            results.append({
                "crawler": crawler,
                "platform": platform,
                "status": "PARTIALLY_BLOCKED",
                "detail": f"Blocked with exceptions: Allow {', '.join(allowed_paths)} (via {source})",
            })
        elif has_partial_block:
            blocked_paths = [p for d, p in rules_to_check if d == "disallow" and p and p != "/"]
            results.append({
                "crawler": crawler,
                "platform": platform,
                "status": "PARTIALLY_BLOCKED",
                "detail": f"Blocked paths: {', '.join(blocked_paths)} (via {source})",
            })
        elif has_empty_disallow or has_allow:
            results.append({
                "crawler": crawler,
                "platform": platform,
                "status": "ALLOWED",
                "detail": f"Explicitly allowed via {source}",
            })
        else:
            results.append({
                "crawler": crawler,
                "platform": platform,
                "status": "NOT_MENTIONED",
                "detail": "Not referenced in robots.txt — allowed by default",
            })

    return results


@mcp.tool(annotations=READ_ONLY)
def aeko_prepare_robots_txt_fix(domain_id: str, current_robots_txt: str) -> str:
    """Analyze a robots.txt for AI crawler blocks and suggest fixes.

    Checks the provided robots.txt content against known AI crawlers
    and returns issues found with recommended fixes. Supports
    case-insensitive matching, partial blocks, and sitemap extraction.

    Args:
        domain_id: UUID of the domain (for context).
        current_robots_txt: The current robots.txt content to analyze.

    Returns:
        Analysis of AI crawler blocks with recommended fixes.
    """
    domain = client.get(f"/api/domains/{domain_id}")
    crawler_results = _parse_robots_txt(current_robots_txt)

    blocked = [r for r in crawler_results if r["status"] == "BLOCKED"]
    partial = [r for r in crawler_results if r["status"] == "PARTIALLY_BLOCKED"]
    allowed = [r for r in crawler_results if r["status"] == "ALLOWED"]
    not_mentioned = [r for r in crawler_results if r["status"] == "NOT_MENTIONED"]

    # Extract sitemaps
    sitemaps = []
    for line in current_robots_txt.strip().split("\n"):
        if line.strip().lower().startswith("sitemap:"):
            sitemaps.append(line.strip().split(":", 1)[1].strip())

    lines = ["# robots.txt AI Crawler Analysis", ""]
    lines.append(f"**Domain**: {domain.get('base_url', 'N/A')}")
    lines.append("")

    # Summary
    total = len(crawler_results)
    lines.append("## Summary")
    lines.append(f"- {len(blocked)} fully blocked | {len(partial)} partially blocked | {len(allowed)} explicitly allowed | {len(not_mentioned)} not mentioned (allowed by default)")
    lines.append("")

    if blocked:
        lines.append(f"## Blocked AI Crawlers ({len(blocked)})")
        for r in blocked:
            lines.append(f"- **{r['crawler']}** ({r['platform']}) — {r['detail']}")
        lines.append("")

    if partial:
        lines.append(f"## Partially Blocked AI Crawlers ({len(partial)})")
        for r in partial:
            lines.append(f"- **{r['crawler']}** ({r['platform']}) — {r['detail']}")
        lines.append("")

    if allowed:
        lines.append(f"## Explicitly Allowed AI Crawlers ({len(allowed)})")
        for r in allowed:
            lines.append(f"- **{r['crawler']}** ({r['platform']}) — {r['detail']}")
        lines.append("")

    if not_mentioned:
        lines.append(f"## Not Mentioned (Allowed by Default) ({len(not_mentioned)})")
        for r in not_mentioned:
            lines.append(f"- **{r['crawler']}** ({r['platform']})")
        lines.append("")

    # Sitemaps
    if sitemaps:
        lines.append("## Sitemaps Found")
        for s in sitemaps:
            lines.append(f"- {s}")
        lines.append("")
    else:
        lines.append("## Sitemaps")
        lines.append("- No Sitemap directive found in robots.txt. Consider adding one for better crawl discovery.")
        lines.append("")

    # Recommendations
    needs_fix = blocked + partial
    if needs_fix:
        lines.append("## Recommended Fix")
        lines.append("Add the following rules to explicitly allow key AI crawlers:")
        lines.append("")
        lines.append("```")
        lines.append("# Allow AI crawlers for better AI engine visibility")
        for r in needs_fix:
            lines.append(f"User-agent: {r['crawler']}")
            lines.append("Allow: /")
            lines.append("")
        lines.append("```")
    else:
        lines.append("## Status: All Clear")
        lines.append("No AI crawlers are blocked. Your site is accessible to all major AI platforms.")

    return "\n".join(lines)


@mcp.tool(annotations=LOCAL_READ_ONLY)
def aeko_validate_llms_txt(url: str) -> str:
    """Internal helper for `/aeko-fix-technical` and `/aeko-fix-store-level`; not intended for standalone use.

    Validates an existing llms.txt file for format compliance and completeness.
    Fetches the llms.txt from the given URL (or appends /llms.txt if needed)
    and checks for format compliance per the llmstxt.org specification.

    Args:
        url: URL of the llms.txt file, or the site's base URL.

    Returns:
        Validation report with issues found and suggestions.
    """
    # Normalize URL
    target_url = url.rstrip("/")
    if not target_url.endswith("/llms.txt"):
        target_url = target_url + "/llms.txt"

    # Also check for llms-full.txt
    full_url = target_url.replace("/llms.txt", "/llms-full.txt")

    lines = ["# llms.txt Validation Report", ""]
    lines.append(f"**URL**: {target_url}")
    lines.append("")

    # Fetch llms.txt
    try:
        resp = httpx.get(target_url, timeout=15.0, follow_redirects=True)
    except httpx.ConnectError:
        return f"Could not connect to {target_url}. Check the URL and try again."
    except httpx.TimeoutException:
        return f"Request timed out for {target_url}."

    if resp.status_code == 404:
        lines.append("## Result: NOT FOUND")
        lines.append("")
        lines.append("No llms.txt file exists at this URL.")
        lines.append("")
        lines.append("### What is llms.txt?")
        lines.append("A file that helps AI engines understand your site structure.")
        lines.append("See https://llmstxt.org/ for the specification.")
        lines.append("")
        lines.append("### Recommendation")
        lines.append("Use the `aeko_prepare_llms_txt` tool to generate one based on your AEKO domain data.")
        return "\n".join(lines)

    if resp.status_code != 200:
        lines.append(f"## Result: HTTP {resp.status_code}")
        lines.append(f"Server returned status {resp.status_code} for llms.txt.")
        return "\n".join(lines)

    content = resp.text
    content_lines = content.strip().split("\n")

    # Validation checks
    issues = []
    suggestions = []
    stats = {}

    # 1. Title (# heading)
    has_title = any(line.strip().startswith("# ") and not line.strip().startswith("## ") for line in content_lines)
    if has_title:
        title_line = next(l for l in content_lines if l.strip().startswith("# ") and not l.strip().startswith("## "))
        stats["title"] = title_line.strip()[2:]
    else:
        issues.append("Missing title — file should start with a `# Title` heading")

    # 2. Description (> blockquote)
    has_description = any(line.strip().startswith("> ") for line in content_lines)
    if not has_description:
        issues.append("Missing description — add a `> Description text` blockquote after the title")

    # 3. Sections (## headings)
    sections = [line.strip() for line in content_lines if line.strip().startswith("## ")]
    stats["section_count"] = len(sections)
    if not sections:
        issues.append("No sections found — organize content with `## Section Name` headings")
    elif len(sections) < 2:
        suggestions.append("Consider adding more sections (e.g., Products, Resources, Support)")

    # 4. Links ([text](url))
    link_pattern = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
    all_links = link_pattern.findall(content)
    stats["link_count"] = len(all_links)
    if not all_links:
        issues.append("No links found — add page links in `- [Page Title](url)` format")
    elif len(all_links) < 5:
        suggestions.append(f"Only {len(all_links)} link(s) found — consider adding more key pages")

    # 5. Check for llms-full.txt reference
    has_full_ref = "llms-full.txt" in content
    stats["references_llms_full"] = has_full_ref

    # 6. Check for llms-full.txt existence
    try:
        full_resp = httpx.get(full_url, timeout=10.0, follow_redirects=True)
        has_full_file = full_resp.status_code == 200
    except Exception:
        has_full_file = False
    stats["llms_full_exists"] = has_full_file

    if has_full_file and not has_full_ref:
        suggestions.append("llms-full.txt exists but isn't referenced in llms.txt — consider linking to it")
    if not has_full_file:
        suggestions.append("No llms-full.txt found — consider creating an extended version with detailed page content")

    # 7. Content length check
    char_count = len(content)
    stats["char_count"] = char_count
    if char_count < 200:
        suggestions.append(f"File is quite short ({char_count} chars) — consider adding more detail")
    elif char_count > 50000:
        suggestions.append(f"File is very large ({char_count} chars) — consider moving detail to llms-full.txt")

    # Build report
    lines.append("## Validation Results")
    lines.append("")

    passed = 4 - len(issues)
    total = 4
    lines.append(f"**Score**: {passed}/{total} required checks passed")
    lines.append("")

    lines.append("| Check | Status |")
    lines.append("|-------|--------|")
    lines.append(f"| Title (`# `) | {'PASS' if has_title else 'FAIL'} |")
    lines.append(f"| Description (`> `) | {'PASS' if has_description else 'FAIL'} |")
    lines.append(f"| Sections (`## `) | {'PASS' if sections else 'FAIL'} — {len(sections)} found |")
    lines.append(f"| Links (`[text](url)`) | {'PASS' if all_links else 'FAIL'} — {len(all_links)} found |")
    lines.append(f"| llms-full.txt exists | {'YES' if has_full_file else 'NO'} |")
    lines.append("")

    if sections:
        lines.append("### Sections Found")
        for s in sections:
            lines.append(f"- {s}")
        lines.append("")

    if issues:
        lines.append("## Issues (Must Fix)")
        for issue in issues:
            lines.append(f"- {issue}")
        lines.append("")

    if suggestions:
        lines.append("## Suggestions (Recommended)")
        for s in suggestions:
            lines.append(f"- {s}")
        lines.append("")

    if not issues:
        lines.append("## Status: Valid")
        lines.append("The llms.txt file passes all required format checks.")

    return "\n".join(lines)


@mcp.tool(annotations=READ_ONLY)
def aeko_prepare_json_ld(domain_id: str, schema_type: str, page_url: str = "") -> str:
    """Gather data needed to generate JSON-LD structured data.

    Collects domain info, page analysis, and product data to prepare
    a brief for generating schema.org JSON-LD markup.

    Args:
        domain_id: UUID of the domain.
        schema_type: Type of schema to generate: Product, FAQ, Article, Organization, or WebSite.
        page_url: Optional specific page URL to generate JSON-LD for.

    Returns:
        Structured brief with all available data fields for JSON-LD generation.
    """
    valid_types = ["Product", "FAQ", "Article", "Organization", "WebSite", "HowTo"]
    if schema_type not in valid_types:
        return f"Invalid schema_type: {schema_type}. Must be one of: {', '.join(valid_types)}"

    domain = client.get(f"/api/domains/{domain_id}")
    lines = [f"# JSON-LD Generation Brief: {schema_type}", ""]

    lines.append("## Domain Context")
    lines.append(f"- **URL**: {domain.get('base_url', 'N/A')}")
    lines.append(f"- **Name**: {domain.get('name', domain.get('base_url', 'N/A'))}")
    scope = domain.get("scope") or {}
    if scope:
        lines.append(f"- **Industry**: {scope.get('industry', 'N/A')}")
    lines.append("")

    # Get page data if URL provided
    if page_url:
        try:
            pages_data = client.get("/api/store-pages/analysis", params={"domain_id": domain_id})
            pages = pages_data if isinstance(pages_data, list) else pages_data.get("pages", [])
            matching = [p for p in pages if p.get("url") == page_url]
            if matching:
                page = matching[0]
                lines.append("## Page Data")
                lines.append(f"- **URL**: {page.get('url')}")
                lines.append(f"- **Title**: {page.get('title', 'N/A')}")
                lines.append(f"- **AI Readiness Score**: {page.get('ai_readiness_score', 'N/A')}")
                analysis = page.get("source_analysis") or {}
                if analysis:
                    lines.append(f"- **Existing JSON-LD types**: {analysis.get('json_ld_types', 'none')}")
                    lines.append(f"- **Word count**: {analysis.get('word_count', 'N/A')}")
                lines.append("")
        except Exception:
            pass

    # Schema-specific guidance
    lines.append(f"## {schema_type} Schema Fields")
    lines.append("")

    if schema_type == "Product":
        lines.append("### Required")
        lines.append("- `@type`: Product")
        lines.append("- `name`: Product name")
        lines.append("- `description`: 50-300 chars, keyword-rich but natural")
        lines.append("- `offers`: price, priceCurrency, availability (full schema.org URL)")
        lines.append("")
        lines.append("### Recommended")
        lines.append("- `brand`: Brand entity with `@type: Brand`")
        lines.append("- `sku` / `gtin13` / `mpn`: Product identifiers")
        lines.append("- `image`: Absolute URLs, multiple angles if available")
        lines.append("- `aggregateRating`: Only if real review data exists — never fabricate")
        lines.append("- `review`: Individual product reviews")
        lines.append("")
        lines.append("### E-Commerce Fields (High Impact for AI Visibility)")
        lines.append("- `shippingDetails`: Use `DefinedRegion` for international shipping zones")
        lines.append("- `hasMerchantReturnPolicy`: Return/refund policy structured data")
        lines.append("- `weight`: Product weight with `QuantitativeValue`")
        lines.append("- `material`: Product material(s)")
        lines.append("- `color`: Product color(s)")
        lines.append("- `size`: Product size using `SizeSpecification`")
        lines.append("- `additionalProperty`: Product-specific attributes (e.g., voltage, capacity)")
        lines.append("")
        lines.append("### AI Voice & Citation")
        lines.append("- `speakable`: Mark key sections for voice assistant extraction")
        lines.append("  ```json")
        lines.append('  "speakable": {')
        lines.append('    "@type": "SpeakableSpecification",')
        lines.append('    "cssSelector": [".product-description", ".product-specs"]')
        lines.append("  }")
        lines.append("  ```")
        lines.append("- `sameAs`: Link to authoritative brand pages (priority order):")
        lines.append("  1. Wikipedia article")
        lines.append("  2. Wikidata entity")
        lines.append("  3. LinkedIn company page")
        lines.append("  4. YouTube channel")
        lines.append("  5. X/Twitter profile")
    elif schema_type == "FAQ":
        lines.append("Structure: FAQPage with mainEntity array of Question items")
        lines.append("Each Question needs: name (question text), acceptedAnswer with text")
        lines.append("Tip: Include 5-10 real customer questions about the product")
    elif schema_type == "Article":
        lines.append("Required: @type (Article/BlogPosting), headline, datePublished, author")
        lines.append("Recommended: image, dateModified, publisher, description, mainEntityOfPage")
        lines.append("")
        lines.append("### AI Voice & Citation")
        lines.append("- `speakable`: Mark the summary/intro paragraph for voice assistants")
    elif schema_type == "Organization":
        lines.append("Required: @type, name, url")
        lines.append("Recommended: logo, sameAs (social links), contactPoint, description")
        lines.append("")
        lines.append("### sameAs Priority (for AI Entity Recognition)")
        lines.append("Include in this priority order (most impactful first):")
        lines.append("1. Wikipedia article URL")
        lines.append("2. Wikidata entity URL (e.g., https://www.wikidata.org/wiki/Q...)")
        lines.append("3. LinkedIn company page")
        lines.append("4. YouTube channel")
        lines.append("5. X/Twitter profile")
        lines.append("6. Facebook page")
    elif schema_type == "WebSite":
        lines.append("Required: @type, name, url")
        lines.append("Recommended: potentialAction (SearchAction), description, publisher")
    elif schema_type == "HowTo":
        lines.append("Required: @type, name, step (array of HowToStep)")
        lines.append("Each HowToStep needs: @type, name, text, optionally image and url")
        lines.append("")
        lines.append("### Recommended")
        lines.append("- `description`: Overview of what this how-to achieves")
        lines.append("- `totalTime`: ISO 8601 duration (e.g., PT30M)")
        lines.append("- `estimatedCost`: MonetaryAmount if applicable")
        lines.append("- `supply`: HowToSupply items needed")
        lines.append("- `tool`: HowToTool items needed")
        lines.append("- `image`: Main image for the how-to")
        lines.append("")
        lines.append("### AI Visibility Tips")
        lines.append("- Use clear, actionable step names (verb-first)")
        lines.append("- Include 5-15 steps for optimal AI extraction")
        lines.append("- Add `video` property if a tutorial video exists")

    lines.append("")
    lines.append("## Instructions")
    lines.append(f"Generate a complete, valid JSON-LD block for {schema_type} schema using the data above.")
    lines.append("Follow schema.org specifications. Include all available fields from the page data.")

    return "\n".join(lines)


@mcp.tool(annotations=LOCAL_READ_ONLY)
def aeko_check_brand_entity(brand_name: str, brand_name_en: str = "") -> str:
    """Check if a brand has Wikipedia/Wikidata entity recognition.

    Searches Wikipedia and Wikidata APIs to determine if a brand
    is recognized as a known entity — a key factor in AI engine
    recommendations.

    Args:
        brand_name: Brand name (any language).
        brand_name_en: Optional English variant of the brand name.

    Returns:
        Entity recognition report with findings and recommendations.
    """
    names_to_check = [brand_name]
    if brand_name_en and brand_name_en.lower() != brand_name.lower():
        names_to_check.append(brand_name_en)

    lines = ["# Brand Entity Recognition Report", ""]
    lines.append(f"**Brand**: {brand_name}")
    if brand_name_en and brand_name_en != brand_name:
        lines.append(f"**English name**: {brand_name_en}")
    lines.append("")

    wikipedia_found = False
    wikipedia_url = None
    wikipedia_extract = None
    wikidata_found = False
    wikidata_id = None
    wikidata_description = None

    for name in names_to_check:
        # --- Wikipedia Search ---
        if not wikipedia_found:
            try:
                wp_resp = httpx.get(
                    "https://en.wikipedia.org/api/rest_v1/page/summary/" + name.replace(" ", "_"),
                    timeout=10.0,
                    follow_redirects=True,
                )
                if wp_resp.status_code == 200:
                    wp_data = wp_resp.json()
                    if wp_data.get("type") != "disambiguation":
                        wikipedia_found = True
                        wikipedia_url = wp_data.get("content_urls", {}).get("desktop", {}).get("page")
                        wikipedia_extract = wp_data.get("extract", "")[:300]
            except Exception:
                pass

        # Try search API as fallback
        if not wikipedia_found:
            try:
                search_resp = httpx.get(
                    "https://en.wikipedia.org/w/api.php",
                    params={"action": "query", "list": "search", "srsearch": name, "format": "json", "srlimit": 3},
                    timeout=10.0,
                )
                if search_resp.status_code == 200:
                    results = search_resp.json().get("query", {}).get("search", [])
                    if results and name.lower() in results[0].get("title", "").lower():
                        wikipedia_found = True
                        title = results[0]["title"]
                        wikipedia_url = f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"
                        wikipedia_extract = re.sub(r"<[^>]+>", "", results[0].get("snippet", ""))
            except Exception:
                pass

        # --- Wikidata Search ---
        if not wikidata_found:
            try:
                wd_resp = httpx.get(
                    "https://www.wikidata.org/w/api.php",
                    params={"action": "wbsearchentities", "search": name, "language": "en", "format": "json", "limit": 3},
                    timeout=10.0,
                )
                if wd_resp.status_code == 200:
                    wd_results = wd_resp.json().get("search", [])
                    for wd_item in wd_results:
                        label = wd_item.get("label", "").lower()
                        if name.lower() in label or label in name.lower():
                            wikidata_found = True
                            wikidata_id = wd_item.get("id")
                            wikidata_description = wd_item.get("description", "")
                            break
            except Exception:
                pass

    # --- Report ---
    entity_score = 0

    lines.append("## Wikipedia")
    if wikipedia_found:
        entity_score += 50
        lines.append(f"- **Status**: FOUND")
        if wikipedia_url:
            lines.append(f"- **URL**: {wikipedia_url}")
        if wikipedia_extract:
            lines.append(f"- **Extract**: {wikipedia_extract}")
    else:
        lines.append("- **Status**: NOT FOUND")
        lines.append("- No dedicated Wikipedia article found for this brand.")
    lines.append("")

    lines.append("## Wikidata")
    if wikidata_found:
        entity_score += 50
        lines.append(f"- **Status**: FOUND")
        lines.append(f"- **ID**: {wikidata_id}")
        lines.append(f"- **URL**: https://www.wikidata.org/wiki/{wikidata_id}")
        if wikidata_description:
            lines.append(f"- **Description**: {wikidata_description}")
    else:
        lines.append("- **Status**: NOT FOUND")
        lines.append("- No Wikidata entity found for this brand.")
    lines.append("")

    # Overall assessment
    lines.append("## Entity Recognition Score")
    lines.append(f"**{entity_score}/100**")
    lines.append("")

    if entity_score == 100:
        lines.append("**Strong entity recognition.** This brand is well-known to knowledge bases that AI engines rely on.")
        lines.append("Use these URLs in your `sameAs` JSON-LD property:")
        lines.append(f"1. {wikipedia_url}")
        lines.append(f"2. https://www.wikidata.org/wiki/{wikidata_id}")
    elif entity_score == 50:
        found_on = "Wikipedia" if wikipedia_found else "Wikidata"
        lines.append(f"**Partial recognition.** Found on {found_on} but not both.")
        if wikipedia_found:
            lines.append(f"Add to `sameAs`: {wikipedia_url}")
        if wikidata_found:
            lines.append(f"Add to `sameAs`: https://www.wikidata.org/wiki/{wikidata_id}")
    else:
        lines.append("**No entity recognition.** This brand is not yet in major knowledge bases.")
        lines.append("")
        lines.append("### How to Build Entity Recognition")
        lines.append("1. **Press coverage** — get featured in notable publications (needed for Wikipedia notability)")
        lines.append("2. **Wikidata entry** — create a Wikidata item with proper claims (industry, headquarters, founding date)")
        lines.append("3. **Consistent branding** — use exact same brand name across all platforms")
        lines.append("4. **Knowledge panel** — claim your Google Knowledge Panel if available")
        lines.append("5. **sameAs links** — link social profiles in Organization JSON-LD even without Wikipedia")

    return "\n".join(lines)
