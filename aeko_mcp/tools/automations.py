"""Manual, owner-scoped access to the reviewed AEKO automation starters.

This adapter deliberately exposes only three reviewed templates. Instances are
created disabled with manual cadence; ad delivery is always held for review.
Running an existing manual instance is an explicit write and uses the caller's
idempotency key verbatim. No run credential or internal runtime token is exposed.
"""
import json
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from ..client import AekoAPIError
from ..server import client, mcp
from ._annotations import READ_ONLY, WRITE_ONCE
from ._structured import AekoToolError, AekoToolInputError, api_error

AutomationKey = Literal[
    "review_context_workflow",
    "ad_performance_shortlist",
    "review_based_ads",
]


class ReviewContextParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_external_ref: str | None = Field(default=None, min_length=1, max_length=1000)
    review_language: str | None = Field(default=None, min_length=2, max_length=16)
    filter_text: None = None


class AdPerformanceParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ad_account_id: UUID
    ad_group_id: UUID
    target_kpi: Literal["ctr", "cpc"]
    percentile: int = Field(default=20, ge=1, le=50)
    min_impressions: int = Field(default=3000, ge=1, le=1_000_000_000)
    lookback_days: int = Field(default=14, ge=1, le=90)
    min_age_days: int = Field(default=7, ge=0, le=90)
    filter_text: None = None


class ContextFilter(BaseModel):
    model_config = ConfigDict(extra="forbid")
    min_score: int | None = Field(default=None, ge=0, le=100)
    has_ads: bool | None = None
    product_external_ref: str | None = None
    created_since: datetime | None = None
    created_within_hours: int | None = Field(default=None, ge=1, le=2160)

    @model_validator(mode="after")
    def exclusive_created_window(self):
        if self.created_since is not None and self.created_within_hours is not None:
            raise ValueError("created_since and created_within_hours are mutually exclusive")
        return self


class ReviewBasedAdsParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    creative_strategy: Literal["auto", "context", "conversational"] = "context"
    filter: ContextFilter = Field(default_factory=ContextFilter)
    filter_text: str | None = None
    ad_account_id: UUID
    campaign_id: UUID | None = None
    target_language: str = Field(min_length=2, max_length=16)
    target_market: str = Field(min_length=2, max_length=8)
    ad_group_name: str = Field(min_length=3, max_length=1000)
    max_bid_micros: int = Field(ge=1, le=100_000_000)


_PARAM_MODELS: dict[str, type[BaseModel]] = {
    "review_context_workflow": ReviewContextParams,
    "ad_performance_shortlist": AdPerformanceParams,
    "review_based_ads": ReviewBasedAdsParams,
}


def _uuid(value: str, field: str) -> str:
    try:
        return str(UUID(value))
    except (ValueError, TypeError, AttributeError):
        raise AekoToolInputError("INVALID_INPUT", f"{field} must be a UUID.") from None


def _params(key: str, params: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(params, dict):
        raise AekoToolInputError("INVALID_INPUT", "params must be an object.")
    model = _PARAM_MODELS[key]
    try:
        return model.model_validate(params).model_dump(mode="json", exclude_none=True)
    except ValidationError as exc:
        errors = exc.errors(include_url=False, include_context=False)
        safe = [{"field": ".".join(str(x) for x in e["loc"]), "type": e["type"]} for e in errors[:12]]
        raise AekoToolInputError("INVALID_INPUT", f"Invalid {key} params: {json.dumps(safe)}") from None


def _call(method, *args, mutation: bool = False, **kwargs):
    try:
        return method(*args, **kwargs)
    except AekoAPIError as exc:
        if not mutation:
            state = "not_attempted"
        elif not exc.request_sent:
            state = "not_attempted"
        elif exc.http_status is not None and exc.http_status < 500:
            state = "rejected"
        else:
            state = "unknown"
        raise api_error(exc, mutation_state=state) from None


def _json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)


def _definition_view(item: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "key", "version", "name_ko", "name_en", "purpose_ko", "automation_class",
        "default_on", "single_instance", "default_cadence", "cadences", "param_schema",
        "destinations", "required_inputs", "model_classes",
    )
    result = {key: item.get(key) for key in fields}
    stages = item.get("stages")
    if isinstance(stages, list):
        result["stages"] = [
            {key: stage.get(key) for key in ("stage_type", "name", "handler")}
            for stage in stages if isinstance(stage, dict)
        ]
    return result


