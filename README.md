# Attendance CRMT

Attendance CRMT is the protected REST authority for attendance identity,
authorization, audit, rules, and SQL Server access.

## REST v1

The complete `/api/v1` operation inventory and pilot migration rules are in
[`docs/contracts/attendance-rest-v1.md`](docs/contracts/attendance-rest-v1.md).
Protected routes require exactly one delegated bearer token and one UUID
`X-Correlation-ID`. CRMT validates the approved client application,
`attendance.access` scope, audience, tenant, and requester identity; it derives
the employee and authorization result server-side and records safe,
correlation-linked audit outcomes.

For the pilot, mapped employees read current coworkers' names and work-status
categories from `GET /api/v1/attendance/current-status`; CRMT chooses the
current Europe/Ljubljana time and accepts no client date or identity selector.
The existing detailed `GET /api/v1/attendance/current` route is now
administrator-only. Existing non-administrator clients must migrate to the
category-only route before pilot traffic; the pre-release contract version
remains `1.0.0`.

Personal and administrator attendance-event listings require explicit start and end
dates with no maximum span; future end dates are allowed. Both dates are
inclusive Europe/Ljubljana calendar dates. Pagination remains default 50,
limit 1–100, nonnegative offset, and `next_offset` for continuation. Pages read
live data in timestamp/event-ID order, without a snapshot guarantee. Summary,
report, and planned-work date limits remain unchanged. This additive acceptance
change preserves REST `1.0.0`, routes, and response fields.

Interactive API documentation is available at `/docs` and `/redoc`. In Swagger
UI, use **Authorize** to enter a delegated Attendance bearer token, then supply
a UUID in the required `X-Correlation-ID` header for each protected request.
Never paste a token into source files, tickets, or other persistent records.
The generated documentation includes the concrete response schema and a
synthetic example for each operation; examples never contain attendance data.

`GET /health` returns `200 {"status":"ok"}` and is liveness only. It does not
check SQL Server, Entra, or audit readiness.

## Run and verify

```bash
uv sync --locked --all-groups
uv run attendance-crmt
env -u PYTHONPATH -u VIRTUAL_ENV .venv/bin/pytest
env -u PYTHONPATH -u VIRTUAL_ENV .venv/bin/ruff check .
env -u PYTHONPATH -u VIRTUAL_ENV .venv/bin/ruff format --check .
```

Copy `.env.example` to `.env` and configure the approved REST service URL,
Entra API audience, scope, and client-application allow-list. Never commit
credentials, tokens, connection strings, certificates, or attendance data.
