"""Saved assistant-task-v1 results and exact task-bound operations.

The backend owns scope, entitlement and claim checks. These adapters preserve
the item/claim/selected-row tuple instead of reusing independent legacy tools.
"""

import json
from typing import Any, Optional

from ..server import client, mcp
from ._annotations import READ_ONLY, WRITE, WRITE_ONCE
from ._structured import AekoToolInputError, path_segment_arg, read_boundary, uuid_arg


def _item(value: str) -> str:
    item = path_segment_arg(value, "item_id")
    if not item.startswith("itm_"):
        raise AekoToolInputError("INVALID_ARGUMENT", "item_id must be an itm_ identifier.")
    return item


def _block(title: str, result: Any) -> str:
    return f"# {title}\n\n```json\n{json.dumps(result, ensure_ascii=False, indent=2, default=str)}\n```"


@mcp.tool(title="Save an AEKO assistant task", annotations=WRITE_ONCE)
def aeko_create_assistant_task(
    action_id: str,
    scope: dict,
    idempotency_key: str,
    request_text: str = "",
    supersedes_item_id: Optional[str] = None,
) -> str:
    """Save one versioned assistant task; no execution happens on save.

    The server catalog resolves the action's skill, evidence and permissions.
    Use a stable idempotency key for retries; changing the request under the
    same key is a conflict. Dashboard handoffs normally create tasks directly.
    """
    if action_id not in {
        "tracking.suggested_prompts.bulk_track.v1",
        "tracking.selected_questions_report.v1",
        "competitors.comparison_report.v1",
        "competitors.question_gaps_report.v1",
        "competitors.source_patterns_report.v1",
        "ads.copy_format.proposal.v1",
        "visibility.overview_report.v1",
        "markets.comparison_report.v1",
        "contexts.group_proposal.v1",
        "contexts.related_questions_report.v1",
        "reviews.strengths_report.v1",
        "ads.performance_report.v1",
        "measure.ga4_report.v1",
        "technical.findings_plan.v1",
        "ads.rule_change_proposal.v1",
    }:
        raise AekoToolInputError("INVALID_ARGUMENT", "Unsupported assistant task action_id.")
    if not isinstance(scope, dict) or not scope:
        raise AekoToolInputError("INVALID_ARGUMENT", "scope must be a non-empty object.")
    if not isinstance(idempotency_key, str) or not 1 <= len(idempotency_key) <= 255:
        raise AekoToolInputError("INVALID_ARGUMENT", "idempotency_key must be 1–255 characters.")
    if not isinstance(request_text, str) or len(request_text) > 4000:
        raise AekoToolInputError("INVALID_ARGUMENT", "request_text must be at most 4000 characters.")
    body: dict[str, Any] = {"action_id": action_id, "scope": scope, "request_text": request_text}
    if supersedes_item_id is not None:
        body["supersedes_item_id"] = _item(supersedes_item_id)
    result = client.post(
        "/api/action-items/assistant-tasks",
        json=body,
        headers={"Idempotency-Key": idempotency_key},
    )
    return _block("Assistant task saved", result)


@mcp.tool(title="Track exact suggestions in a saved task", annotations=WRITE_ONCE)
def aeko_track_task_suggestions(
    item_id: str,
    claim_id: str,
    rows: list[dict],
    ai_platforms: list[str],
    countries: list[str],
) -> str:
    """Track only the exact Context suggestion rows and variants in a claimed task.

    The server compares every row, platform and country with the frozen task,
    checks current quota/access, and persists a per-row receipt. On a retry it
    returns that receipt rather than repeating applied writes. This is distinct
    from the older review tool that picks top suggestions per review.
    """
    item = _item(item_id)
    claim = uuid_arg(claim_id, "claim_id")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 200:
        raise AekoToolInputError("INVALID_ARGUMENT", "rows must contain 1–200 exact suggestions.")
    for row in rows:
        if not isinstance(row, dict) or set(row) - {"context_id", "suggested_prompt_id", "prompt"}:
            raise AekoToolInputError("INVALID_ARGUMENT", "Each row needs exact Context suggestion fields.")
        uuid_arg(row.get("context_id"), "context_id")
        uuid_arg(row.get("suggested_prompt_id"), "suggested_prompt_id")
        if row.get("prompt") is not None and (not isinstance(row["prompt"], str) or not row["prompt"].strip()):
            raise AekoToolInputError("INVALID_ARGUMENT", "An edited prompt must be non-empty text.")
    if not all(isinstance(p, str) and p for p in ai_platforms) or not ai_platforms:
        raise AekoToolInputError("INVALID_ARGUMENT", "ai_platforms must contain explicit values.")
    if not all(isinstance(c, str) and c for c in countries) or not countries:
        raise AekoToolInputError("INVALID_ARGUMENT", "countries must contain explicit values.")
    result = client.post(
        f"/api/action-items/{item}/track-suggestions",
        json={"claim_id": claim, "rows": rows, "ai_platforms": ai_platforms, "countries": countries},
    )
    return _block("Saved task tracking receipt", result)