def _instance_view(item: dict[str, Any]) -> dict[str, Any]:
    return {key: item.get(key) for key in (
        "id", "automation_key", "name", "enabled", "cadence", "params",
        "destination", "model_class", "last_run_at", "next_due_at", "last_run",
    )}


def _run_view(data: dict[str, Any]) -> dict[str, Any]:
    stages = data.get("stages") if isinstance(data.get("stages"), list) else []
    items = data.get("items") if isinstance(data.get("items"), list) else []
    allowed_snapshot = {
        "display_label", "ad_id", "target_kpi", "metric_value", "currency",
        "impressions", "clicks", "spend_micros", "date_from", "date_to", "report_refreshed_at",
    }
    safe_items = []
    for item in items[:500]:
        if not isinstance(item, dict):
            continue
        row = {key: item.get(key) for key in ("id", "item_type", "item_id", "state", "summary", "output", "verdicts")}
        strategy = item.get("creative_strategy")
        if isinstance(strategy, dict) and isinstance(strategy.get("key"), str) and isinstance(strategy.get("reason"), str):
            reference_keys = ("document_id", "version_id", "version", "key", "subkind", "package_digest", "package_slug", "applies_to")
            if all(isinstance(strategy.get(kind), dict) for kind in ("skill_ref", "eval_ref")):
                row["creative_strategy"] = {
                    "key": strategy["key"][:160], "reason": strategy["reason"][:240],
                    **{kind: {key: strategy[kind][key] for key in reference_keys
                              if key in strategy[kind] and isinstance(strategy[kind][key], (str, int))
                              and not isinstance(strategy[kind][key], bool)}
                       for kind in ("skill_ref", "eval_ref")},
                }
        snapshot = item.get("snapshot")
        if isinstance(snapshot, dict):
            row["snapshot"] = {key: value for key, value in snapshot.items() if key in allowed_snapshot}
        safe_items.append(row)
    stage_rows = []
    detail_keys = (
        "target_kpi", "direction", "eligible_count", "selected_count", "minimum_cohort",
        "boundary_tie_count", "reason", "percentile", "ad_changes", "date_from", "date_to",
        "currency", "timezone", "ad_group_id", "source",
    )
    for stage in stages:
        if not isinstance(stage, dict):
            continue
        row = {key: stage.get(key) for key in (
            "index", "stage_type", "name", "status", "input_count", "output_count",
            "removed_count", "removed_by_reason", "duration_ms",
        )}
        details = stage.get("details")
        if isinstance(details, dict):
            row["details"] = {key: details.get(key) for key in detail_keys if key in details}
            ids = details.get("eligible_ad_ids")
            if isinstance(ids, list):
                row["details"]["eligible_ad_ids"] = ids[:200]
                row["details"]["eligible_ad_ids_truncated"] = len(ids) > 200
            exclusions = details.get("exclusions")
            if isinstance(exclusions, list):
                row["details"]["exclusions"] = [
                    {key: entry.get(key) for key in ("ad_id", "name", "reason")}
                    for entry in exclusions[:200] if isinstance(entry, dict)
                ]
                row["details"]["exclusions_truncated"] = len(exclusions) > 200
        stage_rows.append(row)
    return {
        key: data.get(key) for key in (
            "id", "instance_id", "automation_key", "trigger", "mode", "status",
            "partial_reason", "credits_used", "queued_at", "started_at", "finished_at",
            "items_by_state", "items_total",
        )
    } | {
        "items_truncated": isinstance(data.get("items_total"), int) and data["items_total"] > len(safe_items),
        "stages": stage_rows,
        "items": safe_items,
        "output_refs": [
            {key: ref.get(key) for key in ("type", "id", "count")}
            for ref in data.get("output_refs", []) if isinstance(ref, dict)
        ],
        "removed": [
            {"reason": group.get("reason"), "count": group.get("count")}
            for group in data.get("removed", []) if isinstance(group, dict)
        ],
    }


@mcp.tool(title="List automation templates and instances", annotations=READ_ONLY)
def aeko_list_automations(domain_id: str) -> str:
    """List the three supported starter templates and this domain's instances.

    Backend authorization scopes results to the authenticated owner and domain.
    MCP OAuth/agent-token discovery is read-only and does not provision managed
    defaults; the AEKO dashboard handles managed default-instance provisioning.
    """
    domain = _uuid(domain_id, "domain_id")
    data = _call(client.get, "/api/automations", params={"domain_id": domain})
    definitions = data.get("definitions", []) if isinstance(data, dict) else []
    instances = data.get("instances", []) if isinstance(data, dict) else []
    keys = set(_PARAM_MODELS)
    return _json({
        "domain_id": domain,
        "templates": [_definition_view(d) for d in definitions if isinstance(d, dict) and d.get("key") in keys],
        "instances": [_instance_view(i) for i in instances if isinstance(i, dict) and i.get("automation_key") in keys],
    })


