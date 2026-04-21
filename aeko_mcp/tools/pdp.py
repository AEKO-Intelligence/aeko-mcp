from html.parser import HTMLParser
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import urljoin

import httpx
from mcp.server.fastmcp import Image
from ..server import client, mcp
from ._annotations import READ_ONLY, WRITE_ONCE


VALID_STRATEGIES = {"append_below_images", "rewrite_from_scratch"}
VALID_RESEARCH_DEPTHS = {
    "product_page_only",
    "product_page_web",
    "product_page_web_competitor",
}
RESEARCH_DEPTH_ALIASES = {
    "ocr_only": "product_page_only",
    "ocr_web": "product_page_web",
    "ocr_web_competitor": "product_page_web_competitor",
}
VALID_DEPLOYMENT_MODES = {"manual_copy", "write_api"}

PAGE_FETCH_TIMEOUT = 20.0
PAGE_FETCH_HEADERS = {
    "User-Agent": "AEKO-MCP/0.2 (+https://github.com/AEKO-Intelligence/aeko-mcp)",
}


class _ProductPageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self.description = ""
        self.headings: list[tuple[str, str]] = []
        self.images: list[dict[str, str]] = []
        self.meta_images: list[str] = []
        self.jsonld_blocks: list[str] = []
        self._in_title = False
        self._skip_depth = 0
        self._in_jsonld = False
        self._current_heading_tag = ""
        self._current_heading_parts: list[str] = []
        self._title_parts: list[str] = []
        self._jsonld_parts: list[str] = []

    @staticmethod
    def _first_src_from_srcset(value: str) -> str:
        first = value.split(",")[0].strip()
        if not first:
            return ""
        return first.split()[0].strip()

    def handle_starttag(self, tag: str, attrs):
        tag_lower = tag.lower()
        attrs_dict = {key.lower(): value or "" for key, value in attrs}

        if tag_lower == "script" and attrs_dict.get("type", "").lower() == "application/ld+json":
            self._in_jsonld = True
            self._jsonld_parts = []
            return

        if tag_lower in {"script", "style", "noscript"}:
            self._skip_depth += 1
            return

        if tag_lower == "title":
            self._in_title = True
            return

        if tag_lower in {"h1", "h2", "h3"}:
            self._current_heading_tag = tag_lower
            self._current_heading_parts = []
            return

        if tag_lower == "meta":
            name = attrs_dict.get("name", "").lower()
            prop = attrs_dict.get("property", "").lower()
            content = attrs_dict.get("content", "").strip()
            if content and not self.description and (
                name == "description" or prop == "og:description"
            ):
                self.description = content
            if content and prop in {"og:image", "twitter:image"}:
                self.meta_images.append(content)
            return

        if tag_lower == "img":
            src = (
                attrs_dict.get("src")
                or attrs_dict.get("data-src")
                or attrs_dict.get("data-original")
                or attrs_dict.get("data-lazy-src")
                or attrs_dict.get("data-image")
                or self._first_src_from_srcset(attrs_dict.get("srcset", ""))
                or self._first_src_from_srcset(attrs_dict.get("data-srcset", ""))
                or ""
            ).strip()
            if not src:
                return
            alt = attrs_dict.get("alt", "").strip()
            width = attrs_dict.get("width", "").strip()
            height = attrs_dict.get("height", "").strip()
            self.images.append(
                {
                    "src": src,
                    "alt": alt,
                    "width": width,
                    "height": height,
                }
            )

    def handle_endtag(self, tag: str):
        tag_lower = tag.lower()
        if self._in_jsonld and tag_lower == "script":
            payload = "".join(self._jsonld_parts).strip()
            if payload:
                self.jsonld_blocks.append(payload)
            self._jsonld_parts = []
            self._in_jsonld = False
            return

        if tag_lower in {"script", "style", "noscript"}:
            self._skip_depth = max(0, self._skip_depth - 1)
            return

        if tag_lower == "title":
            self._in_title = False
            title = " ".join(part for part in self._title_parts if part).strip()
            if title and not self.title:
                self.title = title
            return

        if self._current_heading_tag and tag_lower == self._current_heading_tag:
            heading = " ".join(part for part in self._current_heading_parts if part).strip()
            if heading:
                self.headings.append((self._current_heading_tag, heading))
            self._current_heading_tag = ""
            self._current_heading_parts = []

    def handle_data(self, data: str):
        if self._skip_depth > 0:
            return
        text = data.strip()
        if not text:
            return
        if self._in_title:
            self._title_parts.append(text)
        if self._in_jsonld:
            self._jsonld_parts.append(data)
        if self._current_heading_tag:
            self._current_heading_parts.append(text)


