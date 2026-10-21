"""Server identity and instructions that every MCP client sees at initialize."""

import json
from importlib.metadata import version

import anyio
import httpx
from mcp.shared.memory import create_connected_server_and_client_session

from aeko_mcp import server


def _initialize():
    async def run():
        async with create_connected_server_and_client_session(server.mcp._mcp_server) as session:
            return await session.initialize()

    return anyio.run(run)


def test_server_info_reports_aeko_package_version_not_the_sdk():
    result = _initialize()

    assert result.serverInfo.name == "AEKO"
    assert result.serverInfo.version == version("aeko-mcp")
    assert result.serverInfo.version != version("mcp")


def test_instructions_fit_the_first_512_characters_and_name_no_client():
    instructions = _initialize().instructions

    assert instructions == server.SERVER_INSTRUCTIONS
    assert len(instructions) <= 512
    # Key cross-tool guidance must be inside the window clients read.
    for phrase in ("aeko_list_domains", "explicit confirmation", "claim", "complete"):
        assert phrase in instructions
    # Platform-neutral: no "connect AEKO to <client>" or "<client> can ..." framing.
    lowered = instructions.lower()
    assert "connect aeko to" not in lowered
    assert "claude can" not in lowered and "chatgpt can" not in lowered


def test_version_override_targets_the_low_level_server():
    # FastMCP 1.11-1.15 keeps a low-level server whose ``version`` feeds
    # serverInfo; the override must land there, not on a new attribute.
    assert server.mcp._mcp_server.version == server.package_version()
    assert server.mcp._mcp_server.create_initialization_options().server_version == (
        server.package_version()
    )


def test_initialize_over_http_reports_package_identity(monkeypatch):
    # A fresh session manager: the SDK allows one run() per manager.
    monkeypatch.setattr(server.mcp, "_session_manager", None)
    seen: list[str] = []

    async def accept(token: str) -> bool:
        seen.append(token)
        return True

    app = server.create_streamable_http_app(
        issuer_url="https://aeko.example", token_validator=accept
    )

    async def run():
        async with server.mcp_lifespan():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://mcp.test"
            ) as http:
                return await http.post(
                    "/",
                    headers={
                        "Authorization": "Bearer aeko_ot1_live",
                        "Accept": "application/json, text/event-stream",
                        "MCP-Protocol-Version": "2025-06-18",
                    },
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2025-06-18",
                            "capabilities": {},
                            "clientInfo": {"name": "identity-test", "version": "0"},
                        },
                    },
                )

    response = anyio.run(run)

    assert response.status_code == 200, response.text
    result = json.loads(response.text)["result"]
    assert result["serverInfo"] == {"name": "AEKO", "version": server.package_version()}
    assert result["instructions"] == server.SERVER_INSTRUCTIONS
    assert seen == ["aeko_ot1_live"]
