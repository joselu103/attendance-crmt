from attendance_crmt.database import create_engine_from_environment
from attendance_crmt.settings import get_settings


def test_database_engine_requires_configured_url(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("ATTENDANCE_DATABASE_URL", raising=False)
    monkeypatch.chdir(tmp_path)

    get_settings.cache_clear()
    try:
        try:
            create_engine_from_environment()
        except RuntimeError as error:
            assert str(error) == "ATTENDANCE_DATABASE_URL must be configured."
        else:
            raise AssertionError("Expected a missing database URL to fail.")
    finally:
        get_settings.cache_clear()
