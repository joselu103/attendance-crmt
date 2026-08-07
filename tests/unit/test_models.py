from decimal import Decimal

import pytest
from sqlalchemy import inspect
from sqlalchemy.dialects.mssql import SMALLDATETIME

from attendance_crmt.database import create_engine_for_url, create_session_factory
from attendance_crmt.models import (
    AttendanceLog,
    Base,
    Employee,
    Location,
    PlannedWork,
    PunchType,
)


@pytest.fixture
def tables():
    return Base.metadata.tables


def test_models_map_the_known_dbo_tables(tables) -> None:
    assert set(tables) == {
        "dbo.att_attendance_log",
        "dbo.att_planirano_delo",
        "dbo.att_punch_type",
        "dbo.izvajalci",
        "dbo.lokacije",
    }


def test_planned_work_uses_confirmed_composite_identity() -> None:
    mapper = inspect(PlannedWork)

    assert [column.name for column in mapper.primary_key] == [
        "izvajalec_id",
        "datum_id",
    ]
    assert PlannedWork.__table__.c.att_planirano_ur_va.type.precision == 8
    assert PlannedWork.__table__.c.att_planirano_ur_va.type.scale == 2
    assert PlannedWork.__table__.c.datum_id.type.__class__ is SMALLDATETIME


def test_punch_type_and_location_preserve_their_keys_and_constraints() -> None:
    assert [column.name for column in inspect(PunchType).primary_key] == [
        "punch_type_id"
    ]
    assert [column.name for column in inspect(Location).primary_key] == ["lokacija_id"]
    assert Location.__table__.c.lokacija_id.autoincrement is True
    assert Location.__table__.c.lokacija_opis.type.length == 35
    assert any(
        constraint.columns.keys() == ["lokacija_opis"]
        for constraint in Location.__table__.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    )


def test_attendance_log_maps_known_foreign_keys_and_relationships() -> None:
    foreign_keys = {
        (foreign_key.parent.name, foreign_key.target_fullname)
        for foreign_key in AttendanceLog.__table__.foreign_keys
    }

    assert foreign_keys == {
        ("att_location_id", "dbo.lokacije.lokacija_id"),
        ("att_punch_type_id", "dbo.att_punch_type.punch_type_id"),
        ("att_user_id", "dbo.izvajalci.izvajalec_id"),
    }
    assert AttendanceLog.location.property.mapper.class_ is Location
    assert AttendanceLog.punch_type.property.mapper.class_ is PunchType
    assert AttendanceLog.employee.property.mapper.class_ is Employee


def test_employee_maps_the_read_model_identity_and_fields() -> None:
    employee = Employee.__table__

    assert [column.name for column in inspect(Employee).primary_key] == ["izvajalec_id"]
    assert set(employee.columns.keys()) == {
        "izvajalec_id",
        "ime",
        "priimek",
        "username",
        "email",
        "user_id",
        "active",
    }
    assert employee.c.username.type.length == 20
    assert employee.c.ime.nullable is False
    assert employee.c.priimek.nullable is False
    assert any(
        constraint.columns.keys() == ["username"]
        for constraint in employee.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    )


def test_mapped_columns_accept_expected_python_value_types() -> None:
    planned_work = PlannedWork(
        izvajalec_id=7,
        datum_id="2026-08-05 00:00:00",
        att_planirano_ur_va=Decimal("8.00"),
    )

    assert planned_work.izvajalec_id == 7
    assert planned_work.att_planirano_ur_va == Decimal("8.00")


def test_database_setup_builds_an_engine_and_session_factory() -> None:
    engine = create_engine_for_url("sqlite://")
    session_factory = create_session_factory(engine)

    assert engine.url.drivername == "sqlite"
    assert session_factory.kw["bind"] is engine
