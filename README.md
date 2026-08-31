# attendance-crmt

A clean, modular [FastMCP](https://gofastmcp.com/) server scaffold managed by
[uv](https://docs.astral.sh/uv/).

## Requirements

- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Python 3.14 or newer (installed automatically by uv when needed)

## Quick start

```bash
uv sync
uv run fastmcp dev src/attendance_crmt/server.py
```

The development inspector opens a local interface for exercising the server's
tools.

## Run as an MCP server

Run the package entry point over standard input/output:

```bash
uv run attendance-crmt
```

## Run with Docker

The container exposes the streamable HTTP MCP endpoint on port 8000 at
`/mcp`.

```bash
docker compose up --build
```

Stop the service with `docker compose down`.

## Database configuration

The attendance mappings use SQLAlchemy with the Microsoft SQL Server `pyodbc`
dialect. Configure a **read-only** connection first while the MCP capabilities
are being discovered. Copy the tracked template to an ignored `.env` file and
set the URL; never commit the resulting file.

```bash
cp .env.example .env
```

`pydantic-settings` reads `.env` during local development. Environment
variables override it, so production deployments should inject
`ATTENDANCE_DATABASE_URL` from their platform secret manager rather than
shipping a `.env` file. `attendance_crmt.database.create_engine_from_environment()`
constructs the engine lazily, so importing the application does not connect to
SQL Server.

Docker Compose passes the ignored local `.env` file into the container at
runtime; it is not copied into the image. Create `.env` before running
`docker compose up --build`.

## Entra delegated-user authentication

The `/mcp` endpoint is a protected, delegated-user boundary. Production starts
with Entra OpenID metadata/JWKS token verification and derives the requester
from signed claims; it does not use a configured administrator fallback.

Set these values in the platform secret/configuration manager (or in the local
ignored `.env` copied from `.env.example`):

| Variable | Purpose |
| --- | --- |
| `ATTENDANCE_MCP_BASE_URL` | Public MCP base URL. Must use HTTPS in production. |
| `ATTENDANCE_ENTRA_TENANT_ID` | Single accepted Entra tenant UUID. |
| `ATTENDANCE_ENTRA_ISSUER` | Expected issuer URL. |
| `ATTENDANCE_ENTRA_OPENID_CONFIGURATION_URL` | OpenID metadata URL on the same authority as the issuer. |
| `ATTENDANCE_ENTRA_AUDIENCE` | Exact Attendance CRMT API audience. |
| `ATTENDANCE_ENTRA_ALLOWED_CLIENT_IDS` | Non-empty JSON array of approved Teams bot client UUIDs. |
| `ATTENDANCE_ENTRA_REQUIRED_SCOPE` | Delegated scope; defaults to `attendance.access`. |
| `ATTENDANCE_ENTRA_CLOCK_SKEW_SECONDS` | Temporal-claim leeway from 0 to 300; defaults to 60. |
| `ATTENDANCE_ENTRA_ADMIN_ROLE` | Exact Entra app role that grants `admin`; defaults to `attendance.admin`. |

The server accepts only RS256-signed delegated tokens discovered through the
configured tenant metadata. It requires the configured tenant, issuer, exact
audience, approved client, delegated scope, temporal claims, `oid`, and a
nonblank `preferred_username`; app-only tokens are rejected. Missing credentials
return `AUTHENTICATION_REQUIRED`; supplied credentials that fail validation return
`TOKEN_INVALID`. Responses use stable safe messages and never include token,
claim, signature, or metadata diagnostics.

After validation, the server trims and case-insensitively maps
`preferred_username` to exactly one active `dbo.izvajalci.email` row. That user
receives `employee`; only the exact configured Entra app role adds `admin`.
Unmapped and duplicate mappings return `IDENTITY_UNMAPPED` and
`IDENTITY_AMBIGUOUS` respectively. Tests use explicitly injected static fake
requesters; production does not.

## Teams bot MCP client contract

The versioned client contract is
[`docs/integrations/teams-bot-mcp-auth-contract.md`](docs/integrations/teams-bot-mcp-auth-contract.md).
Its first requester-scoped operation is `list_my_attendance_events` over MCP
Streamable HTTP at `/mcp`.

Clients send `start_date`, `end_date`, optional `limit` (1-100, default 50),
and optional nonnegative `offset`; the inclusive Europe/Ljubljana date range is
at most 31 calendar days. Clients must not send an employee ID, email, role, or
any other identity selector. CRMT derives the employee, validates the request,
authorizes access, and records the audit event. Invalid range or pagination
values are MCP tool errors with the stable `INVALID_ARGUMENT` code.

## Audit and structured logging

Every successful or failed MCP tool interaction that reaches a registered tool
is recorded in a local SQLite audit database. Audit persistence uses a separate
SQLAlchemy metadata base, engine, and session factory, so it cannot interfere
with the production SQL Server attendance mappings. Audit records use the
server-derived requester identity; production derives it from a validated
delegated token, while isolated tests inject an explicit fake.

`ATTENDANCE_AUDIT_DATABASE_PATH` selects the database path and defaults to
`data/audit.sqlite3`. Startup performs an additive SQLite migration: historic
rows are retained and the nullable `employee_id`, `roles_json`,
`correlation_id`, and `error_code` columns remain null where history has no
truthful value. Back up the persistent audit volume before cleanup or recovery
operations.

Authenticated HTTP MCP clients must send exactly one UUID
`X-Correlation-ID` on every request. The server normalizes it, records it with
new audit rows, and publishes contract version `1.2.0` in
`X-Attendance-MCP-Contract-Version`. Direct in-memory tests explicitly inject a
fixed correlation resolver.

Docker
Compose mounts `/app/data` as the persistent `attendance-audit` volume, so the
audit history survives a container replacement. Back up that volume before
performing destructive Docker cleanup.

The server emits newline-delimited JSON through `structlog` to standard error.
Each interaction log includes `timestamp`, `level`, `event`, `tool_name`,
`outcome`, and `duration_ms`, ready for a future log collector or analysis
tool. Request values are stored in SQLite with common sensitive fields
(`authorization`, `cookie`, `password`, `secret`, and `token`) redacted.

Production composition creates database infrastructure from environment
settings once during server startup. Tests inject `ServerDependencies` with
isolated session factories instead of relying on a shared `.env.test` file.

## Continuous integration

GitHub Actions runs linting, formatting checks, tests, and a Docker image build
for pull requests. Pushes to `main` additionally publish the image to GitHub
Container Registry as `ghcr.io/<owner>/attendance-crmt:latest` and with a
commit-SHA tag.

## Development

```bash
# Run tests
uv run pytest

# Run an individual test category
uv run pytest tests/unit
uv run pytest tests/integration

# Check formatting and linting
uv run ruff check .
uv run ruff format --check .
```

## Project layout

```text
.
├── src/
│   └── attendance_crmt/
│       ├── attendance/       # Reusable attendance contracts, services, and MCP tools
│       ├── audit.py        # Audit ORM model and persistence
│       ├── audit_middleware.py # Cross-cutting MCP tool auditing
│       ├── catalog/          # Reusable catalog contracts, services, and MCP tools
│       ├── dependencies.py # Production and test infrastructure composition
│       ├── identity.py     # Claim-derived requester identity and test fakes
│       ├── server.py       # Server composition and `mcp` entry point
├── tests/
│   ├── unit/               # Isolated model and settings tests
│   ├── integration/        # FastMCP and database-backed behavior tests
│   └── conftest.py         # Shared test fixtures
├── pyproject.toml          # Project metadata and dependencies
└── uv.lock                 # Locked dependency graph
```

## Read-only attendance tools

The MCP surface is intentionally thin. Each feature tool resolves requester
identity and delegates to a transport-independent contract and application
service, which future REST endpoints can reuse.

- `list_employees` — paginated active-employee discovery.
- `get_employee` — one employee's directory-safe metadata.
- `list_punch_types` — configured punch types with server-derived locations.
- `list_locations` — attendance-event location reference data.
- `list_attendance_events` — administrator-only raw attendance-event drill-down.
- `list_my_attendance_events` — requester-scoped raw attendance-event history;
  its employee identity is server-derived and never a tool argument.
- `get_attendance_event` — administrator-only event detail including recorded audit
  metadata.
- `get_daily_attendance` — administrator-only local-calendar event and
  planned-versus-logged daily view.
- `get_planned_work` — administrator-only recorded daily planned-work rows; absent
  rows remain unknown rather than zero.
- `get_current_attendance` — paginated live status for active employees; omitted
  or `null` `as_of` uses the current Europe/Ljubljana local time.
- `get_employee_attendance_analysis` — administrator-only 31-day employee
  analysis with grouped logged hours, planned-work comparison, daily detail,
  incomplete intervals, and overlap anomalies.
- `get_employee_attendance_summary` — administrator-only compact 31-day hours,
  planned-work, punch-type, and anomaly summary without daily detail.
- `get_organization_attendance_analysis` — administrator-only 31-day active
  workforce totals plus paginated employee summaries without daily detail.
- `get_exceptions` — administrator-only paginated operational report for missing
  attendance, incomplete intervals, and interval anomalies.

## Adding a feature tool

1. Add or extend immutable contracts and a reusable service under the relevant
   feature package (for example, `attendance/`).
2. Add a thin MCP adapter in that feature's `tools.py`; do not place query,
   authorization, aggregation, or ORM mapping behavior in the adapter.
3. Register the feature adapter from `create_server()` when it is not already
   registered.
4. Add direct service integration coverage plus MCP behavior coverage where the
   transport boundary contributes behavior.

## License

Add a license appropriate for your project before distribution.
