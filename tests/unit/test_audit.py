import json

from sqlalchemy import select

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
