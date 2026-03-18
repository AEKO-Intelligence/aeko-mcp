import json
import os
import subprocess
import sys
import tempfile
import time

from ..server import mcp


def _build_html(
    product_title: str,
    original_description: str,
    optimized_description: str,
    json_ld: str,
    aeo_score_before: int,
    aeo_score_after: int,
    product_url: str,
    faq_items: list,
    target_market: str,
    language: str,
) -> str:
    """Build a self-contained HTML preview page."""

    # Escape for safe embedding in JS template literals
    def js_escape(s: str) -> str:
        return (
            s.replace("\\", "\\\\")
            .replace("`", "\\`")
            .replace("${", "\\${")
            .replace("</script>", "<\\/script>")
        )

    original_esc = js_escape(original_description)
    optimized_esc = js_escape(optimized_description)
    json_ld_esc = js_escape(json_ld)
    faq_json_esc = js_escape(json.dumps(faq_items, ensure_ascii=False))
    title_esc = js_escape(product_title)
    url_esc = js_escape(product_url)

    market_flags = {
        "US": "\U0001f1fa\U0001f1f8", "KR": "\U0001f1f0\U0001f1f7", "JP": "\U0001f1ef\U0001f1f5",
        "CN": "\U0001f1e8\U0001f1f3", "DE": "\U0001f1e9\U0001f1ea", "FR": "\U0001f1eb\U0001f1f7",
        "GB": "\U0001f1ec\U0001f1e7", "CA": "\U0001f1e8\U0001f1e6", "AU": "\U0001f1e6\U0001f1fa",
    }
    flag = market_flags.get(target_market.upper(), "\U0001f310")

    delta = aeo_score_after - aeo_score_before
    delta_sign = "+" if delta > 0 else ""
    delta_color = "text-green-600" if delta > 0 else ("text-red-600" if delta < 0 else "text-gray-500")

    return f"""<!DOCTYPE html>
<html lang="{language}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AEKO Preview — {product_title}</title>
<script src="https://cdn.tailwindcss.com"></script>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/languages/json.min.js"></script>
<style>
  .tab-active {{ background: #1e293b; color: white; }}
  .tab-inactive {{ background: #f1f5f9; color: #475569; }}
  .diff-add {{ background: #dcfce7; }}
  .diff-del {{ background: #fee2e2; text-decoration: line-through; color: #991b1b; }}
  .check-pass {{ color: #16a34a; }}
  .check-fail {{ color: #dc2626; }}
  .score-bar {{ transition: width 0.6s ease; }}
</style>
</head>
<body class="bg-gray-50 min-h-screen">

<!-- Header -->
<header class="bg-slate-900 text-white px-6 py-4">
  <div class="max-w-7xl mx-auto flex items-center justify-between">
    <div class="flex items-center gap-3">
      <div class="text-xl font-bold tracking-tight">AEKO</div>
      <div class="text-slate-400 text-sm">Preview</div>
    </div>
    <div class="flex items-center gap-4 text-sm">
      <span>{flag} {target_market.upper()}</span>
      <span class="bg-slate-700 px-2 py-0.5 rounded text-xs uppercase">{language}</span>
    </div>
  </div>
</header>

<main class="max-w-7xl mx-auto px-6 py-8">
  <!-- Title + Score -->
  <div class="flex items-start justify-between mb-8">
    <div>
      <h1 class="text-2xl font-bold text-slate-900" id="product-title"></h1>
      <p class="text-sm text-slate-500 mt-1" id="product-url"></p>
    </div>
    <div class="flex items-center gap-4 bg-white rounded-xl shadow-sm border px-6 py-4">
      <div class="text-center">
        <div class="text-xs text-slate-400 uppercase tracking-wide">Before</div>
        <div class="text-2xl font-bold text-slate-400">{aeo_score_before}</div>
      </div>
      <div class="text-slate-300 text-2xl">&rarr;</div>
      <div class="text-center">
        <div class="text-xs text-slate-400 uppercase tracking-wide">After</div>
        <div class="text-2xl font-bold text-slate-900">{aeo_score_after}</div>
      </div>
      <div class="ml-2 px-3 py-1 rounded-full text-sm font-semibold {delta_color} bg-opacity-10" style="background: {'#dcfce7' if delta > 0 else ('#fee2e2' if delta < 0 else '#f1f5f9')}">
        {delta_sign}{delta}
      </div>
    </div>
  </div>

  <!-- Score bars -->
  <div class="bg-white rounded-xl shadow-sm border p-4 mb-8">
    <div class="flex items-center gap-4 mb-2">
      <span class="text-xs text-slate-400 w-12">Before</span>
      <div class="flex-1 bg-gray-100 rounded-full h-3">
        <div class="score-bar bg-slate-300 h-3 rounded-full" style="width: {aeo_score_before}%"></div>
      </div>
      <span class="text-xs text-slate-400 w-8">{aeo_score_before}</span>
    </div>
    <div class="flex items-center gap-4">
      <span class="text-xs text-slate-400 w-12">After</span>
      <div class="flex-1 bg-gray-100 rounded-full h-3">
        <div class="score-bar bg-emerald-500 h-3 rounded-full" style="width: {aeo_score_after}%"></div>
      </div>
      <span class="text-xs text-slate-400 w-8">{aeo_score_after}</span>
    </div>
  </div>

  <div class="flex gap-8">
    <!-- Main content area -->
    <div class="flex-1">
      <!-- Tabs -->
      <div class="flex gap-1 mb-4">
        <button onclick="showTab('original')" id="tab-original" class="tab-active px-4 py-2 rounded-lg text-sm font-medium cursor-pointer">Original</button>
        <button onclick="showTab('optimized')" id="tab-optimized" class="tab-inactive px-4 py-2 rounded-lg text-sm font-medium cursor-pointer">Optimized</button>
        <button onclick="showTab('diff')" id="tab-diff" class="tab-inactive px-4 py-2 rounded-lg text-sm font-medium cursor-pointer">Diff</button>
        <button onclick="showTab('jsonld')" id="tab-jsonld" class="tab-inactive px-4 py-2 rounded-lg text-sm font-medium cursor-pointer">JSON-LD</button>
      </div>

      <!-- Tab content -->
      <div id="content-original" class="bg-white rounded-xl shadow-sm border p-6">
        <div class="prose max-w-none whitespace-pre-wrap" id="original-text"></div>
      </div>
      <div id="content-optimized" class="bg-white rounded-xl shadow-sm border p-6 hidden">
        <div class="prose max-w-none whitespace-pre-wrap" id="optimized-text"></div>
      </div>
      <div id="content-diff" class="bg-white rounded-xl shadow-sm border p-6 hidden">
        <div class="prose max-w-none" id="diff-output"></div>
      </div>
      <div id="content-jsonld" class="bg-white rounded-xl shadow-sm border p-6 hidden">
        <pre><code class="language-json" id="jsonld-code"></code></pre>
      </div>

      <!-- FAQ section -->
      <div id="faq-section" class="mt-8 hidden">
        <h2 class="text-lg font-semibold text-slate-900 mb-4">Generated FAQ</h2>
        <div id="faq-list" class="space-y-3"></div>
      </div>

      <!-- Rich Result Preview -->
      <div id="rich-result-section" class="mt-8">
        <h2 class="text-lg font-semibold text-slate-900 mb-4">Rich Result Preview</h2>
        <div id="rich-result-card" class="bg-white rounded-xl shadow-sm border p-6"></div>
      </div>
    </div>

    <!-- Sidebar: AEO Checklist -->
    <div class="w-72 shrink-0">
      <div class="bg-white rounded-xl shadow-sm border p-5 sticky top-8">
        <h3 class="text-sm font-semibold text-slate-900 uppercase tracking-wide mb-4">AEO Checklist</h3>
        <div id="checklist" class="space-y-2"></div>
        <div class="mt-4 pt-4 border-t">
          <div class="flex justify-between text-sm">
            <span class="text-slate-500">Score</span>
            <span id="checklist-score" class="font-semibold"></span>
          </div>
        </div>
      </div>
    </div>
  </div>
</main>

<footer class="text-center py-8 text-xs text-slate-400">
  Generated by AEKO &middot; AI Engine Optimization
</footer>

<script>
// Data
const DATA = {{
  title: `{title_esc}`,
  url: `{url_esc}`,
  original: `{original_esc}`,
  optimized: `{optimized_esc}`,
  jsonLd: `{json_ld_esc}`,
  faqItems: JSON.parse(`{faq_json_esc}`),
}};

// Init
document.getElementById('product-title').textContent = DATA.title;
document.getElementById('product-url').textContent = DATA.url;
document.getElementById('original-text').textContent = DATA.original;
document.getElementById('optimized-text').textContent = DATA.optimized;

// JSON-LD display
try {{
  const parsed = JSON.parse(DATA.jsonLd);
  document.getElementById('jsonld-code').textContent = JSON.stringify(parsed, null, 2);
  hljs.highlightElement(document.getElementById('jsonld-code'));
}} catch(e) {{
  document.getElementById('jsonld-code').textContent = DATA.jsonLd;
}}

// Tab switching
function showTab(name) {{
  ['original','optimized','diff','jsonld'].forEach(t => {{
    document.getElementById('content-' + t).classList.toggle('hidden', t !== name);
    document.getElementById('tab-' + t).className = t === name
      ? 'tab-active px-4 py-2 rounded-lg text-sm font-medium cursor-pointer'
      : 'tab-inactive px-4 py-2 rounded-lg text-sm font-medium cursor-pointer';
  }});
}}

// Word-level diff (Myers-like)
function wordDiff(oldText, newText) {{
  const oldWords = oldText.split(/(\\s+)/);
  const newWords = newText.split(/(\\s+)/);

  // LCS-based diff
  const m = oldWords.length, n = newWords.length;
  // For very long texts, fall back to line diff
  if (m * n > 500000) {{
    return lineDiff(oldText, newText);
  }}

  const dp = Array.from({{length: m + 1}}, () => new Uint16Array(n + 1));
  for (let i = 1; i <= m; i++) {{
    for (let j = 1; j <= n; j++) {{
      if (oldWords[i-1] === newWords[j-1]) {{
        dp[i][j] = dp[i-1][j-1] + 1;
      }} else {{
        dp[i][j] = Math.max(dp[i-1][j], dp[i][j-1]);
      }}
    }}
  }}

  // Backtrack
  const result = [];
  let i = m, j = n;
  while (i > 0 || j > 0) {{
    if (i > 0 && j > 0 && oldWords[i-1] === newWords[j-1]) {{
      result.unshift({{type: 'equal', text: oldWords[i-1]}});
      i--; j--;
    }} else if (j > 0 && (i === 0 || dp[i][j-1] >= dp[i-1][j])) {{
      result.unshift({{type: 'add', text: newWords[j-1]}});
      j--;
    }} else {{
      result.unshift({{type: 'del', text: oldWords[i-1]}});
      i--;
    }}
  }}

  return result.map(r => {{
    if (r.type === 'add') return `<span class="diff-add">${{escHtml(r.text)}}</span>`;
    if (r.type === 'del') return `<span class="diff-del">${{escHtml(r.text)}}</span>`;
    return escHtml(r.text);
  }}).join('');
}}

function lineDiff(oldText, newText) {{
  const oldLines = oldText.split('\\n');
  const newLines = newText.split('\\n');
  const parts = [];
  const maxLen = Math.max(oldLines.length, newLines.length);
  for (let i = 0; i < maxLen; i++) {{
    const o = oldLines[i] || '';
    const n = newLines[i] || '';
    if (o === n) {{
      parts.push(escHtml(o));
    }} else {{
      if (o) parts.push(`<span class="diff-del">${{escHtml(o)}}</span>`);
      if (n) parts.push(`<span class="diff-add">${{escHtml(n)}}</span>`);
    }}
  }}
  return parts.join('\\n');
}}

function escHtml(s) {{
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}}

// Render diff
document.getElementById('diff-output').innerHTML =
  '<div class="whitespace-pre-wrap">' + wordDiff(DATA.original, DATA.optimized) + '</div>';

// FAQ
if (DATA.faqItems && DATA.faqItems.length > 0) {{
  document.getElementById('faq-section').classList.remove('hidden');
  const list = document.getElementById('faq-list');
  DATA.faqItems.forEach((item, idx) => {{
    const q = item.question || item.q || '';
    const a = item.answer || item.a || '';
    list.innerHTML += `
      <div class="bg-gray-50 rounded-lg p-4">
        <div class="font-medium text-slate-900 mb-1">${{idx+1}}. ${{escHtml(q)}}</div>
        <div class="text-sm text-slate-600">${{escHtml(a)}}</div>
      </div>`;
  }});
}}

// Rich Result Preview
function renderRichResult() {{
  const card = document.getElementById('rich-result-card');
  try {{
    const ld = JSON.parse(DATA.jsonLd);
    const name = ld.name || DATA.title;
    const desc = (ld.description || '').substring(0, 160);
    const brand = ld.brand?.name || ld.brand || '';
    const price = ld.offers?.price || ld.offers?.[0]?.price || '';
    const currency = ld.offers?.priceCurrency || ld.offers?.[0]?.priceCurrency || '';
    const rating = ld.aggregateRating?.ratingValue || '';
    const reviewCount = ld.aggregateRating?.reviewCount || '';
    const availability = ld.offers?.availability || ld.offers?.[0]?.availability || '';
    const availShort = availability.replace('https://schema.org/', '').replace('http://schema.org/', '');

    card.innerHTML = `
      <div class="border-l-4 border-blue-500 pl-4">
        <div class="text-blue-700 text-sm mb-1">${{escHtml(DATA.url || 'example.com')}}</div>
        <div class="text-lg font-medium text-blue-900 mb-1">${{escHtml(name)}}</div>
        <div class="text-sm text-slate-600 mb-2">${{escHtml(desc)}}</div>
        <div class="flex flex-wrap gap-3 text-xs text-slate-500">
          ${{brand ? `<span>Brand: ${{escHtml(brand)}}</span>` : ''}}
          ${{price ? `<span class="font-semibold text-slate-700">${{escHtml(currency)}} ${{escHtml(String(price))}}</span>` : ''}}
          ${{rating ? `<span>${{'&#9733;'.repeat(Math.round(Number(rating)))}} ${{rating}}${{reviewCount ? ` (${{reviewCount}} reviews)` : ''}}</span>` : ''}}
          ${{availShort ? `<span>${{availShort}}</span>` : ''}}
        </div>
      </div>`;
  }} catch(e) {{
    card.innerHTML = '<p class="text-sm text-slate-400">No valid JSON-LD to preview.</p>';
  }}
}}
renderRichResult();

// AEO Checklist
function renderChecklist() {{
  const el = document.getElementById('checklist');
  const scoreEl = document.getElementById('checklist-score');
  let passed = 0;

  const checks = [];
  try {{
    const ld = JSON.parse(DATA.jsonLd);
    checks.push({{ label: 'Product schema', ok: ld['@type'] === 'Product' || (Array.isArray(ld['@type']) && ld['@type'].includes('Product')) }});
    checks.push({{ label: 'Brand defined', ok: !!ld.brand }});
    checks.push({{ label: 'Price / Offers', ok: !!ld.offers }});
    checks.push({{ label: 'Aggregate rating', ok: !!ld.aggregateRating }});
    checks.push({{ label: 'SKU / GTIN', ok: !!(ld.sku || ld.gtin || ld.gtin13 || ld.gtin8 || ld.mpn) }});
    checks.push({{ label: 'Product image', ok: !!ld.image }});
    checks.push({{ label: 'Description', ok: !!(ld.description && ld.description.length > 50) }});
    checks.push({{ label: 'Availability', ok: !!(ld.offers?.availability || ld.offers?.[0]?.availability) }});
  }} catch(e) {{
    checks.push({{ label: 'Valid JSON-LD', ok: false }});
  }}

  checks.push({{ label: 'FAQ content', ok: DATA.faqItems && DATA.faqItems.length >= 3 }});
  checks.push({{ label: 'Optimized description', ok: DATA.optimized.length > DATA.original.length }});

  checks.forEach(c => {{
    if (c.ok) passed++;
    el.innerHTML += `
      <div class="flex items-center gap-2 text-sm">
        <span class="${{c.ok ? 'check-pass' : 'check-fail'}}">${{c.ok ? '&#10003;' : '&#10007;'}}</span>
        <span class="${{c.ok ? 'text-slate-700' : 'text-slate-400'}}">${{c.label}}</span>
      </div>`;
  }});

  scoreEl.textContent = `${{passed}}/${{checks.length}}`;
}}
renderChecklist();
</script>
</body>
</html>"""


