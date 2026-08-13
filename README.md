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
with the legacy SQL Server attendance mappings. Until the Teams bot introduces
an authenticated caller identity, records use `actor_id = "mcp"` deliberately;
they do not claim to identify an end user.

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
│       ├── audit.py        # Audit ORM model and persistence
│       ├── audit_middleware.py # Cross-cutting MCP tool auditing
│       ├── dependencies.py # Production and test infrastructure composition
│       ├── server.py       # Server composition and `mcp` entry point
│       └── tools/          # Isolated tool registrations
├── tests/
│   ├── unit/               # Isolated model and settings tests
│   ├── integration/        # FastMCP and database-backed behavior tests
│   └── conftest.py         # Shared test fixtures
├── pyproject.toml          # Project metadata and dependencies
└── uv.lock                 # Locked dependency graph
```

## Adding a tool

1. Add a focused module under `src/attendance_crmt/tools/`.
2. Expose a registration function from `tools/__init__.py`.
3. Register it in `create_server()` in `server.py`.
4. Add a behavior-level test under `tests/`.

## License

Add a license appropriate for your project before distribution.
