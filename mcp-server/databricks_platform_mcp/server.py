"""
Databricks Platform MCP Server

A FastMCP server that exposes Databricks provisioning operations as MCP tools.
Wraps functions from databricks-platform-core.
"""

from fastmcp import FastMCP

mcp = FastMCP("databricks-platform")

# Import and register provisioning tools (side-effect: @mcp.tool decorators)
from .tools import provisioning  # noqa: F401, E402


def main():
    mcp.run()
