"""Attendance CRMT protected REST authority."""


def main() -> None:
    """Run the production REST application."""
    import uvicorn

    uvicorn.run(
        "attendance_crmt.server:create_production_http_app",
        factory=True,
        host="0.0.0.0",
        port=8000,
    )


__all__ = ["main"]
