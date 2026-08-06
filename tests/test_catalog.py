import asyncio
import json

from sqlalchemy import create_engine, event
from sqlalchemy.pool import StaticPool

from attendance_crmt.database import create_session_factory
from attendance_crmt.models import Employee
from attendance_crmt.server import create_server


def test_list_employees_returns_a_bounded_page_of_active_employees() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def attach_dbo(connection, _connection_record) -> None:
        connection.execute("ATTACH DATABASE ':memory:' AS dbo")
        connection.create_collation(
            "SQL_Latin1_General_CP1250_CI_AS",
            lambda left, right: (left > right) - (left < right),
        )

    Employee.__table__.create(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as session:
        session.add_all(
            [
                Employee(
                    izvajalec_id=2,
                    ime="Zala",
                    priimek="Kovač",
                    username="zkovac",
                    email="zala@example.test",
                    active=1,
                ),
                Employee(
                    izvajalec_id=3,
                    ime="Bine",
                    priimek="Vidmar",
                    username="bvidmar",
                    email="bine@example.test",
                    active=1,
                ),
                Employee(
                    izvajalec_id=1,
                    ime="Ana",
                    priimek="Novak",
                    username="anovak",
                    email=None,
                    active=0,
                ),
            ]
        )
        session.commit()

    server = create_server(session_factory=session_factory)
    result = asyncio.run(server.call_tool("list_employees", {"limit": 1, "offset": 0}))

    assert result.is_error is False
    assert json.loads(result.content[0].text) == {
        "items": [
            {
                "employee_id": 2,
                "first_name": "Zala",
                "last_name": "Kovač",
                "username": "zkovac",
                "email": "zala@example.test",
                "active": 1,
            }
        ],
        "limit": 1,
        "offset": 0,
        "next_offset": 1,
    }
