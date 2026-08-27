"""Attendance CRMT FastMCP server package."""


def main() -> None:
    """Run the production FastMCP server through stdio."""
    from attendance_crmt.server import create_production_server

    create_production_server().run(transport="stdio")


__all__ = ["main"]
