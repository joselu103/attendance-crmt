"""Example FastMCP tool registrations."""

from fastmcp import FastMCP


def register_echo_tool(server: FastMCP) -> None:
    """Register the example echo tool on a FastMCP server."""

    @server.tool()
    def echo(message: str) -> str:
        """Return a message unchanged."""
        return message
