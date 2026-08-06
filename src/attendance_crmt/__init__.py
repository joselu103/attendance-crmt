"""attendance-crmt FastMCP server package."""

from attendance_crmt.server import mcp


def main() -> None:
    """Run the FastMCP server through stdio"""
    mcp.run(transport="stdio")


__all__ = ["main", "mcp"]
