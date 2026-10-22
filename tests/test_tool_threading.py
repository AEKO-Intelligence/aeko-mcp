"""Synchronous tools run off the event loop and keep the request's bearer token.

Embedded in the backend, a tool's HTTP call returns to the same process. If the
tool held the event loop, that request could not be served and concurrent calls
stalled until the HTTP timeout (seen in production as 502s and killed workers).
"""

import threading

import anyio
from mcp.shared.memory import create_connected_server_and_client_session

from aeko_mcp import server
from aeko_mcp.tools import research


def test_sync_tool_leaves_the_event_loop_free_and_sees_the_request_token(monkeypatch):
    loop_answered = threading.Event()
    seen = {}

    def fake_get(path, params=None):
        seen["thread"] = threading.get_ident()
        seen["headers"] = server.client._headers()
        # Wait for a coroutine scheduled on the loop. On the loop thread this would never come.
        seen["loop_free"] = loop_answered.wait(timeout=5)
        return [{"id": "tp-1", "raw_prompt": "prompt"}]

    monkeypatch.setattr(research.client, "get", fake_get)

    async def answer_from_the_loop():
        await anyio.sleep(0.05)
        loop_answered.set()

    async def run():
        ctx = server.client.set_request_auth_token("request-token")
        try:
            async with create_connected_server_and_client_session(server.mcp._mcp_server) as session:
                async with anyio.create_task_group() as tg:
                    tg.start_soon(answer_from_the_loop)
                    result = await session.call_tool("aeko_get_tracked_prompts", {})
        finally:
            server.client.reset_request_auth_token(ctx)
        return threading.get_ident(), result

    loop_thread, result = anyio.run(run)

    assert result.isError is False
    assert seen["loop_free"] is True
    assert seen["thread"] != loop_thread
    assert seen["headers"] == {"Authorization": "Bearer request-token"}


def test_registered_tools_are_async_but_module_functions_stay_sync(monkeypatch):
    monkeypatch.setattr(research.client, "get", lambda path, params=None: [])
    tool = server.mcp._tool_manager.get_tool("aeko_get_tracked_prompts")

    assert tool.is_async is True
    assert tool.fn.__wrapped__ is research.aeko_get_tracked_prompts
    assert isinstance(research.aeko_get_tracked_prompts(), str)