def _open_in_browser(filepath: str) -> None:
    """Open a file in the default browser."""
    if sys.platform == "darwin":
        subprocess.Popen(["open", filepath])
    elif sys.platform.startswith("linux"):
        subprocess.Popen(["xdg-open", filepath])
    elif sys.platform == "win32":
        os.startfile(filepath)


@mcp.tool()
def aeko_preview_optimized_page(
    product_title: str,
    original_description: str,
    optimized_description: str,
    json_ld: str,
    aeo_score_before: int,
    aeo_score_after: int,
    product_url: str = "",
    faq_items: str = "[]",
    target_market: str = "US",
    language: str = "en",
) -> str:
    """Generate an HTML preview comparing original vs AEO-optimized content and open it in the browser.

    Creates a self-contained HTML file with side-by-side comparison, word-level diff,
    JSON-LD preview, AEO checklist, and score visualization. Opens automatically in
    the default browser.

    Args:
        product_title: Name of the product being optimized.
        original_description: The current product description text.
        optimized_description: The AEO-optimized product description text.
        json_ld: JSON string of the Product schema.org structured data.
        aeo_score_before: AEO readiness score before optimization (0-100).
        aeo_score_after: AEO readiness score after optimization (0-100).
        product_url: URL of the product page (optional).
        faq_items: JSON string array of FAQ objects with "question" and "answer" keys (optional).
        target_market: Target market country code, e.g. "US", "KR", "JP" (default "US").
        language: Content language code, e.g. "en", "ko" (default "en").
    """
    # Parse FAQ items
    try:
        faq_list = json.loads(faq_items) if isinstance(faq_items, str) else faq_items
    except (json.JSONDecodeError, TypeError):
        faq_list = []

    html = _build_html(
        product_title=product_title,
        original_description=original_description,
        optimized_description=optimized_description,
        json_ld=json_ld,
        aeo_score_before=aeo_score_before,
        aeo_score_after=aeo_score_after,
        product_url=product_url,
        faq_items=faq_list,
        target_market=target_market,
        language=language,
    )

    # Write to temp file and open
    timestamp = int(time.time())
    tmp_dir = tempfile.gettempdir()
    filepath = os.path.join(tmp_dir, f"aeko-preview-{timestamp}.html")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)

    _open_in_browser(filepath)

    return f"Preview opened in browser: {filepath}\n\nThe HTML file contains:\n- Original vs Optimized description tabs\n- Word-level diff view\n- JSON-LD structured data with syntax highlighting\n- Rich Result preview card\n- AEO checklist sidebar ({aeo_score_before} → {aeo_score_after})"