def _fetch_product_page(url: str) -> tuple[str | None, str | None]:
    try:
        resp = httpx.get(
            url,
            headers=PAGE_FETCH_HEADERS,
            timeout=PAGE_FETCH_TIMEOUT,
            follow_redirects=True,
        )
        resp.raise_for_status()
        return resp.text, None
    except httpx.HTTPStatusError as e:
        return None, f"HTTP {e.response.status_code} when fetching {url}"
    except httpx.ConnectError:
        return None, f"Could not connect to {url}"
    except httpx.TimeoutException:
        return None, f"Timed out while fetching {url}"
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


def _trim_text(text: str, limit: int = 220) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _dedupe_images(images: list[dict[str, str]], page_url: str, limit: int = 12) -> list[dict[str, str]]:
    deduped: list[dict[str, str]] = []
    seen: set[str] = set()
    for image in images:
        src = image.get("src", "").strip()
        if not src:
            continue
        full_src = urljoin(page_url, src)
        if full_src in seen:
            continue
        seen.add(full_src)
        deduped.append(
            {
                "src": full_src,
                "alt": image.get("alt", "").strip(),
                "width": image.get("width", "").strip(),
                "height": image.get("height", "").strip(),
            }
        )
        if len(deduped) >= limit:
            break
    return deduped


def _merge_page_images(
    page_url: str,
    parsed_images: list[dict[str, str]],
    meta_images: list[str],
    fallback_image_url: str | None = None,
    limit: int = 12,
) -> list[dict[str, str]]:
    merged = list(parsed_images)
    for meta_url in meta_images:
        merged.append({"src": meta_url, "alt": "", "width": "", "height": ""})
    if fallback_image_url:
        merged.append({"src": fallback_image_url, "alt": "", "width": "", "height": ""})
    return _dedupe_images(merged, page_url, limit=limit)


def _safe_get(path: str, params: dict | None = None) -> tuple[dict | list | None, str | None]:
    try:
        return client.get(path, params=params), None
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


def _safe_post(path: str, payload: dict) -> tuple[dict | None, str | None]:
    try:
        return client.post(path, json=payload), None
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


def _canonical_url(url: str | None) -> str:
    return (url or "").split("?")[0].split("#")[0]


def _slugify(value: str) -> str:
    chars: list[str] = []
    last_dash = False
    for char in value.lower():
        if char.isalnum():
            chars.append(char)
            last_dash = False
        elif not last_dash:
            chars.append("-")
            last_dash = True
    return "".join(chars).strip("-") or "product"


def _description_length(text: str | None) -> int:
    return len((text or "").strip())


def _render_strategy(strategy: str) -> list[str]:
    if strategy == "append_below_images":
        return [
            "- Keep the current image-led top section intact.",
            "- Add structured HTML below the image stack so the merchant can paste it under existing visuals.",
            "- Prioritize a concise overview, spec/features block, trust or proof section, and FAQ.",
        ]
    return [
        "- Rewrite the full product detail body from scratch.",
        "- Build a clearer H2/H3 spine than the current page and replace weak or image-only copy.",
        "- Keep the output Cafe24-safe HTML with no framework-specific markup.",
    ]


