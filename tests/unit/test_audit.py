import json
from uuid import UUID

from sqlalchemy import select, text

from attendance_crmt.audit import (
    AuditEvent,
    AuditLog,
    create_audit_engine,
    create_audit_session_factory,
)


def test_audit_log_redacts_sensitive_request_values(tmp_path) -> None:
    engine = create_audit_engine(tmp_path / "audit.sqlite3")
    session_factory = create_audit_session_factory(engine)
    audit_log = AuditLog(session_factory)

    try:
        audit_log.record(
            actor_id="test-user",
            tool_name="future_tool",
            request={
                "nested": {"authorization": "Bearer secret"},
                "token": "secret",
            },
            outcome="success",
            duration_ms=0,
        )

        with session_factory() as session:
            event = session.scalar(select(AuditEvent))
    finally:
        engine.dispose()

    assert event is not None
    assert json.loads(event.request_json) == {
        "nested": {"authorization": "[REDACTED]"},
        "token": "[REDACTED]",
    }


def test_audit_log_persists_authenticated_context_and_stable_error_code(
    tmp_path,
) -> None:
    engine = create_audit_engine(tmp_path / "audit.sqlite3")
    session_factory = create_audit_session_factory(engine)
    audit_log = AuditLog(session_factory)
    correlation_id = UUID("11111111-1111-1111-1111-111111111111")

    try:
        audit_log.record(
            actor_id="22222222-2222-2222-2222-222222222222:33333333-3333-3333-3333-333333333333",
            employee_id=42,
            roles=frozenset({"admin", "employee"}),
            correlation_id=correlation_id,
            tool_name="future_tool",
            request={},
            outcome="failure",
            error_code="FORBIDDEN",
            duration_ms=12,
        )

        with session_factory() as session:
            event = session.scalar(select(AuditEvent))
    finally:
        engine.dispose()

    assert event is not None
    assert (
        event.actor_id
        == "22222222-2222-2222-2222-222222222222:33333333-3333-3333-3333-333333333333"
    )
    assert event.employee_id == 42
    assert event.roles_json == '["admin", "employee"]'
    assert event.correlation_id == str(correlation_id)
    assert event.error_code == "FORBIDDEN"


def test_audit_schema_migration_adds_authenticated_context_columns(tmp_path) -> None:
    engine = create_audit_engine(tmp_path / "audit.sqlite3")
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    CREATE TABLE audit_event (
                        event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        occurred_at_utc DATETIME NOT NULL,
                        actor_id VARCHAR(50) NOT NULL,
                        tool_name VARCHAR(255) NOT NULL,
                        request_json TEXT NOT NULL,
                        outcome VARCHAR(20) NOT NULL,
                        duration_ms INTEGER NOT NULL
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO audit_event (
                        occurred_at_utc, actor_id, tool_name, request_json, outcome, duration_ms
                    ) VALUES (
                        '2026-08-26T00:00:00+00:00', 'historic-user', 'historic_tool',
                        '{}', 'success', 1
                    )
                    """
                )
            )

        session_factory = create_audit_session_factory(engine)

        with engine.connect() as connection:
            columns = {
                row[1]
                for row in connection.execute(text("PRAGMA table_info(audit_event)"))
            }
        with session_factory() as session:
            historic_event = session.scalar(select(AuditEvent))
    finally:
        engine.dispose()

    assert {
        "correlation_id",
        "employee_id",
        "roles_json",
        "error_code",
    } <= columns
    assert historic_event is not None
    assert historic_event.actor_id == "historic-user"
    assert historic_event.correlation_id is None
    assert historic_event.employee_id is None
    assert historic_event.roles_json is None
    assert historic_event.error_code is None
