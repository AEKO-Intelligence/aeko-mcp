"""Directory-review contract for every registered tool.

OpenAI's app review requires explicit boolean readOnlyHint, destructiveHint
and openWorldHint on every tool; Anthropic's connector review requires the
title and the read-only/destructive hints. Both reject descriptions that
reference tools the user does not have, pull instructions from elsewhere, or
mismatch what the tool does. These checks run against the tools/list a client
actually receives.
"""

import ast
import inspect
import re
import textwrap

import anyio
import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import ToolAnnotations

from aeko_mcp import server
from aeko_mcp.tools import _structured
from aeko_mcp.tools._annotations import READ_ONLY, tool_spec

MAX_DESCRIPTION_CHARS = 1024

# Tools that overwrite live data, change spend, publish, or change existing state.
MUST_BE_DESTRUCTIVE = {
    "aeko_update_ad_group",
    "aeko_update_ad_creative",
    "aeko_update_ad_rule",
    "aeko_update_product_description",
    "aeko_update_product_page",
    "aeko_update_product_tags",
    "aeko_update_product_meta",
    "aeko_inject_products",
    "aeko_inject_reviews",
    "aeko_publish_content_variation",
    "aeko_update_markets",
    "aeko_update_content_variation",
    "aeko_update_context",
    "aeko_update_context_translation",
    "aeko_sync_store",
    "aeko_sync_feed",
    "aeko_select_ga4_property",
    "aeko_complete_action_item",
}
# Name patterns the review rules call out explicitly.
DESTRUCTIVE_NAME = re.compile(
    r"^aeko_(set_\w+_state|delete_\w+|revert_\w+|unpublish_\w+|untrack_\w+|dismiss_\w+|archive_\w+)$"
)

# Reaches Cafe24/Shopify, OpenAI Ads, Google Analytics or aeko.shop, or has a public effect.
MUST_BE_OPEN_WORLD = {
    "aeko_get_product_description",
    "aeko_update_product_description",
    "aeko_update_product_tags",
    "aeko_update_product_meta",
    "aeko_update_product_page",
    "aeko_revert_store_write",
    "aeko_sync_store",
    "aeko_inject_products",
    "aeko_inject_reviews",
    "aeko_publish_content_variation",
    "aeko_unpublish_content",
    "aeko_request_media_upload",
    "aeko_sync_ga4",
    "aeko_select_ga4_property",
    "aeko_list_ga4_properties",
    "aeko_sync_feed",
    "aeko_get_ad_insights",
    "aeko_get_product_insights",
    "aeko_create_ad_group_from_context",
    "aeko_update_ad_group",
    "aeko_update_ad_creative",
    "aeko_set_campaign_state",
    "aeko_set_ad_group_state",
    "aeko_set_ad_state",
}
# Confined to the user's own AEKO data.
MUST_BE_CLOSED_WORLD = {
    "aeko_list_domains",
    "aeko_get_visibility_summary",
    "aeko_get_tracked_prompts",
    "aeko_track_prompt",
    "aeko_list_action_items",
    "aeko_claim_action_item",
    "aeko_list_contexts",
    "aeko_create_context",
    "aeko_list_store_products",
    "aeko_list_store_integrations",
    "aeko_list_store_writes",
    "aeko_list_campaigns",
    "aeko_get_conversion_insights",
    "aeko_save_content_variation",
    "aeko_connect_store",
    "aeko_read_brand_package_file",
}

# Phrases that tell the model to load and execute server-hosted instructions.
INSTRUCTION_PULL_PHRASES = (
    "before execution",
    "executing the skill",
    "read all required instructions",
    "before using it as brand knowledge",
)


def _served_tools():
    async def run():
        async with create_connected_server_and_client_session(server.mcp._mcp_server) as session:
            return (await session.list_tools()).tools

    return anyio.run(run)


TOOLS = _served_tools()
TOOL_IDS = [tool.name for tool in TOOLS]
BY_NAME = {tool.name: tool for tool in TOOLS}


def _raw_docstring(name: str) -> str:
    """The docstring as Python <= 3.12 exposes it in __doc__ (not dedented).

    Python 3.13 strips docstring indentation at compile time, but production
    runs Python 3.12, where FastMCP sends the indented text as the description.
    """
    fn = server.mcp._tool_manager.get_tool(name).fn
    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef))
    return ast.get_docstring(node, clean=False) or ""


