import pytest
from pydantic import ValidationError

from attendance_crmt.database import create_engine_from_environment
from attendance_crmt.settings import Settings


def test_database_engine_loads_url_from_dotenv_file(tmp_path, monkeypatch) -> None:
    database_url = "sqlite://"
    (tmp_path / ".env").write_text(
        f"ATTENDANCE_DATABASE_URL={database_url}\n", encoding="utf-8"
    )
    monkeypatch.delenv("ATTENDANCE_DATABASE_URL", raising=False)
    monkeypatch.chdir(tmp_path)

    engine = create_engine_from_environment()

    assert engine.url.drivername == "sqlite"


def test_environment_variable_overrides_dotenv_value(tmp_path, monkeypatch) -> None:
    dotenv_url = "sqlite:///dotenv.db"
    environment_url = "sqlite:///environment.db"
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(f"ATTENDANCE_DATABASE_URL={dotenv_url}\n", encoding="utf-8")
    monkeypatch.setenv("ATTENDANCE_DATABASE_URL", environment_url)

    settings = Settings(_env_file=dotenv_path)

    assert settings.database_url == environment_url


def test_settings_require_database_url(monkeypatch) -> None:
    monkeypatch.delenv("ATTENDANCE_DATABASE_URL", raising=False)

    with pytest.raises(ValidationError, match="ATTENDANCE_DATABASE_URL"):
        Settings(_env_file=None)
