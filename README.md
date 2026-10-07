# Attendance CRMT

Attendance CRMT is the protected REST authority for attendance identity,
authorization, audit, rules, and SQL Server access.

## REST v1

The complete REST v1 operation inventory is in
[`docs/contracts/attendance-rest-v1.md`](docs/contracts/attendance-rest-v1.md).
Protected routes require exactly one delegated bearer token and one UUID
`X-Correlation-ID`. CRMT validates the approved client application,
`attendance.access` scope, audience, tenant, and requester identity; it derives
the employee and authorization result server-side and records safe,
correlation-linked audit outcomes.

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
