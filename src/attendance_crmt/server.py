"""FastMCP server composition."""

from fastmcp import FastMCP

from attendance_crmt.tools import register_echo_tool

SERVER_NAME = "attendance-crmt"
SERVER_INSTRUCTIONS = "A modular FastMCP server scaffold."


def create_server() -> FastMCP:
    """Create the application server and register its tools."""
    server = FastMCP(name=SERVER_NAME, instructions=SERVER_INSTRUCTIONS)
    register_echo_tool(server)
    return server


mcp = create_server()
