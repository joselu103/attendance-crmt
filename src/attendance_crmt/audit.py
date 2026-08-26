"""Append-only SQLAlchemy audit storage for MCP tool interactions."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import DateTime, Integer, String, Text, create_engine
from sqlalchemy.engine import URL, Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

SENSITIVE_FIELD_NAMES = frozenset(
    {"authorization", "cookie", "password", "secret", "token"}
)


class AuditBase(DeclarativeBase):
    """Base for the local SQLite audit database."""


class AuditEvent(AuditBase):
    """One immutable record of an MCP tool interaction."""

    __tablename__ = "audit_event"

    event_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    occurred_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    actor_id: Mapped[str] = mapped_column(String(80), nullable=False)
    employee_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    roles_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    tool_name: Mapped[str] = mapped_column(String(255), nullable=False)
    request_json: Mapped[str] = mapped_column(Text, nullable=False)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)


def create_audit_engine(database_path: Path) -> Engine:
    """Create a local SQLite engine for the audit database."""
    database_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(URL.create("sqlite", database=str(database_path)))


AUDIT_ADDITIVE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("employee_id", "INTEGER"),
    ("roles_json", "TEXT"),
    ("correlation_id", "VARCHAR(36)"),
    ("error_code", "VARCHAR(64)"),
)


def create_audit_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create or additively migrate the local SQLite audit schema."""
    AuditBase.metadata.create_all(engine)
    _migrate_audit_schema(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _migrate_audit_schema(engine: Engine) -> None:
    """Add nullable fields without rewriting established local audit records."""
    with engine.begin() as connection:
        existing_columns = {
            row[1]
            for row in connection.exec_driver_sql("PRAGMA table_info(audit_event)")
        }
        for column_name, column_type in AUDIT_ADDITIVE_COLUMNS:
            if column_name not in existing_columns:
                connection.exec_driver_sql(
                    f"ALTER TABLE audit_event ADD COLUMN {column_name} {column_type}"
                )


class AuditLog:
    """Persist MCP audit events through an injected SQLAlchemy session factory."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def record(
        self,
        *,
        actor_id: str,
        tool_name: str,
        request: Mapping[str, Any],
        outcome: str,
        duration_ms: int,
    ) -> None:
        """Add one immutable audit event."""
        event = AuditEvent(
            occurred_at_utc=datetime.now(UTC),
            actor_id=actor_id,
            tool_name=tool_name,
            request_json=json.dumps(_sanitize(request), sort_keys=True, default=str),
            outcome=outcome,
            duration_ms=duration_ms,
        )
        with self._session_factory.begin() as session:
            session.add(event)


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: "[REDACTED]"
            if isinstance(key, str) and key.casefold() in SENSITIVE_FIELD_NAMES
            else _sanitize(item)
            for key, item in value.items()
        }
    if isinstance(value, list | tuple):
        return [_sanitize(item) for item in value]
    return value
