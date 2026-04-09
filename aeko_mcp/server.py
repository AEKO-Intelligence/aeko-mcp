import atexit

from mcp.server.fastmcp import FastMCP
from .client import AekoClient

mcp = FastMCP("AEKO", instructions="AI Engine Optimization for Cross-Border Commerce")
client = AekoClient()
atexit.register(client.close)

# Import tool modules to register all tools with the mcp instance
from .tools import visibility, content, product, suggestions, suggestions_v2, research, preview, images, generate, report, citability, aeko_score, local_content, campaigns, content_recommendations, store_write  # noqa: E402, F401


if __name__ == "__main__":
    mcp.run()
