"""attendance-crmt FastMCP server package."""

from attendance_crmt.server import mcp


def main() -> None:
    """Run the FastMCP server through streamable-http."""
    mcp.run(transport="streamable-http")


__all__ = ["main", "mcp"]
