import json

from pydantic import ValidationError
from sqlalchemy.exc import OperationalError

from attendance_crmt import readiness
from attendance_crmt.readiness import check_active_email_uniqueness, main


def test_active_email_readiness_reports_only_aggregate_duplicate_counts(
    employee_session_factory,
    employee_factory,
    capsys,
) -> None:
    employees = [
        employee_factory.build(email=" person@example.com ", active=1),
        employee_factory.build(email="PERSON@example.com", active=1),
        employee_factory.build(email="unique@example.com", active=1),
        employee_factory.build(email="   ", active=1),
        employee_factory.build(email="person@example.com", active=0),
    ]
    with employee_session_factory() as session:
        session.add_all(employees)
        session.commit()

    result = check_active_email_uniqueness(employee_session_factory)

    assert result.model_dump(mode="json") == {
        "active_employee_count": 4,
        "active_with_usable_email_count": 3,
        "duplicate_normalized_email_count": 1,
        "duplicate_active_employee_count": 2,
        "ready": False,
    }
    assert main(session_factory=employee_session_factory) == 2
    output = capsys.readouterr().out
    assert json.loads(output)["duplicate_normalized_email_count"] == 1
    assert "person@example.com" not in output.lower()


def test_active_email_readiness_passes_when_usable_active_emails_are_unique(
    employee_session_factory,
    employee_factory,
    capsys,
) -> None:
    employees = [
        employee_factory.build(email="person@example.com", active=1),
        employee_factory.build(email="other@example.com", active=1),
        employee_factory.build(email=None, active=1),
        employee_factory.build(email="person@example.com", active=0),
    ]
    with employee_session_factory() as session:
        session.add_all(employees)
        session.commit()

    result = check_active_email_uniqueness(employee_session_factory)

    assert result.model_dump(mode="json") == {
        "active_employee_count": 3,
        "active_with_usable_email_count": 2,
        "duplicate_normalized_email_count": 0,
        "duplicate_active_employee_count": 0,
        "ready": True,
    }
    assert main(session_factory=employee_session_factory) == 0
    assert json.loads(capsys.readouterr().out)["ready"] is True


def test_active_email_readiness_hides_misconfigured_runtime_details(
    monkeypatch,
    capsys,
) -> None:
    error = ValidationError.from_exception_data(
        "Settings",
        [{"type": "missing", "loc": ("attendance_db_url",), "input": {}}],
    )
    monkeypatch.setattr(readiness, "get_settings", lambda: (_ for _ in ()).throw(error))

    assert main() == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "Active-email readiness check is unavailable.\n"
    assert "attendance_db_url" not in captured.err


def test_active_email_readiness_hides_database_failure_details(capsys) -> None:
    def failing_session_factory():
        raise OperationalError(
            "SELECT sensitive SQL statement",
            {},
            ConnectionError("sensitive backend detail"),
        )

    assert main(session_factory=failing_session_factory) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "Active-email readiness check is unavailable.\n"
    assert "sensitive" not in captured.err