def test_registry_is_not_empty():
    assert len(TOOLS) >= 100


@pytest.mark.parametrize("tool", TOOLS, ids=TOOL_IDS)
def test_every_tool_declares_explicit_boolean_hints(tool):
    annotations = tool.annotations
    assert annotations is not None
    dumped = annotations.model_dump(exclude_none=True)
    for hint in ("readOnlyHint", "destructiveHint", "openWorldHint", "idempotentHint"):
        assert hint in dumped, f"{tool.name} omits {hint}"
        assert type(dumped[hint]) is bool, f"{tool.name}.{hint} is not a bool"
    if annotations.readOnlyHint:
        assert annotations.destructiveHint is False


@pytest.mark.parametrize("tool", TOOLS, ids=TOOL_IDS)
def test_every_tool_repeats_its_title_in_annotations(tool):
    assert tool.title and tool.title.strip()
    assert tool.annotations.title == tool.title


@pytest.mark.parametrize("tool", TOOLS, ids=TOOL_IDS)
def test_descriptions_fit_the_directory_limit(tool):
    assert tool.description and tool.description.strip()
    assert len(tool.description) <= MAX_DESCRIPTION_CHARS
    raw = _raw_docstring(tool.name)
    assert len(raw) <= MAX_DESCRIPTION_CHARS, f"{tool.name} is {len(raw)} chars on Python 3.12"


@pytest.mark.parametrize("tool", TOOLS, ids=TOOL_IDS)
def test_descriptions_do_not_reference_plugin_slash_commands(tool):
    assert "/aeko-" not in tool.description


@pytest.mark.parametrize("tool", TOOLS, ids=TOOL_IDS)
def test_descriptions_do_not_pull_instructions_or_promote_upgrades(tool):
    lowered = tool.description.lower()
    for phrase in INSTRUCTION_PULL_PHRASES:
        assert phrase not in lowered, f"{tool.name}: {phrase!r}"
    assert "upgrade" not in lowered


@pytest.mark.parametrize("tool", TOOLS, ids=TOOL_IDS)
def test_descriptions_do_not_name_internal_symbols(tool):
    for symbol in (
        "_upload_local_images_for_aeko_shop",
        "AekoShopPublisher",
        "aeko_content_drafts",
        "MediaPresignRequest",
        "UserPrompts",
        "aeko_get_cited_sources",
        "aeko_get_metrics",
        "WebFetch",
    ):
        assert symbol not in tool.description, f"{tool.name}: {symbol}"


def test_campaign_budget_tool_is_not_registered():
    """Product decision: MCP and skills do not set ad budgets."""
    assert "aeko_update_campaign_budget" not in BY_NAME
    for tool in TOOLS:
        assert "aeko_update_campaign_budget" not in (tool.description or "")


def test_known_destructive_tools_are_flagged():
    expected = MUST_BE_DESTRUCTIVE | {name for name in BY_NAME if DESTRUCTIVE_NAME.match(name)}
    assert MUST_BE_DESTRUCTIVE <= set(BY_NAME)
    not_flagged = sorted(
        name for name in expected if BY_NAME[name].annotations.destructiveHint is not True
    )
    assert not_flagged == []


def test_open_world_hint_tracks_external_reach():
    assert MUST_BE_OPEN_WORLD | MUST_BE_CLOSED_WORLD <= set(BY_NAME)
    assert sorted(n for n in MUST_BE_OPEN_WORLD if not BY_NAME[n].annotations.openWorldHint) == []
    assert sorted(n for n in MUST_BE_CLOSED_WORLD if BY_NAME[n].annotations.openWorldHint) == []


def test_tool_spec_copies_the_preset_with_the_title():
    spec = tool_spec("Example title", READ_ONLY, structured_output=True)
    assert spec["title"] == "Example title"
    assert spec["structured_output"] is True
    assert isinstance(spec["annotations"], ToolAnnotations)
    assert spec["annotations"].title == "Example title"
    assert READ_ONLY.title is None


def test_plan_messages_state_plan_scope_without_upgrade_wording():
    """OpenAI plugin guidelines: explain a feature is not in the current plan; do not upsell."""
    messages = [
        _structured._STATUS_ERRORS[402][1],
        _structured._BACKEND_CODE_MESSAGES["TIER_REQUIRED"],
    ]
    for message in messages:
        assert "not included in your current AEKO plan" in message
        assert "upgrade" not in message.lower()
        assert "higher" not in message.lower()
