"""Brand Kit tools.

The live Brand Kit is the source of truth for an AEKO domain's voice,
persona, and style guardrails. Plan.md snapshots reference a
`snapshot_version`; every edit here bumps the version so downstream skills
can detect staleness.

Backend contract: `api/schemas/brand_kits.py` — `BrandKitResponse` /
`BrandKitUpdate`.
"""
from typing import Any, List, Optional

from ..server import mcp, client


def _fmt_list(label: str, values: Optional[List[str]], max_items: int = 10) -> List[str]:
    if not values:
        return []
    shown = values[:max_items]
    more = len(values) - len(shown)
    suffix = f" (+{more} more)" if more > 0 else ""
    joined = ", ".join(shown)
    return [f"- **{label}**: {joined}{suffix}"]


def _format_brand_kit(kit: dict) -> str:
    if not kit:
        return "No brand kit found for this domain. Run `/aeko-brand-kit` to create one."

    lines: List[str] = []
    lines.append(f"# Brand Kit — {kit.get('brand_name', 'Unnamed')}")
    lines.append("")
    lines.append(f"- **Kit ID**: `{kit.get('id', 'N/A')}`")
    lines.append(f"- **Domain ID**: `{kit.get('domain_id') or 'N/A'}`")
    lines.append(f"- **Status**: {kit.get('status', 'unknown')}")
    lines.append(f"- **Snapshot version**: `{kit.get('snapshot_version', 'N/A')}`")
    lines.append(f"- **Updated**: {kit.get('updated_at', 'N/A')}")
    if kit.get("generator_version"):
        lines.append(f"- **Generator**: {kit['generator_version']}")
    lines.append("")

    def section(label: str, body: Optional[str]) -> None:
        if body:
            lines.append(f"## {label}")
            lines.append("")
            lines.append(body.strip())
            lines.append("")

    section("Tagline", kit.get("tagline"))
    section("Tone of voice", kit.get("tone_of_voice"))
    section("Brand voice summary", kit.get("brand_voice_summary"))
    section("Target audience", kit.get("target_audience"))

    guardrails: List[str] = []
    guardrails.extend(_fmt_list("must_include", kit.get("must_include")))
    guardrails.extend(_fmt_list("forbidden", kit.get("forbidden")))
    guardrails.extend(_fmt_list("sample_urls", kit.get("sample_urls")))
    if guardrails:
        lines.append("## Guardrails & samples")
        lines.append("")
        lines.extend(guardrails)
        lines.append("")

    visual_bits: List[str] = []
    if kit.get("primary_color"):
        visual_bits.append(f"- **Primary color**: {kit['primary_color']}")
    if kit.get("logo_url"):
        visual_bits.append(f"- **Logo**: {kit['logo_url']}")
    if visual_bits:
        lines.append("## Visual")
        lines.append("")
        lines.extend(visual_bits)
        lines.append("")

    meta = kit.get("metadata") or {}
    if meta:
        lines.append("## Account")
        lines.append("")
        lines.append(f"- **Tier**: {meta.get('account_tier', 'unknown')}")
        if meta.get("billing_url"):
            lines.append(f"- **Billing**: {meta['billing_url']}")
        lines.append("")

    if kit.get("last_error"):
        lines.append("## Last error")
        lines.append("")
        lines.append(f"> {kit['last_error']}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


@mcp.tool()
def aeko_get_brand_kit(domain_id: str) -> str:
    """Fetch the active Brand Kit for a domain.

    Returns the live kit (voice, persona, guardrails, snapshot_version,
    account tier). `aeko-run-action` uses this to check for stale snapshots
    and to enforce `requires_brand_kit` plans.

    Args:
        domain_id: UUID of the domain.
    """
    data = client.get(f"/api/brand-kit/{domain_id}")
    return _format_brand_kit(data)


@mcp.tool()
def aeko_update_brand_kit(
    kit_id: str,
    name: Optional[str] = None,
    status: Optional[str] = None,
    brand_name: Optional[str] = None,
    tagline: Optional[str] = None,
    tone_of_voice: Optional[str] = None,
    brand_voice_summary: Optional[str] = None,
    target_audience: Optional[str] = None,
    primary_color: Optional[str] = None,
    logo_url: Optional[str] = None,
    sample_urls: Optional[List[str]] = None,
    must_include: Optional[List[str]] = None,
    forbidden: Optional[List[str]] = None,
) -> str:
    """Patch a Brand Kit. Only pass the fields you want to change.

    Every successful update bumps `snapshot_version`. Downstream
    `aeko-run-action` runs against a Plan.md with an older snapshot will
    warn the user before proceeding.

    `status` may only be set to `active` or `draft` by clients;
    `generating` / `failed` are system-controlled.

    Args:
        kit_id: UUID of the brand kit to update.
        (other fields): any subset of BrandKitUpdate.
    """
    body: dict[str, Any] = {}
    for key, value in (
        ("name", name),
        ("status", status),
        ("brand_name", brand_name),
        ("tagline", tagline),
        ("tone_of_voice", tone_of_voice),
        ("brand_voice_summary", brand_voice_summary),
        ("target_audience", target_audience),
        ("primary_color", primary_color),
        ("logo_url", logo_url),
        ("sample_urls", sample_urls),
        ("must_include", must_include),
        ("forbidden", forbidden),
    ):
        if value is not None:
            body[key] = value

    if not body:
        return "No fields to update. Pass at least one field."

    updated = client.patch(f"/api/brand-kits/{kit_id}", json=body)
    return _format_brand_kit(updated)
