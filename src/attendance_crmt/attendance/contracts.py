"""Transport-independent contracts for attendance application services."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, field_serializer, model_validator

_EUROPE_LJUBLJANA = ZoneInfo("Europe/Ljubljana")


def _serialize_local_datetime(value: datetime) -> str:
    """Serialize a database-local timestamp as RFC 3339 Europe/Ljubljana time."""
    return value.replace(tzinfo=_EUROPE_LJUBLJANA).isoformat()


class AttendanceEventQuery(BaseModel):
    """Validated selection and pagination criteria for attendance events."""

    model_config = ConfigDict(frozen=True)

    employee_id: int
    start_date: date
    end_date: date
    limit: int = 50
    offset: int = 0

    @model_validator(mode="after")
    def validate_date_range(self) -> AttendanceEventQuery:
        """Apply shared range and pagination rules."""
        if not 1 <= self.limit <= 100:
            raise ValueError("limit must be between 1 and 100.")
        if self.offset < 0:
            raise ValueError("offset must not be negative.")
        if self.start_date > self.end_date:
            raise ValueError("start_date must not be after end_date.")
        return self


class AttendanceEventSummary(BaseModel):
    """A read-only attendance event returned by the application service."""

    model_config = ConfigDict(frozen=True)

    attendance_event_id: int
    employee_id: int
    punch_type: str | None
    location: str | None
    checked_in_at: datetime | None
    checked_out_at: datetime | None
    note: str | None


class AttendanceEventPage(BaseModel):
    """A bounded page of attendance events for one employee."""

    model_config = ConfigDict(frozen=True)

    items: list[AttendanceEventSummary]
    limit: int
    offset: int
    next_offset: int | None


class AttendanceEventDetail(AttendanceEventSummary):
    """One attendance event including recorded audit metadata."""

    edited: bool
    recorded_at: datetime | None
    modified_at: datetime | None
    modified_by: str | None
    data_source: str | None


class DailyAttendanceQuery(BaseModel):
    """Validated daily attendance selection for one employee."""

    model_config = ConfigDict(frozen=True)

    employee_id: int
    day: date


class DailyAttendance(BaseModel):
    """One day's raw events and calculated attendance outcome."""

    model_config = ConfigDict(frozen=True)

    employee_id: int
    day: date
    events: list[AttendanceEventSummary]
    logged_hours: Decimal
    known_planned_hours: Decimal | None
    balance_hours: Decimal | None
    planned_hours_complete: bool
    incomplete_interval_count: int
    anomaly_count: int


LiveAttendanceStatus = Literal[
    "office",
    "remote",
    "customer_site",
    "break",
    "absence",
    "no_status",
    "unknown",
]


class CurrentAttendanceQuery(BaseModel):
    """Validated point-in-time filters for active employee presence."""

    model_config = ConfigDict(frozen=True)

    as_of: datetime
    status: LiveAttendanceStatus | None = None
    limit: int = 50
    offset: int = 0

    @model_validator(mode="after")
    def validate_pagination(self) -> CurrentAttendanceQuery:
        if self.as_of.tzinfo is not None:
            raise ValueError("as_of must be a Europe/Ljubljana local timestamp.")
        if not 1 <= self.limit <= 100:
            raise ValueError("limit must be between 1 and 100.")
        if self.offset < 0:
            raise ValueError("offset must not be negative.")
        return self


class CurrentAttendanceSummary(BaseModel):
    """An active employee's effective attendance state at one instant."""

    model_config = ConfigDict(frozen=True)

    employee_id: int
    first_name: str
    last_name: str
    status: LiveAttendanceStatus
    attendance_event_id: int | None
    started_at: datetime | None
    punch_type: str | None
    location: str | None

    @field_serializer("started_at", when_used="json")
    def serialize_started_at(self, value: datetime | None) -> str | None:
        """Expose database-local timestamps with their Europe/Ljubljana offset."""
        return _serialize_local_datetime(value) if value is not None else None


