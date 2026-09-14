"""FastMCP server composition."""

from fastapi import FastAPI
from fastmcp import FastMCP

from attendance_crmt.attendance.tools import register_attendance_tools
from attendance_crmt.audit_middleware import AuditMiddleware
from attendance_crmt.catalog.tools import register_catalog_tools
from attendance_crmt.dependencies import (
    ServerDependencies,
    create_production_dependencies,
)
from attendance_crmt.http_contract import ContractVersionHeaderMiddleware
from attendance_crmt.observability import configure_structlog
from attendance_crmt.rest import create_app
from attendance_crmt.settings import Settings, get_settings


def create_server(
    dependencies: ServerDependencies,
    *,
    settings: Settings | None = None,
) -> FastMCP:
    """Create a server from explicit dependencies and authentication."""
    settings = settings or get_settings()
    configure_structlog(settings.environment)

    server = FastMCP(
        name=settings.server_name,
        instructions=settings.server_instructions,
        auth=dependencies.auth_provider,
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
    return create_server(dependencies, settings=settings)


def create_http_app(
    server: FastMCP,
    dependencies: ServerDependencies | None = None,
) -> FastAPI:
    """Compose REST as the runtime surface and mount MCP as a rollback bridge.

    REST owns its routes at the application root. The embedded FastMCP ASGI app
    remains mounted unchanged at ``/mcp`` until the separate adapter has passed
    its parity gate.
    """
    mcp_http_app = server.http_app(
        path="/mcp",
        stateless_http=True,
        json_response=True,
        host_origin_protection=True,
    )
    app = create_app(dependencies, lifespan=mcp_http_app.lifespan)
    mcp_app = ContractVersionHeaderMiddleware(mcp_http_app)
    app.mount("/", mcp_app)
    return app


def create_production_http_app(settings: Settings | None = None) -> FastAPI:
    """Build the production REST application with its temporary MCP bridge."""
    settings = settings or get_settings()
    dependencies = create_production_dependencies(settings)
    return create_http_app(create_server(dependencies, settings=settings), dependencies)
