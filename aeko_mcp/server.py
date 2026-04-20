import argparse
import atexit
import contextlib
import os
from collections.abc import AsyncIterator

from mcp.server.fastmcp import FastMCP

from .client import AekoClient


def _env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _build_mcp() -> FastMCP:
    server = FastMCP(
        "AEKO",
        instructions="AI Engine Optimization for Cross-Border Commerce",
        stateless_http=_env_flag("AEKO_MCP_STATELESS_HTTP", True),
        json_response=_env_flag("AEKO_MCP_JSON_RESPONSE", True),
    )
    # Default to "/" so an embedding ASGI app's own mount prefix (e.g. app.mount("/mcp", ...))
    # is not doubled. Override via AEKO_MCP_STREAMABLE_HTTP_PATH when running standalone.
    server.settings.streamable_http_path = os.environ.get("AEKO_MCP_STREAMABLE_HTTP_PATH", "/")
    return server


mcp = _build_mcp()
client = AekoClient()
atexit.register(client.close)

# Import tool modules to register all tools with the mcp instance
from .tools import visibility, content, product, suggestions, suggestions_v2, research, preview, images, generate, report, citability, aeko_score, local_content, campaigns, content_recommendations, store_write, pdp, action_plan, brand_kit  # noqa: E402, F401


@contextlib.asynccontextmanager
async def mcp_lifespan() -> AsyncIterator[None]:
    """Lifespan helper for mounting AEKO MCP into an existing ASGI app."""
    async with mcp.session_manager.run():
        yield


def create_streamable_http_app(
    streamable_http_path: str | None = None,
    issuer_url: str | None = None,
):
    """Return an ASGI app that serves AEKO MCP over streamable HTTP.

    ``issuer_url`` is the public base URL where this MCP is reachable
    (e.g. ``https://aeko.ai``). When supplied, any 401 response from the
    MCP app gets a ``WWW-Authenticate`` challenge pointing at
    ``<issuer_url>/.well-known/oauth-protected-resource`` so MCP clients
    can start OAuth discovery per the spec.
    """
    if streamable_http_path is not None:
        mcp.settings.streamable_http_path = streamable_http_path
    app = mcp.streamable_http_app()

    challenge_value = (
        f'Bearer realm="aeko", resource_metadata="{issuer_url.rstrip("/")}'
        f'/.well-known/oauth-protected-resource"'
    ).encode() if issuer_url else None

    async def asgi_app(scope, receive, send):
        if scope["type"] != "http":
            await app(scope, receive, send)
            return

        method = scope.get("method", "").upper()
        headers = dict(scope.get("headers", []))
        raw_auth = headers.get(b"authorization", b"").decode()
        token_value = raw_auth[7:].strip() if raw_auth.lower().startswith("bearer ") else None

        # Pre-flight gate: without a bearer, return 401 + WWW-Authenticate
        # so MCP clients can discover the OAuth AS via RFC 9728 and start
        # the browser flow. FastMCP's own handshake is public by default,
        # which would otherwise let clients sail past connect without
        # running OAuth and only hit auth errors mid-tool-call.
        #
        # OPTIONS requests (CORS preflight) are allowed through unauth so
        # browser-based MCP clients can still negotiate headers.
        if (
            challenge_value is not None
            and method != "OPTIONS"
            and not token_value
        ):
            await send({
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"www-authenticate", challenge_value),
                ],
            })
            await send({
                "type": "http.response.body",
                "body": b'{"error":"unauthorized","error_description":"Bearer token required for MCP access"}',
            })
            return

        ctx_token = client.set_request_auth_token(token_value or None)

        async def send_with_challenge(message):
            if (
                challenge_value is not None
                and message.get("type") == "http.response.start"
                and message.get("status") == 401
            ):
                response_headers = list(message.get("headers", []))
                if not any(h[0].lower() == b"www-authenticate" for h in response_headers):
                    response_headers.append((b"www-authenticate", challenge_value))
                    message = {**message, "headers": response_headers}
            await send(message)

        try:
            await app(scope, receive, send_with_challenge)
        finally:
            client.reset_request_auth_token(ctx_token)

    return asgi_app


def run_server(
    transport: str = "streamable-http",
    host: str | None = None,
    port: int | None = None,
    mount_path: str | None = None,
) -> None:
    kwargs: dict[str, object] = {"transport": transport}
    if host is not None:
        kwargs["host"] = host
    if port is not None:
        kwargs["port"] = port
    if mount_path is not None:
        kwargs["mount_path"] = mount_path
    mcp.run(**kwargs)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the AEKO MCP server")
    parser.add_argument(
        "--transport",
        choices=("streamable-http",),
        default=os.environ.get("AEKO_MCP_TRANSPORT", "streamable-http"),
        help="MCP transport to run. AEKO is designed for hosted streamable HTTP.",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("AEKO_MCP_HOST"),
        help="Host for streamable HTTP transport.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ["AEKO_MCP_PORT"]) if os.environ.get("AEKO_MCP_PORT") else None,
        help="Port for streamable HTTP transport.",
    )
    parser.add_argument(
        "--mount-path",
        default=os.environ.get("AEKO_MCP_MOUNT_PATH"),
        help="Optional mount path override when running an HTTP transport.",
    )
    args = parser.parse_args()
    run_server(
        transport=args.transport,
        host=args.host,
        port=args.port,
        mount_path=args.mount_path,
    )


if __name__ == "__main__":
    main()
