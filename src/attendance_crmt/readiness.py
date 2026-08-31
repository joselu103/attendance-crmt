"""Read-only production readiness checks for Attendance CRMT."""

from __future__ import annotations

import json
import sys

from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from attendance_crmt.database import create_engine_for_url, create_session_factory
from attendance_crmt.identity import (
    active_employee_with_usable_email_conditions,
    normalized_active_employee_email_expression,
)
from attendance_crmt.models import Employee
from attendance_crmt.settings import get_settings


class ActiveEmailUniquenessResult(BaseModel):
    """Aggregate-only outcome of the active-email identity readiness check."""

    model_config = ConfigDict(frozen=True)

    active_employee_count: int
    active_with_usable_email_count: int
    duplicate_normalized_email_count: int
    duplicate_active_employee_count: int
    ready: bool


def check_active_email_uniqueness(
    session_factory: sessionmaker[Session],
) -> ActiveEmailUniquenessResult:
    """Count active-email mapping conflicts without selecting identity values."""
    normalized_email = normalized_active_employee_email_expression()
    usable_active_email = active_employee_with_usable_email_conditions()
    duplicate_group_count = func.count(Employee.izvajalec_id)

    with session_factory() as session:
        active_employee_count = session.scalar(
            select(func.count(Employee.izvajalec_id)).where(Employee.active == 1)
        )
        active_with_usable_email_count = session.scalar(
            select(func.count(Employee.izvajalec_id)).where(*usable_active_email)
        )
        duplicate_active_employee_counts = session.scalars(
            select(duplicate_group_count)
            .where(*usable_active_email)
            .group_by(normalized_email)
            .having(duplicate_group_count > 1)
        ).all()

    duplicate_normalized_email_count = len(duplicate_active_employee_counts)
    duplicate_active_employee_count = sum(duplicate_active_employee_counts)
    return ActiveEmailUniquenessResult(
        active_employee_count=active_employee_count or 0,
        active_with_usable_email_count=active_with_usable_email_count or 0,
        duplicate_normalized_email_count=duplicate_normalized_email_count,
        duplicate_active_employee_count=duplicate_active_employee_count,
        ready=duplicate_normalized_email_count == 0,
    )


def main(*, session_factory: sessionmaker[Session] | None = None) -> int:
    """Print a safe aggregate readiness result and return a process exit status."""
    try:
        if session_factory is None:
            settings = get_settings()
            session_factory = create_session_factory(
                create_engine_for_url(settings.attendance_db_url)
            )
        result = check_active_email_uniqueness(session_factory)
    except SQLAlchemyError, ValidationError:
        print("Active-email readiness check is unavailable.", file=sys.stderr)
        return 1

    print(json.dumps(result.model_dump(mode="json"), sort_keys=True))
    return 0 if result.ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
