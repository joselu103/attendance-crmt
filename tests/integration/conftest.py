"""Shared pytest fixtures for database-backed tests."""

from collections.abc import Iterator
from typing import cast

import factory
import pytest
from sqlalchemy import Engine, Table, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from attendance_crmt.audit import (
    AuditLog,
    create_audit_engine,
    create_audit_session_factory,
)
from attendance_crmt.database import create_session_factory
from attendance_crmt.dependencies import ServerDependencies
from attendance_crmt.models import Employee


class EmployeeFactory(factory.Factory):
    """Build valid employee records with generated directory data."""

    class Meta:
        model = Employee

    izvajalec_id = factory.Sequence(lambda index: index + 1)
    ime = factory.Faker("first_name")
    priimek = factory.Faker("last_name")
    username = factory.Sequence(lambda index: f"employee{index}")
    email = factory.Faker("email")
    active = 1


@pytest.fixture
def sqlite_engine() -> Iterator[Engine]:
    """Provide SQLite configured for the SQL Server ``dbo`` employee mapping."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def attach_dbo(connection, _connection_record) -> None:
        connection.execute("ATTACH DATABASE ':memory:' AS dbo")
        connection.create_collation(
            "SQL_Latin1_General_CP1250_CI_AS",
            lambda left, right: (left > right) - (left < right),
        )

    yield engine
    engine.dispose()


@pytest.fixture
def employee_session_factory(sqlite_engine: Engine) -> sessionmaker[Session]:
    """Provide sessions backed by an empty ``dbo.izvajalci`` test table."""
    cast(Table, Employee.__table__).create(sqlite_engine)
    return create_session_factory(sqlite_engine)


@pytest.fixture
def audit_session_factory(tmp_path) -> Iterator[sessionmaker[Session]]:
    """Provide an isolated file-backed SQLite audit database for one test."""
    engine = create_audit_engine(tmp_path / "audit.sqlite3")
    yield create_audit_session_factory(engine)
    engine.dispose()


@pytest.fixture
def audit_log(audit_session_factory: sessionmaker[Session]) -> AuditLog:
    """Provide audit persistence backed by the test's isolated SQLite database."""
    return AuditLog(audit_session_factory)


@pytest.fixture
def server_dependencies(
    employee_session_factory: sessionmaker[Session],
    audit_log: AuditLog,
) -> ServerDependencies:
    """Provide all infrastructure required by an isolated MCP server."""
    return ServerDependencies(
        attendance_session_factory=employee_session_factory,
        audit_log=audit_log,
    )


@pytest.fixture
def employee_factory() -> type[EmployeeFactory]:
    """Provide a Factory Boy factory for generated employee test data."""
    return EmployeeFactory