def _render_research_depth(research_depth: str) -> list[str]:
    if research_depth == "product_page_only":
        return [
            "- Use only facts already present in AEKO/store data plus anything extracted from the product page and its PDP images.",
            "- Do not add unsupported market claims, certifications, or policy promises.",
        ]
    if research_depth == "product_page_web":
        return [
            "- Start from AEKO/store data and facts extracted from the product page and its PDP images.",
            "- Add only web facts from official brand or manufacturer sources unless the user explicitly asks for broader research.",
        ]
    return [
        "- Start from product-page extraction and official web facts.",
        "- Add a competitor-input pass before drafting so the final PDP emphasizes defensible differentiators.",
        "- Use competitor pages for structure and positioning only; do not copy wording.",
    ]


def _normalize_research_depth(research_depth: str) -> str:
    value = (research_depth or "").strip()
    return RESEARCH_DEPTH_ALIASES.get(value, value)


def _platform_publish_instructions(platform: str, output_path: str | None = None) -> list[str]:
    if platform == "cafe24":
        lines = [
            "1. Open Cafe24 Admin → 상품관리 → 상품수정.",
            "2. Scroll to 상세설명 and paste the generated HTML below the existing image section.",
            "3. If you generated JSON-LD separately, place it in the product detail HTML or your SEO/head injection area.",
        ]
    elif platform == "shopify":
        lines = [
            "1. Open Shopify Admin → Products → the target product.",
            "2. Switch the description editor to HTML mode and paste the generated HTML.",
            "3. Add JSON-LD via the product description block only if your theme supports it; otherwise inject it in the theme/head layer.",
        ]
    else:
        lines = [
            "1. Open your commerce admin and edit the target product.",
            "2. Paste the generated HTML into the product detail / description editor.",
            "3. Place any JSON-LD in the platform's supported head or rich-description area.",
        ]
    if output_path:
        lines.append(f"4. The HTML was also saved locally at `{output_path}`.")
    return lines


def _fetch_integrations() -> tuple[list[dict], str | None]:
    data, err = _safe_get("/api/store-integrations")
    if err:
        return [], err
    return data if isinstance(data, list) else [], None


def _fetch_product(product_id: str) -> tuple[dict | None, str | None]:
    data, err = _safe_get(f"/api/store-products/{product_id}")
    if err:
        return None, err
    return data if isinstance(data, dict) else None, None


def _resolve_product_context(product_id: str) -> tuple[dict | None, str | None]:
    product, err = _fetch_product(product_id)
    if err:
        return None, err
    if not product:
        return None, f"Product `{product_id}` not found."

    integrations, integrations_err = _fetch_integrations()
    if integrations_err:
        return None, integrations_err

    integration = next(
        (item for item in integrations if item.get("id") == product.get("store_integration_id")),
        None,
    )
    if integration is None:
        return None, "Could not resolve the product's connected store integration."

    domain_id = integration.get("domain_id")
    domain = None
    if domain_id:
        domain_data, domain_err = _safe_get(f"/api/domains/{domain_id}")
        if domain_err is None and isinstance(domain_data, dict):
            domain = domain_data

    page_analysis = None
    if domain_id and product.get("product_url"):
        analysis_data, analysis_err = _safe_get(
            "/api/store-pages/analysis",
            params={"domain_id": domain_id, "url": product["product_url"]},
        )
        if analysis_err is None:
            if isinstance(analysis_data, list):
                page_analysis = analysis_data[0] if analysis_data else None
            elif isinstance(analysis_data, dict):
                pages = analysis_data.get("pages")
                if isinstance(pages, list) and pages:
                    page_analysis = pages[0]
                else:
                    page_analysis = analysis_data

    ranked_product = None
    if domain_id:
        ranked_data, ranked_err = _safe_get(
            "/api/store-products",
            params={
                "domain_id": domain_id,
                "include_citability": True,
                "sort": "score_asc",
                "limit": 500,
                "offset": 0,
            },
        )
        if ranked_err is None and isinstance(ranked_data, dict):
            items = ranked_data.get("items") or []
            ranked_product = next((item for item in items if item.get("id") == product_id), None)

    suggestion = None
    if domain_id:
        suggestions_data, suggestions_err = _safe_get(
            "/api/suggestions/v2",
            params={"domain_id": domain_id, "category": "pdp_update"},
        )
        if suggestions_err is None and isinstance(suggestions_data, dict):
            buckets = suggestions_data.get("categories") or {}
            suggestions = buckets.get("pdp_update") or suggestions_data.get("suggestions") or []
            target_url = _canonical_url(product.get("product_url"))
            for item in suggestions:
                brief = item.get("brief") or {}
                if _canonical_url(brief.get("target_url")) == target_url:
                    suggestion = item
                    break

    return {
        "product": product,
        "integration": integration,
        "domain": domain,
        "page_analysis": page_analysis,
        "ranked_product": ranked_product,
        "suggestion": suggestion,
    }, None


