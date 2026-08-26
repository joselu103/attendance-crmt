"""FastMCP server composition."""

from fastmcp import FastMCP
from fastmcp.server.auth import TokenVerifier

from attendance_crmt.attendance.tools import register_attendance_tools
from attendance_crmt.audit_middleware import AuditMiddleware
from attendance_crmt.authentication import EntraTokenVerifier
from attendance_crmt.catalog.tools import register_catalog_tools
from attendance_crmt.dependencies import (
    ServerDependencies,
    create_production_dependencies,
)
from attendance_crmt.observability import configure_structlog
from attendance_crmt.settings import Settings, get_settings


def create_server(
    dependencies: ServerDependencies,
    *,
    auth: TokenVerifier | None = None,
    settings: Settings | None = None,
) -> FastMCP:
    """Create a server from explicit dependencies and optional authentication."""
    settings = settings or get_settings()
    configure_structlog()

    server = FastMCP(
        name=settings.server_name,
        instructions=settings.server_instructions,
        auth=auth,
    )
    server.add_middleware(
        AuditMiddleware(dependencies.audit_log, dependencies.requester_resolver)
    )
    register_catalog_tools(
        server, session_factory=dependencies.attendance_session_factory
    )
    register_attendance_tools(
        server,
        session_factory=dependencies.attendance_session_factory,
        requester_resolver=dependencies.requester_resolver,
    )
    return server


def create_production_server(settings: Settings | None = None) -> FastMCP:
    """Build the production server with Entra auth and claim-derived identity."""
    settings = settings or get_settings()
    dependencies = create_production_dependencies(settings)
    auth = EntraTokenVerifier(settings.entra_mcp_authentication)
    return create_server(dependencies, auth=auth, settings=settings)


mcp = create_production_server()
