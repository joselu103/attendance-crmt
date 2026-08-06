"""Tool modules exposed by the FastMCP server."""

from attendance_crmt.tools.catalog import register_catalog_tools
from attendance_crmt.tools.echo import register_echo_tool

__all__ = ["register_catalog_tools", "register_echo_tool"]
