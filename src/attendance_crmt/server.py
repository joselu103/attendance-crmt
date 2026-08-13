"""FastMCP server composition."""

from fastmcp import FastMCP

from attendance_crmt.audit_middleware import AuditMiddleware
from attendance_crmt.dependencies import (
    ServerDependencies,
    create_production_dependencies,
)
from attendance_crmt.observability import configure_structlog
from attendance_crmt.settings import get_settings
from attendance_crmt.tools import register_catalog_tools


def create_server(dependencies: ServerDependencies | None = None) -> FastMCP:
    """Create the application server and register its tools."""
    settings = get_settings()
    dependencies = dependencies or create_production_dependencies(settings)
    configure_structlog()

    server = FastMCP(
        name=settings.server_name,
        instructions=settings.server_instructions,
    )
    server.add_middleware(AuditMiddleware(dependencies.audit_log))
    register_catalog_tools(
        server, session_factory=dependencies.attendance_session_factory
    )
    return server


mcp = create_server()
