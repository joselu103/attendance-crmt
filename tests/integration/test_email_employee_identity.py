import pytest

from attendance_crmt.identity import (
    EmailIdentityAmbiguousError,
    EmailIdentityUnmappedError,
    resolve_active_employee_id_for_email,
)


def test_resolve_active_employee_id_for_email_returns_unique_active_employee(
    employee_session_factory,
    employee_factory,
) -> None:
    employee = employee_factory.build(
        izvajalec_id=42,
        email="person@example.com",
        active=1,
    )
    with employee_session_factory() as session:
        session.add(employee)
        session.commit()

    employee_id = resolve_active_employee_id_for_email(
        session_factory=employee_session_factory,
        email="  PERSON@example.com  ",
    )

    assert employee_id == 42


def test_resolve_active_employee_id_for_email_rejects_inactive_employee(
    employee_session_factory,
    employee_factory,
) -> None:
    employee = employee_factory.build(email="person@example.com", active=0)
    with employee_session_factory() as session:
        session.add(employee)
        session.commit()

    with pytest.raises(EmailIdentityUnmappedError):
        resolve_active_employee_id_for_email(
            session_factory=employee_session_factory,
            email="person@example.com",
        )


def test_resolve_active_employee_id_for_email_rejects_duplicate_active_email(
    employee_session_factory,
    employee_factory,
) -> None:
    employees = employee_factory.build_batch(2, email="person@example.com", active=1)
    with employee_session_factory() as session:
        session.add_all(employees)
        session.commit()

    with pytest.raises(EmailIdentityAmbiguousError):
        resolve_active_employee_id_for_email(
            session_factory=employee_session_factory,
            email="person@example.com",
        )
