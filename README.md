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
tools. The example `echo` tool returns a supplied message unchanged.

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

## Continuous integration

GitHub Actions runs linting, formatting checks, tests, and a Docker image build
for pull requests. Pushes to `main` additionally publish the image to GitHub
Container Registry as `ghcr.io/<owner>/attendance-crmt:latest` and with a
commit-SHA tag.

## Development

```bash
# Run tests
uv run pytest

# Check formatting and linting
uv run ruff check .
uv run ruff format --check .
```

## Project layout

```text
.
├── src/
│   └── attendance_crmt/
│       ├── server.py       # Server composition and `mcp` entry point
│       └── tools/          # Isolated tool registrations
├── tests/                  # Server behavior tests
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
