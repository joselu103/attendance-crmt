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

## Audit and structured logging

Every successful or failed MCP tool interaction that reaches a registered tool
is recorded in a local SQLite audit database. Audit persistence uses a separate
SQLAlchemy metadata base, engine, and session factory, so it cannot interfere
with the production SQL Server attendance mappings. Audit records use the
server-derived MVP requester identity; future MCP or REST authentication can
replace that resolver without changing feature services.

`ATTENDANCE_AUDIT_DATABASE_PATH` selects the database path and defaults to
`data/audit.sqlite3`. The local `data/` directory is ignored by Git. Docker
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
│       ├── identity.py     # Requester identity and MVP resolver
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
- `list_attendance_events` — administrator-only raw attendance-event drill-down.
- `get_current_attendance` — paginated live status for active employees; omitted
  or `null` `as_of` uses the current Europe/Ljubljana local time.
- `get_employee_attendance_analysis` — administrator-only 31-day employee
  analysis with grouped logged hours, planned-work comparison, daily detail,
  incomplete intervals, and overlap anomalies.
- `get_employee_attendance_summary` — administrator-only compact 31-day hours,
  planned-work, punch-type, and anomaly summary without daily detail.
- `get_organization_attendance_analysis` — administrator-only 31-day active
  workforce totals plus paginated employee summaries without daily detail.

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
