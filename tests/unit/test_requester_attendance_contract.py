from datetime import date, datetime

import pytest
from pydantic import ValidationError

from attendance_crmt.attendance.contracts import (
    AttendanceEventPage,
    AttendanceEventSummary,
    AttendanceExceptionsQuery,
    EmployeeAttendanceAnalysisQuery,
    MyAttendanceEventQuery,
    MyAttendanceSummaryQuery,
    OrganizationAttendanceAnalysisQuery,
    PlannedWorkQuery,
)


def _event() -> AttendanceEventSummary:
    return AttendanceEventSummary(
        attendance_event_id=100,
        employee_id=42,
        punch_type="Remote work",
        location="Home",
        checked_in_at=datetime(2026, 8, 10, 8, 0),  # noqa: DTZ001
        checked_out_at=datetime(2026, 8, 10, 16, 0),  # noqa: DTZ001
        note=None,
    )


def test_my_attendance_query_accepts_31_inclusive_calendar_days() -> None:
    query = MyAttendanceEventQuery(
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 31),
    )

    assert query.start_date == date(2026, 8, 1)
    assert query.end_date == date(2026, 8, 31)


def test_my_attendance_query_rejects_invalid_pagination_and_date_order() -> None:
    with pytest.raises(ValidationError, match="start_date must not be after end_date"):
        MyAttendanceEventQuery(
            start_date=date(2026, 8, 2),
            end_date=date(2026, 8, 1),
        )

    with pytest.raises(ValidationError, match="limit must be between 1 and 100"):
        MyAttendanceEventQuery(
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 1),
            limit=101,
        )

    with pytest.raises(ValidationError, match="offset must not be negative"):
        MyAttendanceEventQuery(
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 1),
            offset=-1,
        )


def test_attendance_event_page_is_deeply_immutable() -> None:
    page = AttendanceEventPage(
        items=(_event(),),
        limit=50,
        offset=0,
        next_offset=None,
    )

    with pytest.raises(TypeError):
        page.items[0] = _event()  # type: ignore[index]

    with pytest.raises(ValidationError, match="frozen"):
        page.items[0].note = "changed"  # type: ignore[misc]


def test_attendance_event_timestamps_include_ljubljana_offset() -> None:
    payload = _event().model_dump(mode="json")

    assert payload["checked_in_at"] == "2026-08-10T08:00:00+02:00"
    assert payload["checked_out_at"] == "2026-08-10T16:00:00+02:00"


@pytest.mark.parametrize(
    "query_type,extra",
    [
        (MyAttendanceSummaryQuery, {}),
        (PlannedWorkQuery, {"employee_id": 42}),
        (EmployeeAttendanceAnalysisQuery, {"employee_id": 42}),
        (OrganizationAttendanceAnalysisQuery, {}),
        (AttendanceExceptionsQuery, {}),
    ],
)
def test_non_history_contracts_keep_date_caps(query_type, extra) -> None:
    with pytest.raises(ValidationError, match="must not exceed"):
        query_type(start_date=date(2026, 1, 1), end_date=date(2028, 12, 31), **extra)
