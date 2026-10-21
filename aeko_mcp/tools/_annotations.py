"""Shared MCP tool annotations for AEKO.

Every tool declares ``readOnlyHint``, ``destructiveHint`` and
``openWorldHint`` as explicit booleans, and repeats its title in
``annotations.title``. OpenAI's app review requires all three hints on every
tool; Anthropic's connector review requires the title plus the read-only and
destructive hints. Register tools with :func:`tool_spec` so the title is
written once::

    @mcp.tool(**tool_spec("List ads", READ_ONLY_EXTERNAL))

Classification rules (MCP spec, Anthropic and OpenAI review guidance):

- ``readOnlyHint``: true only when the tool changes nothing anywhere.
- ``destructiveHint``: true when the tool may modify, overwrite or delete
  existing data, change the state of something that already exists, publish
  or unpublish, change live store or ad state, or commit spend. False for
  read-only tools and for writes that only add new records. Being able to
  undo a change does not make it non-destructive.
- ``openWorldHint``: true when the tool reaches a system outside the user's
  AEKO account (a connected Cafe24/Shopify store, OpenAI Ads, Google
  Analytics, third-party web content) or has a public effect (aeko.shop, a
  public CDN URL). False when the tool only touches the user's own AEKO data,
  even though AEKO itself is a hosted service.
- ``idempotentHint``: true when repeating the same call has no further
  effect.
"""
from typing import Any

from mcp.types import ToolAnnotations


def _hints(
    *,
    read_only: bool,
    destructive: bool,
    idempotent: bool,
    open_world: bool,
) -> ToolAnnotations:
    return ToolAnnotations(
        readOnlyHint=read_only,
        destructiveHint=destructive,
        idempotentHint=idempotent,
        openWorldHint=open_world,
    )


# Reads.
READ_ONLY = _hints(read_only=True, destructive=False, idempotent=True, open_world=False)
READ_ONLY_EXTERNAL = _hints(read_only=True, destructive=False, idempotent=True, open_world=True)

# Purely additive writes: create new records, never change existing ones.
ADDITIVE = _hints(read_only=False, destructive=False, idempotent=True, open_world=False)
ADDITIVE_ONCE = _hints(read_only=False, destructive=False, idempotent=False, open_world=False)
ADDITIVE_EXTERNAL = _hints(read_only=False, destructive=False, idempotent=True, open_world=True)
ADDITIVE_ONCE_EXTERNAL = _hints(
    read_only=False, destructive=False, idempotent=False, open_world=True
)

# Writes that modify, replace, delete, publish, change state or spend.
DESTRUCTIVE = _hints(read_only=False, destructive=True, idempotent=False, open_world=False)
DESTRUCTIVE_IDEMPOTENT = _hints(
    read_only=False, destructive=True, idempotent=True, open_world=False
)
DESTRUCTIVE_EXTERNAL = _hints(
    read_only=False, destructive=True, idempotent=False, open_world=True
)
DESTRUCTIVE_IDEMPOTENT_EXTERNAL = _hints(
    read_only=False, destructive=True, idempotent=True, open_world=True
)


def tool_spec(title: str, annotations: ToolAnnotations, **kwargs: Any) -> dict[str, Any]:
    """Return ``mcp.tool`` keyword arguments with the title in both places."""
    return {
        "title": title,
        "annotations": annotations.model_copy(update={"title": title}),
        **kwargs,
    }