def _inspect_page(url: str, fallback_image_url: str | None = None) -> tuple[dict | None, str | None]:
    html, err = _fetch_product_page(url)
    if err:
        return None, err
    if html is None:
        return None, f"Could not fetch {url}"

    parser = _ProductPageParser()
    parser.feed(html)
    images = _merge_page_images(
        url,
        parser.images,
        parser.meta_images,
        fallback_image_url=fallback_image_url,
    )
    headings = parser.headings[:10]

    return {
        "url": url,
        "title": parser.title,
        "description": parser.description,
        "headings": headings,
        "images": images,
        "html_length": len(html),
        "jsonld_count": len(parser.jsonld_blocks),
    }, None


def _download_image_to_temp(image_url: str) -> tuple[str | None, str | None]:
    try:
        resp = httpx.get(
            image_url,
            headers=PAGE_FETCH_HEADERS,
            timeout=PAGE_FETCH_TIMEOUT,
            follow_redirects=True,
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        return None, f"HTTP {e.response.status_code} when fetching image {image_url}"
    except httpx.ConnectError:
        return None, f"Could not connect to image {image_url}"
    except httpx.TimeoutException:
        return None, f"Timed out while fetching image {image_url}"
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"

    suffix = Path(image_url.split("?")[0]).suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        suffix = ".jpg"

    with NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(resp.content)
        return tmp.name, None


def _candidate_reason_lines(item: dict) -> list[str]:
    lines: list[str] = []
    status = item.get("ai_readiness_status")
    if status == "needs_fixes":
        lines.append("Needs fixes based on AEKO AI-readiness analysis.")
    elif status == "analyzing":
        lines.append("Still analyzing; use this if you want to work ahead of the next AEKO pass.")
    elif status == "ready":
        lines.append("Marked ready by AEKO, but still available if you want a manual rewrite.")

    description_len = _description_length(item.get("description"))
    if description_len < 120:
        lines.append("Current PDP copy is very thin; likely image-led or under-explained.")

    counts = item.get("pdp_suggestion_counts") or {}
    total_counts = sum(int(v or 0) for v in counts.values())
    if total_counts:
        breakdown = ", ".join(f"{key}:{value}" for key, value in counts.items() if value)
        lines.append(f"Open PDP suggestions exist in AEKO ({breakdown}).")

    if not lines:
        lines.append("Candidate product synced from the connected store.")
    return lines


@mcp.tool(annotations=READ_ONLY)
def aeko_list_pdp_candidates(
    domain_id: str = "",
    store_integration_id: str = "",
    limit: int = 20,
    include_ready: bool = False,
) -> str:
    """List synced products that are strong candidates for PDP optimization.

    Uses AEKO's coarse AI-readiness state and any active `pdp_update`
    suggestions to surface weak, image-led, or still-analyzing product pages.

    Args:
        domain_id: Optional domain UUID. Use this to focus on one store/domain.
        store_integration_id: Optional store integration UUID if you already know the store.
        limit: Maximum number of products to return (1-100 recommended).
        include_ready: Include `ready` products as manual rewrite candidates.
    """
    params = {
        "include_citability": True,
        "sort": "score_asc",
        "limit": max(1, min(limit, 100)),
        "offset": 0,
    }
    if domain_id:
        params["domain_id"] = domain_id
    if store_integration_id:
        params["store_integration_id"] = store_integration_id

    data, err = _safe_get("/api/store-products", params=params)
    if err:
        return f"# PDP candidates unavailable\n\n```\n{err}\n```"
    if not isinstance(data, dict):
        return "# PDP candidates unavailable\n\nThe backend returned an unexpected response."

    items = data.get("items") or []
    if not include_ready:
        items = [item for item in items if item.get("ai_readiness_status") != "ready"]

    if not items:
        return (
            "# No weak PDP candidates found\n\n"
            "AEKO does not currently show any non-ready products for this filter. "
            "You can retry with `include_ready=true` if you still want to rewrite a page manually."
        )

    summary = data.get("summary") or {}
    lines = ["# PDP optimization candidates", ""]
    if domain_id:
        lines.append(f"- **Domain ID**: `{domain_id}`")
    if store_integration_id:
        lines.append(f"- **Store integration**: `{store_integration_id}`")
    lines.append(
        f"- **Portfolio summary**: total={summary.get('total', '?')}, "
        f"needs_fixes={summary.get('needs_fixes', '?')}, analyzing={summary.get('analyzing', '?')}, ready={summary.get('ready', '?')}"
    )
    lines.append("")

    for index, item in enumerate(items, 1):
        lines.append(f"## {index}. {item.get('title') or 'Untitled product'}")
        lines.append(f"- **Product ID**: `{item.get('id', '?')}`")
        lines.append(f"- **External product ID**: `{item.get('external_product_id', '?')}`")
        lines.append(f"- **URL**: {item.get('product_url', 'N/A')}")
        lines.append(f"- **AI readiness**: {item.get('ai_readiness_status', 'unknown')}")
        if item.get("image_url"):
            lines.append(f"- **Image**: {item['image_url']}")
        for reason in _candidate_reason_lines(item):
            lines.append(f"- **Why now**: {reason}")
        lines.append("")

    lines.append("Next step: pick a `Product ID` and call `aeko_get_pdp_optimization_brief(product_id=...)`.")
    return "\n".join(lines)


@mcp.tool(annotations=READ_ONLY)
def aeko_inspect_product_page(product_id: str) -> str:
    """Fetch a synced product page and extract page structure + PDP image URLs.

    This makes the `product_page_*` workflow concrete: it reads the live
    product URL, surfaces page headings, and lists the primary image assets
    that can be reviewed before drafting.

    Args:
        product_id: AEKO store-product UUID.
    """
    ctx, err = _resolve_product_context(product_id)
    if err:
        return f"# Product page inspection unavailable\n\n```\n{err}\n```"
    if ctx is None:
        return "# Product page inspection unavailable"

    product = ctx["product"]
    url = product.get("product_url") or ""
    if not url:
        return "# Product page inspection unavailable\n\nThis product does not have a product URL."

    page, page_err = _inspect_page(url, fallback_image_url=product.get("image_url"))
    if page_err:
        return f"# Product page inspection unavailable\n\n```\n{page_err}\n```"
    if page is None:
        return "# Product page inspection unavailable"

    lines = [f"# Product page inspection: {product.get('title') or 'Untitled product'}", ""]
    lines.append(f"- **Product ID**: `{product.get('id', '?')}`")
    lines.append(f"- **URL**: {url}")
    if page.get("title"):
        lines.append(f"- **HTML title**: {_trim_text(page['title'])}")
    if page.get("description"):
        lines.append(f"- **Meta description**: {_trim_text(page['description'])}")
    lines.append(f"- **Fetched HTML size**: {page.get('html_length', 0)} chars")
    lines.append(f"- **JSON-LD blocks found**: {page.get('jsonld_count', 0)}")
    lines.append("")

    headings = page.get("headings") or []
    lines.append("## Page structure")
    if headings:
        for tag, text in headings:
            lines.append(f"- **{tag.upper()}**: {_trim_text(text)}")
    else:
        lines.append("- No H1/H2/H3 headings were extracted from the live page.")
    lines.append("")

    images = page.get("images") or []
    lines.append("## Product page images")
    if images:
        for index, image in enumerate(images, 1):
            parts = [f"{index}. {image['src']}"]
            alt = image.get("alt")
            if alt:
                parts.append(f'alt="{_trim_text(alt, 120)}"')
            dims = "x".join(part for part in [image.get("width"), image.get("height")] if part)
            if dims:
                parts.append(dims)
            lines.append("- " + " | ".join(parts))
    else:
        lines.append("- No `<img>` assets were extracted from the live page.")
    lines.append("")
    lines.append("Use these image URLs and headings as product-page inputs before drafting the final PDP HTML.")
    return "\n".join(lines)


@mcp.tool(annotations=READ_ONLY)
def aeko_read_product_page_image(product_id: str, image_index: int = 1) -> Image:
    """Download one image from the live product page and return it as an MCP Image.

    This bridges the gap between product-page inspection and actual visual
    review: the caller can inspect the live PDP, then open one of its image
    assets directly through MCP vision.

    Args:
        product_id: AEKO store-product UUID.
        image_index: 1-based index from `aeko_inspect_product_page`.
    """
    ctx, err = _resolve_product_context(product_id)
    if err:
        raise ValueError(f"Product page image unavailable: {err}")
    if ctx is None:
        raise ValueError("Product page image unavailable")

    product = ctx["product"]
    url = product.get("product_url") or ""
    if not url:
        raise ValueError("Product page image unavailable: this product does not have a product URL.")

    page, page_err = _inspect_page(url, fallback_image_url=product.get("image_url"))
    if page_err:
        raise ValueError(f"Product page image unavailable: {page_err}")
    if page is None:
        raise ValueError("Product page image unavailable")

    images = page.get("images") or []
    if not images:
        raise ValueError("Product page image unavailable: no image assets were extracted from the live product page.")
    if image_index < 1 or image_index > len(images):
        raise ValueError(
            f"Product page image unavailable: image_index must be between 1 and {len(images)} for this page."
        )

    selected = images[image_index - 1]
    temp_path, download_err = _download_image_to_temp(selected["src"])
    if download_err:
        raise ValueError(f"Product page image unavailable: {download_err}")
    if temp_path is None:
        raise ValueError("Product page image unavailable")

    return Image(path=temp_path)


@mcp.tool(annotations=READ_ONLY)
def aeko_get_pdp_optimization_brief(
    product_id: str,
    strategy: str = "append_below_images",
    research_depth: str = "product_page_web",
) -> str:
    """Internal helper for `/aeko-competitive-pdp-input` and `/aeko-run-action`; not intended for standalone use.

    Builds a merchant-facing PDP optimization brief for one synced product.
    Product-first (not suggestion-key-first): resolves the product, store
    integration, domain, page analysis, and any matching AEKO `pdp_update`
    suggestion for the product URL.

    Args:
        product_id: AEKO store-product UUID.
        strategy: `append_below_images` or `rewrite_from_scratch`.
        research_depth: `product_page_only`, `product_page_web`, or `product_page_web_competitor`.
    """
    research_depth = _normalize_research_depth(research_depth)
    if strategy not in VALID_STRATEGIES:
        valid = ", ".join(sorted(VALID_STRATEGIES))
        return f"Invalid `strategy`: {strategy}. Valid values: {valid}."
    if research_depth not in VALID_RESEARCH_DEPTHS:
        valid = ", ".join(sorted(VALID_RESEARCH_DEPTHS))
        return f"Invalid `research_depth`: {research_depth}. Valid values: {valid}."

    ctx, err = _resolve_product_context(product_id)
    if err:
        return f"# PDP brief unavailable\n\n```\n{err}\n```"
    if ctx is None:
        return "# PDP brief unavailable"

    product = ctx["product"]
    integration = ctx["integration"]
    domain = ctx.get("domain") or {}
    ranked_product = ctx.get("ranked_product") or {}
    suggestion = ctx.get("suggestion") or {}
    page_analysis = ctx.get("page_analysis") or {}

    lines = [f"# PDP optimization brief: {product.get('title') or 'Untitled product'}", ""]
    lines.append("## Product context")
    lines.append(f"- **Product ID**: `{product.get('id', '?')}`")
    lines.append(f"- **External product ID**: `{product.get('external_product_id', '?')}`")
    lines.append(f"- **Product URL**: {product.get('product_url', 'N/A')}")
    lines.append(f"- **Platform**: {integration.get('platform', 'unknown')}")
    lines.append(f"- **Store**: `{integration.get('store_identifier', '?')}`")
    lines.append(f"- **Domain ID**: `{integration.get('domain_id', '?')}`")
    if domain.get("base_url"):
        lines.append(f"- **Domain URL**: {domain['base_url']}")
    if domain.get("scope"):
        lines.append(f"- **Domain scope**: {domain['scope']}")
    if ranked_product.get("ai_readiness_status"):
        lines.append(f"- **AI readiness**: {ranked_product['ai_readiness_status']}")
    lines.append(f"- **Current description length**: {_description_length(product.get('description'))} chars")
    lines.append("")

    lines.append("## Selected strategy")
    lines.append(f"- **Strategy**: `{strategy}`")
    lines.extend(_render_strategy(strategy))
    lines.append("")

    lines.append("## Research depth")
    lines.append(f"- **Depth**: `{research_depth}`")
    lines.extend(_render_research_depth(research_depth))
    lines.append("")

    lines.append("## Recommended section spine")
    if strategy == "append_below_images":
        sections = [
            "Why this product / quick summary",
            "Key benefits",
            "Specs or materials",
            "Who it is for / use scenarios",
            "Care / usage notes",
            "FAQ",
        ]
    else:
        sections = [
            "Hero summary",
            "Key benefits",
            "Specs / materials / dimensions",
            "Use cases or fit guidance",
            "Trust signals / differentiators",
            "FAQ",
        ]
    for section in sections:
        lines.append(f"- {section}")
    lines.append("")

    lines.append("## Current page signals")
    analysis_result = page_analysis.get("analysis_result") or {}
    issues = analysis_result.get("issues") or []
    if page_analysis.get("ai_readiness_score") is not None:
        lines.append(f"- **Current page AI-readiness**: {page_analysis['ai_readiness_score']}/100")
    if page_analysis.get("has_product_jsonld") is not None:
        lines.append(f"- **Has Product JSON-LD**: {page_analysis['has_product_jsonld']}")
    if issues:
        lines.append("- **Top issues**:")
        for issue in issues[:6]:
            lines.append(f"  - {issue}")
    else:
        lines.append("- No detailed page-analysis issues were returned for this product yet.")
    lines.append("")

    if suggestion:
        brief = suggestion.get("brief") or {}
        lines.append("## Matching AEKO PDP suggestion")
        lines.append(f"- **Suggestion key**: `{suggestion.get('key', '?')}`")
        if suggestion.get("priority"):
            lines.append(f"- **Priority**: {suggestion['priority']}")
        if suggestion.get("rationale"):
            lines.append(f"- **Why**: {suggestion['rationale']}")
        if brief.get("persona"):
            lines.append(f"- **Persona**: {brief['persona']}")
        if brief.get("tone"):
            lines.append(f"- **Tone**: {brief['tone']}")
        if brief.get("structure"):
            lines.append(f"- **Suggested structure**: {' → '.join(brief['structure'])}")
        if brief.get("topics"):
            lines.append(f"- **Topics to cover**: {', '.join(brief['topics'])}")
        if brief.get("required_jsonld"):
            lines.append(f"- **Required JSON-LD**: {', '.join(brief['required_jsonld'])}")
        if brief.get("must_include"):
            lines.append(f"- **Must include**: {', '.join(brief['must_include'])}")
        evidence = suggestion.get("source_evidence") or []
        if evidence:
            lines.append("- **Winning competitor structures to mirror**:")
            for item in evidence[:5]:
                headline = item.get("headline") or item.get("url") or "Competitor source"
                structure = item.get("structure") or []
                suffix = f" ({' / '.join(structure)})" if structure else ""
                lines.append(f"  - {headline}{suffix}")
        lines.append("")

    lines.append("## Recommended workflow")
    lines.append("1. Review this brief and confirm the product, strategy, and research depth.")
    lines.append("2. Use `aeko_inspect_product_page(...)` and `aeko_read_product_page_image(...)` to extract factual details from the live PDP.")
    if research_depth == "product_page_web":
        lines.append("3. Add official web facts from the brand or manufacturer before drafting.")
    elif research_depth == "product_page_web_competitor":
        lines.append(
            "3. Run `/aeko-competitive-pdp-input "
            f"{product.get('id', '')}` to collect competitor structure and differentiator inputs before drafting."
        )
    lines.append("4. Generate the final HTML.")
    lines.append("5. Deploy with `aeko_deploy_pdp_html(product_id=..., html=..., deployment_mode='manual_copy' | 'write_api')`.")
    # Suggestion completion is v1-UUID only today. PDP briefs come from v2,
    # which has no complete endpoint — users mark done in the dashboard.
    return "\n".join(lines)


@mcp.tool(annotations=WRITE_ONCE)
def aeko_deploy_pdp_html(
    product_id: str,
    html: str,
    deployment_mode: str = "manual_copy",
) -> str:
    """Save generated PDP HTML locally or write it back to the store via API.

    Args:
        product_id: AEKO store-product UUID.
        html: Final product detail HTML.
        deployment_mode: `manual_copy` or `write_api`.
    """
    if deployment_mode not in VALID_DEPLOYMENT_MODES:
        valid = ", ".join(sorted(VALID_DEPLOYMENT_MODES))
        return f"Invalid `deployment_mode`: {deployment_mode}. Valid values: {valid}."

    ctx, err = _resolve_product_context(product_id)
    if err:
        return f"# PDP deployment unavailable\n\n```\n{err}\n```"
    if ctx is None:
        return "# PDP deployment unavailable"

    product = ctx["product"]
    integration = ctx["integration"]
    platform = integration.get("platform", "unknown")

    if deployment_mode == "manual_copy":
        lines = ["# PDP HTML ready for manual deployment", ""]
        lines.append(f"- **Product**: {product.get('title') or 'Untitled product'}")
        lines.append(f"- **Platform**: {platform}")
        lines.append("- **HTML source**: Use the generated HTML already shown in the MCP conversation.")
        lines.append("")
        lines.append("## Next steps")
        for step in _platform_publish_instructions(platform):
            lines.append(step)
        return "\n".join(lines)

    payload = {"description": html}
    result, write_err = _safe_post(
        f"/api/store-integrations/{integration.get('id')}/products/{product.get('external_product_id')}",
        payload,
    )
    if write_err:
        return f"# PDP write failed\n\n```\n{write_err}\n```"

    lines = ["# PDP written to store", ""]
    lines.append(f"- **Product**: {product.get('title') or 'Untitled product'}")
    lines.append(f"- **Platform**: {platform}")
    lines.append(f"- **Store integration**: `{integration.get('id', '?')}`")
    if result:
        lines.append(f"- **Status**: {result.get('status', 'ok')}")
        if result.get("audit_id"):
            lines.append(f"- **Audit ID**: `{result['audit_id']}`")
            lines.append(f"- **Rollback**: `aeko_revert_store_write(audit_id='{result['audit_id']}')`")
    lines.append("")
    lines.append("The product description HTML was sent directly to the connected store.")
    return "\n".join(lines)
