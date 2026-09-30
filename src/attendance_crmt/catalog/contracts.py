"""Transport-independent contracts for catalog application services."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EmployeePageQuery(BaseModel):
    """Validated pagination criteria for employee discovery."""

    model_config = ConfigDict(frozen=True)

    limit: int = 50
    offset: int = 0

    @model_validator(mode="after")
    def validate_pagination(self) -> EmployeePageQuery:
        """Apply the shared bounded-pagination rule."""
        if not 1 <= self.limit <= 100:
            raise ValueError("limit must be between 1 and 100.")
        if self.offset < 0:
            raise ValueError("offset must not be negative.")
        return self


class EmployeeResolveQuery(BaseModel):
    """One exact directory identifier for privileged employee resolution."""

    model_config = ConfigDict(frozen=True)

    employee_id: int | None = None
    username: str | None = Field(default=None, min_length=1)
    email: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_exactly_one_identifier(self) -> EmployeeResolveQuery:
        """Require one, and only one, exact employee identifier."""
        if (
            sum(
                value is not None
                for value in (self.employee_id, self.username, self.email)
            )
            != 1
        ):
            raise ValueError("exactly one employee identifier is required.")
        return self


class EmployeeSummary(BaseModel):
    """A directory-safe employee representation."""

    model_config = ConfigDict(frozen=True)

    employee_id: int
    first_name: str
    last_name: str
    username: str
    email: str | None
    active: int | None


class EmployeePage(BaseModel):
    """A bounded page of employee directory results."""

    model_config = ConfigDict(frozen=True)

    items: list[EmployeeSummary]
    limit: int
    offset: int
    next_offset: int | None


class PunchTypeSummary(BaseModel):
    """Configured punch type with its server-derived attendance location."""

    model_config = ConfigDict(frozen=True)

    punch_type_id: int
    punch_type: str | None
    active: int | None
    derived_location_id: int | None
    derived_location: str | None


class LocationSummary(BaseModel):
    """Reference location available on recorded attendance events."""

    model_config = ConfigDict(frozen=True)

    location_id: int
    location: str | None