@mcp.tool(title="Resolve automation setup contract", annotations=READ_ONLY)
def aeko_resolve_automation_contract(
    domain_id: str,
    automation_key: AutomationKey,
    params: dict[str, Any],
) -> str:
    """Check a manual starter setup using AEKO's validators without saving or running it."""
    domain = _uuid(domain_id, "domain_id")
    key = str(automation_key)
    normalized = _params(key, params)
    body: dict[str, Any] = {"name": "", "params": normalized, "cadence": "manual", "model_class": "basic"}
    if key == "review_based_ads":
        body["destination"] = {"policy": "hold"}
    data = _call(client.post, f"/api/automations/{key}/resolve-contract", json=body,
                 params={"domain_id": domain})
    if not isinstance(data, dict):
        raise AekoToolError("INVALID_BACKEND_RESPONSE", "AEKO returned an unexpected contract response.")
    return _json({key: data.get(key) for key in ("ready", "reason_code", "job_contract", "credits_remaining")})


@mcp.tool(title="Create manual automation instance", annotations=WRITE_ONCE)
def aeko_create_automation_instance(
    domain_id: str,
    automation_key: AutomationKey,
    name: str,
    params: dict[str, Any],
) -> str:
    """Save a disabled, manual instance of a supported starter template.

    Creation never runs the automation. Cadence is fixed to manual and the
    review-based ads template always uses destination policy hold.
    """
    domain = _uuid(domain_id, "domain_id")
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 160:
        raise AekoToolInputError("INVALID_INPUT", "name must contain 1 to 160 characters.")
    key = str(automation_key)
    normalized = _params(key, params)
    body: dict[str, Any] = {"name": name.strip(), "params": normalized, "cadence": "manual", "model_class": "basic"}
    if key == "review_based_ads":
        body["destination"] = {"policy": "hold"}
    data = _call(client.post, f"/api/automations/{key}/instances", json=body,
                 params={"domain_id": domain}, mutation=True)
    if not isinstance(data, dict):
        raise AekoToolError("INVALID_BACKEND_RESPONSE", "AEKO returned an unexpected instance response.", mutation_state="unknown")
    return _json(_instance_view(data))


@mcp.tool(title="Run manual automation instance", annotations=WRITE_ONCE)
def aeko_run_automation_instance(domain_id: str, instance_id: str, idempotency_key: str) -> str:
    """Queue one existing supported manual instance exactly once per idempotency key.

    Reuse the exact same key only to recover the same request after an uncertain result.
    The guarded backend route atomically requires a supported starter, manual cadence,
    basic model, and a hold destination for ads. The adapter does not retry.
    """
    domain = _uuid(domain_id, "domain_id")
    instance = _uuid(instance_id, "instance_id")
    if (not isinstance(idempotency_key, str) or not idempotency_key
            or len(idempotency_key) > 255 or idempotency_key != idempotency_key.strip()):
        raise AekoToolInputError("INVALID_INPUT", "idempotency_key must contain 1 to 255 characters without surrounding whitespace.")
    data = _call(client.post, f"/api/automations/instances/{instance}/run-starter",
                 params={"domain_id": domain}, headers={"Idempotency-Key": idempotency_key}, mutation=True)
    if not isinstance(data, dict):
        raise AekoToolError("INVALID_BACKEND_RESPONSE", "AEKO returned an unexpected run response.", mutation_state="unknown")
    return _json({key: data.get(key) for key in ("run_id", "poll_url", "mode")})


@mcp.tool(title="Read automation run results", annotations=READ_ONLY)
def aeko_get_automation_run(domain_id: str, run_id: str) -> str:
    """Read status, stages, and bounded safe result fields for one owned automation run."""
    domain = _uuid(domain_id, "domain_id")
    run = _uuid(run_id, "run_id")
    data = _call(client.get, f"/api/automations/runs/{run}", params={"domain_id": domain})
    if not isinstance(data, dict):
        raise AekoToolError("INVALID_BACKEND_RESPONSE", "AEKO returned an unexpected run response.")
    if data.get("automation_key") not in _PARAM_MODELS:
        raise AekoToolInputError("RUN_NOT_SUPPORTED", "Run is not a supported starter automation.")
    return _json(_run_view(data))
