"""FastMCP server composition."""

from fastmcp import FastMCP
from sqlalchemy.orm import Session, sessionmaker

from attendance_crmt.tools import register_catalog_tools

SERVER_NAME = "attendance-crmt"
SERVER_INSTRUCTIONS = "A modular FastMCP server scaffold."


def create_server(session_factory: sessionmaker[Session] | None = None) -> FastMCP:
    """Create the application server and register its tools."""
    server = FastMCP(name=SERVER_NAME, instructions=SERVER_INSTRUCTIONS)
    register_catalog_tools(server, session_factory=session_factory)
    return server


mcp = create_server()
