import asyncio
import io
import json

import structlog

from attendance_crmt.observability import (
    bind_identity_context,
    configure_structlog,
    get_logger,
    reset_identity_context,
)


def test_development_logging_is_colored_and_allows_debug_events() -> None:
    output = io.StringIO()
    configure_structlog("development", stream=output)

    get_logger("attendance_crmt.test").debug("development event")

    event = output.getvalue()
    assert "development event" in event
    assert "debug" in event
    assert "\x1b[" in event


def test_staging_logging_is_single_line_json_on_info_or_higher() -> None:
    output = io.StringIO()
    configure_structlog("staging", stream=output)
    logger = get_logger("attendance_crmt.test")

    logger.debug("not emitted")
    logger.info("staging event")

    lines = output.getvalue().splitlines()
    assert len(lines) == 1
    event = json.loads(lines[0])
    assert event["event"] == "staging event"
    assert event["level"] == "info"
    assert event["logger"] == "attendance_crmt.test"
    assert event["timestamp"].endswith("+02:00") or event["timestamp"].endswith(
        "+01:00"
    )
    assert event["timestamp_utc"].endswith("Z")
    assert event["module"] == "test_observability"
    assert event["filename"] == "test_observability.py"
    assert isinstance(event["lineno"], int)


def test_production_logging_recursively_redacts_without_mutating_payload() -> None:
    output = io.StringIO()
    configure_structlog("production", stream=output)
    payload = {
        "token": "top-secret",
        "nested": {"Authorization": "Bearer secret", "safe": "value"},
        "items": [{"password": "secret"}, {"safe": "also-safe"}],
    }

    get_logger("attendance_crmt.test").info("production event", payload=payload)

    event = json.loads(output.getvalue())
    assert event["payload"] == {
        "token": "[REDACTED]",
        "nested": {"Authorization": "[REDACTED]", "safe": "value"},
        "items": [{"password": "[REDACTED]"}, {"safe": "also-safe"}],
    }
    assert payload == {
        "token": "top-secret",
        "nested": {"Authorization": "Bearer secret", "safe": "value"},
        "items": [{"password": "secret"}, {"safe": "also-safe"}],
    }


async def _emit_bound_identity_event() -> None:
    tokens = bind_identity_context(subject="tenant:user", client_id="client")
    try:
        await asyncio.sleep(0)
        get_logger("attendance_crmt.test").info("bound identity event")
    finally:
        reset_identity_context(tokens)


def test_identity_context_survives_async_work_and_is_cleaned_up() -> None:
    output = io.StringIO()
    configure_structlog("production", stream=output)

    asyncio.run(_emit_bound_identity_event())
    get_logger("attendance_crmt.test").info("unbound identity event")

    bound, unbound = map(json.loads, output.getvalue().splitlines())
    assert bound["subject"] == "tenant:user"
    assert bound["client_id"] == "client"
    assert bound["authentication_scheme"] == "bearer"
    assert "subject" not in unbound
    assert "client_id" not in unbound


def teardown_function() -> None:
    structlog.reset_defaults()
