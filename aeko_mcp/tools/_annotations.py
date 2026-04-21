"""Shared MCP tool annotations for AEKO.

Centralized so every tool file picks the same preset and Claude Desktop can
offer "always allow" on read-only tools uniformly. Six presets cover the
whole surface:

- READ_ONLY         — GET-wrapping tools that hit the AEKO backend
- WRITE             — idempotent PATCH/POST (same args → same state)
- WRITE_ONCE        — non-idempotent POST (creates new rows, generates, etc.)
- DESTRUCTIVE       — DELETE / revert / irreversible state changes
- LOCAL_READ_ONLY   — local filesystem or external URL reads (no AEKO call)
- LOCAL_WRITE       — local filesystem writes (saves content to disk)

Desktop uses ``readOnlyHint`` to decide the approval chrome: True ⇒ user can
check "always allow for this tool". ``destructiveHint`` surfaces a stronger
warning. ``openWorldHint=True`` flags that the tool reaches outside the
local environment (i.e. hits AEKO or an external URL).
"""
from mcp.types import ToolAnnotations


READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    idempotentHint=True,
    openWorldHint=True,
)

WRITE = ToolAnnotations(
    readOnlyHint=False,
    idempotentHint=True,
    destructiveHint=False,
    openWorldHint=True,
)

WRITE_ONCE = ToolAnnotations(
    readOnlyHint=False,
    idempotentHint=False,
    destructiveHint=False,
    openWorldHint=True,
)

DESTRUCTIVE = ToolAnnotations(
    readOnlyHint=False,
    idempotentHint=False,
    destructiveHint=True,
    openWorldHint=True,
)

LOCAL_READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    idempotentHint=True,
    openWorldHint=False,
)

LOCAL_WRITE = ToolAnnotations(
    readOnlyHint=False,
    idempotentHint=True,
    destructiveHint=False,
    openWorldHint=False,
)