@mcp.tool(title="Save an AEKO action output", annotations=WRITE_ONCE)
def aeko_save_action_output(
    item_id: str,
    claim_id: str,
    idempotency_key: str,
    kind: str,
    schema_version: str,
    markdown: Optional[str] = None,
    data: Optional[dict] = None,
    evidence_ids: Optional[list[str]] = None,
) -> str:
    """Persist a claimed task's actual result for AEKO's report/output viewer.

    Client-written kinds are ``report_markdown``,
    ``ad_copy_format_proposal``, ``context_group_proposal`` and
    ``ad_rule_proposal``. Tracking receipts are server-created by
    ``aeko_track_task_suggestions``; client success summaries cannot create
    them. A local file path is not a report.
    """
    item = _item(item_id)
    claim = uuid_arg(claim_id, "claim_id")
    if kind not in {"report_markdown", "ad_copy_format_proposal", "context_group_proposal", "ad_rule_proposal"}:
        raise AekoToolInputError("INVALID_ARGUMENT", "Unsupported client-written output kind.")
    if schema_version != "assistant-output-v1":
        raise AekoToolInputError("INVALID_ARGUMENT", "schema_version must be assistant-output-v1.")
    if not isinstance(idempotency_key, str) or not 1 <= len(idempotency_key) <= 160:
        raise AekoToolInputError("INVALID_ARGUMENT", "idempotency_key must be 1–160 characters.")
    if kind == "report_markdown" and (not isinstance(markdown, str) or not markdown.strip() or len(markdown.encode("utf-8")) > 64 * 1024):
        raise AekoToolInputError("INVALID_ARGUMENT", "Report Markdown must be non-empty and at most 64 KiB.")
    if kind == "report_markdown" and data is not None:
        raise AekoToolInputError("INVALID_ARGUMENT", "A report cannot include structured data.")
    if kind in {"ad_copy_format_proposal", "context_group_proposal"} and (markdown is not None or evidence_ids or not isinstance(data, dict)):
        raise AekoToolInputError("INVALID_ARGUMENT", "A proposal needs structured data only.")
    if kind == "ad_rule_proposal":
        if markdown is not None or not isinstance(data, dict) or set(data) != {"rule_id", "expected_version", "rationale", "changes"}:
            raise AekoToolInputError("INVALID_ARGUMENT", "A rule proposal needs its exact structured fields and no Markdown.")
        uuid_arg(data["rule_id"], "rule_id")
        if isinstance(data["expected_version"], bool) or not isinstance(data["expected_version"], int) or data["expected_version"] < 1:
            raise AekoToolInputError("INVALID_ARGUMENT", "expected_version must be a positive integer.")
        if not isinstance(data["rationale"], str) or not 1 <= len(data["rationale"].strip()) <= 2000:
            raise AekoToolInputError("INVALID_ARGUMENT", "rationale must be 1–2000 characters.")
        if not isinstance(data["changes"], dict) or not data["changes"] or set(data["changes"]) - {"name", "description", "match", "conditions", "guards"}:
            raise AekoToolInputError("INVALID_ARGUMENT", "changes must contain supported rule fields only.")
        if any(value is None for value in data["changes"].values()):
            raise AekoToolInputError("INVALID_ARGUMENT", "Rule changes must contain concrete values.")
        if not isinstance(evidence_ids, list) or len(evidence_ids) != 1:
            raise AekoToolInputError("INVALID_ARGUMENT", "A rule proposal needs its one frozen rule evidence ID.")
    if data is not None and (not isinstance(data, dict) or len(json.dumps(data).encode("utf-8")) > 64 * 1024):
        raise AekoToolInputError("INVALID_ARGUMENT", "data must be an object of at most 64 KiB.")
    if evidence_ids is not None and (not isinstance(evidence_ids, list) or len(evidence_ids) > 200):
        raise AekoToolInputError("INVALID_ARGUMENT", "evidence_ids must contain at most 200 frozen IDs.")
    evidence = [uuid_arg(eid, "evidence_id") for eid in (evidence_ids or [])]
    result = client.post(
        f"/api/action-items/{item}/outputs",
        json={
            "claim_id": claim,
            "idempotency_key": idempotency_key,
            "kind": kind,
            "schema_version": schema_version,
            "markdown": markdown,
            "data": data,
            "evidence_ids": evidence,
        },
    )
    return _block("Action output saved", result)


