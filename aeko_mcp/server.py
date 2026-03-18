import atexit

from mcp.server.fastmcp import FastMCP
from .client import AekoClient

mcp = FastMCP("AEKO", instructions="AI Engine Optimization for Cross-Border Commerce")
client = AekoClient()
atexit.register(client.close)

# Import tool modules to register all tools with the mcp instance
from .tools import visibility, content, product, suggestions, research, preview, images, generate, report, citability, geo_score, local_content  # noqa: E402, F401


if __name__ == "__main__":
    mcp.run()
