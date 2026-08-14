from datetime import date, datetime
from decimal import Decimal

from attendance_crmt.attendance.contracts import PlannedWorkQuery
from attendance_crmt.attendance.services import get_planned_work
from attendance_crmt.identity import Requester
from attendance_crmt.models import PlannedWork


def test_planned_work_service_returns_recorded_daily_hours_only(
    employee_session_factory,
    employee_factory,
) -> None:
    employee = employee_factory.build(izvajalec_id=42)
    with employee_session_factory() as session:
        session.add_all(
            [
                employee,
                PlannedWork(
                    izvajalec_id=employee.izvajalec_id,
                    datum_id=datetime(2026, 8, 10),  # noqa: DTZ001
                    att_planirano_ur_va=Decimal("8.00"),
                ),
                PlannedWork(
                    izvajalec_id=employee.izvajalec_id,
                    datum_id=datetime(2026, 8, 12),  # noqa: DTZ001
                    att_planirano_ur_va=Decimal("6.00"),
                ),
            ]
        )
        session.commit()

    result = get_planned_work(
        requester=Requester(actor_id="admin", roles=frozenset({"admin"})),
        session_factory=employee_session_factory,
        query=PlannedWorkQuery(
            employee_id=employee.izvajalec_id,
            start_date=date(2026, 8, 10),
            end_date=date(2026, 8, 12),
        ),
    )

    assert [(item.day, item.planned_hours) for item in result.items] == [
        (date(2026, 8, 10), Decimal("8.00")),
        (date(2026, 8, 12), Decimal("6.00")),
    ]
