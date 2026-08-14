"""Transport-independent contracts for attendance application services."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, model_validator


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