class CurrentAttendancePage(BaseModel):
    """A bounded page of active employees' point-in-time attendance states."""

    model_config = ConfigDict(frozen=True)

    items: list[CurrentAttendanceSummary]
    as_of: datetime
    limit: int
    offset: int
    next_offset: int | None

    @field_serializer("as_of", when_used="json")
    def serialize_as_of(self, value: datetime) -> str:
        """Expose the requested local timestamp with its Europe/Ljubljana offset."""
        return _serialize_local_datetime(value)


class EmployeeAttendanceAnalysisQuery(BaseModel):
    """Validated employee reporting range, limited to 31 calendar days."""

    model_config = ConfigDict(frozen=True)

    employee_id: int
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def validate_range(self) -> EmployeeAttendanceAnalysisQuery:
        if self.start_date > self.end_date:
            raise ValueError("start_date must not be after end_date.")
        if (self.end_date - self.start_date).days >= 31:
            raise ValueError("reporting date range must not exceed 31 calendar days.")
        return self


class PunchTypeHours(BaseModel):
    """Completed, non-anomalous interval duration grouped by punch type."""

    model_config = ConfigDict(frozen=True)

    punch_type_id: int | None
    punch_type: str | None
    hours: Decimal


class AttendanceAnalysisDay(BaseModel):
    """One calendar day's planned and logged attendance result."""

    model_config = ConfigDict(frozen=True)

    day: date
    known_planned_hours: Decimal | None
    logged_hours: Decimal
    missing_attendance: bool
    incomplete_interval_count: int
    anomaly_count: int


class EmployeeAttendanceAnalysis(BaseModel):
    """Transport-independent monthly attendance analysis for one employee."""

    model_config = ConfigDict(frozen=True)

    employee_id: int
    start_date: date
    end_date: date
    logged_hours: Decimal
    known_planned_hours: Decimal
    balance_hours: Decimal | None
    planned_hours_complete: bool
    punch_type_totals: list[PunchTypeHours]
    days: list[AttendanceAnalysisDay]


class EmployeeAttendanceSummary(BaseModel):
    """Compact employee attendance result without a daily breakdown."""

    model_config = ConfigDict(frozen=True)

    employee_id: int
    start_date: date
    end_date: date
    logged_hours: Decimal
    known_planned_hours: Decimal
    balance_hours: Decimal | None
    planned_hours_complete: bool
    punch_type_totals: list[PunchTypeHours]
    incomplete_interval_count: int
    anomaly_count: int


class OrganizationAttendanceAnalysisQuery(BaseModel):
    """Validated organization reporting range and employee-summary pagination."""

    model_config = ConfigDict(frozen=True)

    start_date: date
    end_date: date
    limit: int = 50
    offset: int = 0

    @model_validator(mode="after")
    def validate_range_and_pagination(self) -> OrganizationAttendanceAnalysisQuery:
        if self.start_date > self.end_date:
            raise ValueError("start_date must not be after end_date.")
        if (self.end_date - self.start_date).days >= 31:
            raise ValueError("reporting date range must not exceed 31 calendar days.")
        if not 1 <= self.limit <= 100:
            raise ValueError("limit must be between 1 and 100.")
        if self.offset < 0:
            raise ValueError("offset must not be negative.")
        return self


class EmployeeAttendanceAnalysisSummary(BaseModel):
    """Organization-level employee result without the employee daily breakdown."""

    model_config = ConfigDict(frozen=True)

    employee_id: int
    first_name: str
    last_name: str
    logged_hours: Decimal
    known_planned_hours: Decimal
    balance_hours: Decimal | None
    planned_hours_complete: bool
    incomplete_interval_count: int
    anomaly_count: int


class OrganizationAttendanceAnalysis(BaseModel):
    """Organization totals plus a bounded page of active-employee summaries."""

    model_config = ConfigDict(frozen=True)

    start_date: date
    end_date: date
    active_employee_count: int
    logged_hours: Decimal
    known_planned_hours: Decimal
    balance_hours: Decimal | None
    planned_hours_complete: bool
    items: list[EmployeeAttendanceAnalysisSummary]
    limit: int
    offset: int
    next_offset: int | None