@mcp.tool(title="List saved AEKO action outputs", annotations=READ_ONLY)
def aeko_list_action_outputs(item_id: str) -> str:
    """Read owner-checked outputs of one saved task for reconciliation."""
    with read_boundary():
        item = _item(item_id)
        return _block("Action outputs", client.get(f"/api/action-items/{item}/outputs"))


@mcp.tool(title="Read a saved AEKO action output", annotations=READ_ONLY)
def aeko_get_action_output(item_id: str, output_id: str) -> str:
    """Read one owner-checked report, proposal or server tracking receipt."""
    with read_boundary():
        item = _item(item_id)
        output = uuid_arg(output_id, "output_id")
        return _block("Action output", client.get(f"/api/action-items/{item}/outputs/{output}"))


@mcp.tool(title="List ad copy writing formats", annotations=READ_ONLY)
def aeko_get_ad_copy_formats(domain_id: str) -> str:
    """Read built-in and current-brand custom writing formats and versions."""
    with read_boundary():
        domain = uuid_arg(domain_id, "domain_id")
        return _block("Ad copy writing formats", client.get("/api/ad-copy-formats", params={"domain_id": domain}))


@mcp.tool(title="Create a brand ad copy writing format", annotations=WRITE_ONCE)
def aeko_create_ad_copy_format(
    domain_id: str,
    name: str,
    title_instructions: str,
    description_instructions: str,
    examples: list[dict],
    language_codes: list[str],
    idempotency_key: Optional[str] = None,
) -> str:
    """Create an explicitly requested custom writing format, never an ad run.

    Built-ins are read-only. The backend checks brand ownership and validates
    the versioned definition; this operation does not upload or activate ads.
    Supply a stable idempotency key before retrying an uncertain creation.
    """
    domain = uuid_arg(domain_id, "domain_id")
    if not all(isinstance(s, str) and s.strip() for s in (name, title_instructions, description_instructions)):
        raise AekoToolInputError("INVALID_ARGUMENT", "Format name and instructions must be non-empty.")
    if not isinstance(examples, list) or not isinstance(language_codes, list) or not language_codes:
        raise AekoToolInputError("INVALID_ARGUMENT", "Examples and language codes must be explicit lists.")
    if idempotency_key is not None and (not isinstance(idempotency_key, str) or not 1 <= len(idempotency_key) <= 160):
        raise AekoToolInputError("INVALID_ARGUMENT", "idempotency_key must be 1–160 characters.")
    kwargs: dict[str, Any] = {
        "json": {
            "domain_id": domain,
            "name": name,
            "title_instructions": title_instructions,
            "description_instructions": description_instructions,
            "examples": examples,
            "language_codes": language_codes,
        }
    }
    if idempotency_key is not None:
        kwargs["headers"] = {"Idempotency-Key": idempotency_key}
    result = client.post("/api/ad-copy-formats", **kwargs)
    return _block("Ad copy writing format created", result)
