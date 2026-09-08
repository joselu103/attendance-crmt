"""Application dependency composition for production and test servers."""

from __future__ import annotations

from dataclasses import dataclass

from fastmcp.server.auth import TokenVerifier
from sqlalchemy.orm import Session, sessionmaker

from attendance_crmt.audit import (
    AuditLog,
    create_audit_engine,
    create_audit_session_factory,
)
from attendance_crmt.authentication import EntraTokenVerifier
from attendance_crmt.database import (
    create_engine_for_url,
    create_session_factory,
)
from attendance_crmt.identity import (
    AuthenticatedTokenRequesterResolver,
    PrincipalResolver,
    RequesterResolver,
)
from attendance_crmt.settings import Settings


@dataclass(frozen=True)
class ServerDependencies:
    """Infrastructure used by the MCP server and its registered tools."""

    attendance_session_factory: sessionmaker[Session]
    audit_log: AuditLog
    requester_resolver: RequesterResolver
    auth_provider: TokenVerifier | None
    principal_resolver: PrincipalResolver | None = None


def create_production_dependencies(settings: Settings) -> ServerDependencies:
    """Eagerly build production database dependencies from validated settings."""
    attendance_session_factory = create_session_factory(
        create_engine_for_url(settings.attendance_db_url)
    )
    audit_session_factory = create_audit_session_factory(
        create_audit_engine(settings.audit_db_path)
    )
    principal_resolver = AuthenticatedTokenRequesterResolver(
        session_factory=attendance_session_factory,
        admin_role=settings.entra_admin_role,
        email_aliases=settings.entra_email_aliases,
    )
    return ServerDependencies(
        attendance_session_factory=attendance_session_factory,
        audit_log=AuditLog(audit_session_factory),
        requester_resolver=principal_resolver,
        auth_provider=EntraTokenVerifier(settings.entra_mcp_authentication),
        principal_resolver=principal_resolver,
    )
