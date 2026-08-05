"""SQLAlchemy mappings for the legacy attendance database tables."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CHAR,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.mssql import SMALLDATETIME
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

SLOVENIAN_COLLATION = "Slovenian_CI_AI"
CP1250_COLLATION = "SQL_Latin1_General_CP1250_CI_AS"


class Base(DeclarativeBase):
    """Base class for attendance database mappings."""


class PlannedWork(Base):
    """Expected work hours for an employee on a specific day.

    ``(izvajalec_id, datum_id)`` is unique, so it is used as the ORM identity.
    """

    __tablename__ = "att_planirano_delo"
    __table_args__ = ({"schema": "dbo"},)

    izvajalec_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    datum_id: Mapped[datetime] = mapped_column(SMALLDATETIME, primary_key=True)
    att_planirano_ur_va: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    user_id: Mapped[str | None] = mapped_column(
        String(50, collation=SLOVENIAN_COLLATION)
    )
    modified: Mapped[datetime | None] = mapped_column(SMALLDATETIME)


class PunchType(Base):
    """A configured category of attendance event."""

    __tablename__ = "att_punch_type"
    __table_args__ = ({"schema": "dbo"},)

    punch_type_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    punch_type_desc: Mapped[str | None] = mapped_column(
        String(100, collation=SLOVENIAN_COLLATION)
    )
    user_id: Mapped[str | None] = mapped_column(
        String(20, collation=SLOVENIAN_COLLATION)
    )
    modified: Mapped[datetime | None] = mapped_column(SMALLDATETIME)
    active: Mapped[int | None] = mapped_column(Integer)
    reporting: Mapped[int | None] = mapped_column(Integer)

    attendance_logs: Mapped[list[AttendanceLog]] = relationship(
        back_populates="punch_type"
    )


class Location(Base):
    """A location that can be attached to an attendance event."""

    __tablename__ = "lokacije"
    __table_args__ = (
        UniqueConstraint("lokacija_opis"),
        {"schema": "dbo"},
    )

    lokacija_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    lokacija_opis: Mapped[str | None] = mapped_column(
        String(35, collation=CP1250_COLLATION)
    )
    user_id: Mapped[str | None] = mapped_column(String(20, collation=CP1250_COLLATION))
    modified: Mapped[datetime | None] = mapped_column(SMALLDATETIME)

    attendance_logs: Mapped[list[AttendanceLog]] = relationship(
        back_populates="location"
    )


class Employee(Base):
    """Employee record (``izvajalci``)."""

    __tablename__ = "izvajalci"
    __table_args__ = (
        UniqueConstraint("username"),
        {"schema": "dbo"},
    )

    izvajalec_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    ime: Mapped[str] = mapped_column(
        String(35, collation=CP1250_COLLATION), nullable=False
    )
    priimek: Mapped[str] = mapped_column(
        String(35, collation=CP1250_COLLATION), nullable=False
    )
    username: Mapped[str] = mapped_column(
        String(20, collation=CP1250_COLLATION), nullable=False
    )
    email: Mapped[str | None] = mapped_column(String(50, collation=CP1250_COLLATION))
    user_id: Mapped[str | None] = mapped_column(String(20, collation=CP1250_COLLATION))
    active: Mapped[int | None] = mapped_column(Integer)

    attendance_logs: Mapped[list[AttendanceLog]] = relationship(
        back_populates="employee"
    )


class AttendanceLog(Base):
    """An individual attendance event, including an optional end time."""

    __tablename__ = "att_attendance_log"
    __table_args__ = ({"schema": "dbo"},)

    att_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    att_user_id: Mapped[int] = mapped_column(
        ForeignKey("dbo.izvajalci.izvajalec_id"), nullable=False
    )
    att_location_id: Mapped[int | None] = mapped_column(
        ForeignKey("dbo.lokacije.lokacija_id")
    )
    att_punch_type_id: Mapped[int | None] = mapped_column(
        ForeignKey("dbo.att_punch_type.punch_type_id")
    )
    att_in: Mapped[datetime | None] = mapped_column(DateTime)
    att_out: Mapped[datetime | None] = mapped_column(DateTime)
    att_opomba: Mapped[str | None] = mapped_column(
        String(255, collation=SLOVENIAN_COLLATION)
    )
    att_edited: Mapped[int | None] = mapped_column(Integer)
    inserted: Mapped[datetime | None] = mapped_column(SMALLDATETIME)
    modified: Mapped[datetime | None] = mapped_column(SMALLDATETIME)
    user_id: Mapped[str | None] = mapped_column(
        String(20, collation=SLOVENIAN_COLLATION)
    )
    data_source: Mapped[str | None] = mapped_column(
        CHAR(10, collation=SLOVENIAN_COLLATION)
    )

    employee: Mapped[Employee] = relationship(back_populates="attendance_logs")
    location: Mapped[Location | None] = relationship(back_populates="attendance_logs")
    punch_type: Mapped[PunchType | None] = relationship(
        back_populates="attendance_logs"
    )
