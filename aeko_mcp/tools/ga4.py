"""MCP tools for GA4 connection status and sync operations."""

import json
from typing import Any, Optional

from ..server import client, mcp
from ._annotations import READ_ONLY, WRITE


def _json_block(title: str, payload: Any) -> str:
    return f"# {title}\n\n```json\n{json.dumps(payload, ensure_ascii=False, indent=2, default=str)}\n```"


@mcp.tool(title="Get GA4 status", annotations=READ_ONLY)
def aeko_get_ga4_status(domain_id: str) -> str:
    """Check whether GA4 is connected and whether a property is selected."""
    data = client.get("/api/ga4/status", params={"domain_id": domain_id})
    return _json_block("GA4 status", data)


@mcp.tool(title="List GA4 properties", annotations=READ_ONLY)
def aeko_list_ga4_properties(domain_id: str) -> str:
    """List selectable GA4 properties for an already connected domain."""
    data = client.get("/api/ga4/properties", params={"domain_id": domain_id})
    return _json_block("GA4 properties", data)


@mcp.tool(title="Select GA4 property", annotations=WRITE)
def aeko_select_ga4_property(
    domain_id: str,
    property_id: str,
    property_name: str,
    account_id: Optional[str] = None,
    account_name: Optional[str] = None,
) -> str:
    """Select the GA4 property AEKO should use for Measure analytics."""
    payload = {
        "domain_id": domain_id,
        "property_id": property_id,
        "property_name": property_name,
        "account_id": account_id,
        "account_name": account_name,
    }
    body = {k: v for k, v in payload.items() if v is not None}
    client.post("/api/ga4/select-property", json=body)
    return _json_block("GA4 property selected", body)


@mcp.tool(title="Sync GA4 metrics", annotations=WRITE)
def aeko_sync_ga4(domain_id: str) -> str:
    """Trigger GA4 metric sync for the selected property.

    The backend owns the fixed sync lookback and rate limit.
    """
    data = client.post("/api/ga4/sync-mine", json={"domain_id": domain_id})
    return _json_block("GA4 sync complete", data)
