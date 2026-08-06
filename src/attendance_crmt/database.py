"""SQL Server engine and session-factory construction."""

from pydantic import ValidationError
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from attendance_crmt.settings import DATABASE_URL_ENV, Settings


def create_engine_for_url(database_url: str) -> Engine:
    """Build a SQLAlchemy engine without opening a database connection.

    Use a ``mssql+pyodbc`` URL for the legacy SQL Server database, for example:
    ``mssql+pyodbc://user:password@host/database?driver=ODBC+Driver+18+for+SQL+Server``.
    """
    return create_engine(database_url, pool_pre_ping=True)


def create_engine_from_environment() -> Engine:
    """Build an engine from the configured database URL without connecting."""
    try:
        database_url = Settings().database_url
    except ValidationError as error:
        message = f"{DATABASE_URL_ENV} must be configured."
        raise RuntimeError(message) from error

    return create_engine_for_url(database_url)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create an explicit session factory bound to ``engine``."""
    return sessionmaker(bind=engine, expire_on_commit=False)
