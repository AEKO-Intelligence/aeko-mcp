"""Read the same owner-scoped Fact Check records used by the dashboard."""
import json
from ..server import mcp, client
from ._annotations import READ_ONLY


@mcp.tool(title="List brand fact checks", annotations=READ_ONLY)
def aeko_list_fact_checks(domain_id: str, state: str = "needs_review,action_required", limit: int = 30, offset: int = 0) -> str:
    """List stored source/Wiki comparisons for one owned domain, without calling AI.

    Missing Wiki information is separate from a contradiction. User confirmation
    happens in AEKO's Fact Check/Brand Wiki review flow. This tool does not approve
    knowledge or mark an external source corrected. Use pagination for more rows.
    """
    payload = client.get("/api/fact-check", params={"domain_id": domain_id, "state": state, "limit": max(1, min(limit, 100)), "offset": max(offset, 0)})
    return json.dumps(payload, ensure_ascii=False, default=str)


@mcp.tool(title="Get fact check and review history", annotations=READ_ONLY)
def aeko_get_fact_check(domain_id: str, finding_id: str) -> str:
    """Read a finding's current revision, exact source quotation, Wiki reference and decisions.

    Before executing a saved correction plan, require its expected revision and
    action_required state to match this record. Source and accepted Wiki freshness
    must still be checked; a recorded decision is not permission to publish or send.
    """
    payload = client.get(f"/api/fact-check/{finding_id}", params={"domain_id": domain_id})
    return json.dumps(payload, ensure_ascii=False, default=str)
