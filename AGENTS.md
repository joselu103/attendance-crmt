# Attendance CRMT REST Core

Attendance CRMT is the protected REST authority for attendance identity,
authorization, audit, rules, and SQL Server access; the embedded FastMCP runtime
is a temporary compatibility bridge.

Use `uv` with Python 3.14. Before changing code, read `AGENT_STATE.json`, the
active `AGENT_INBOX.md`, and the applicable root guidance. Use the clean
environment commands below for the required Python checks:

```bash
env -u PYTHONPATH -u VIRTUAL_ENV .venv/bin/pytest
env -u PYTHONPATH -u VIRTUAL_ENV .venv/bin/ruff check .
env -u PYTHONPATH -u VIRTUAL_ENV .venv/bin/ruff format --check .
```

Load task-specific guidance:

- [Service boundary and invariants](docs/agent-guidance/service-boundary.md)
- [REST migration and compatibility](docs/agent-guidance/rest-migration.md)
- [Verification and state](docs/agent-guidance/verification-and-state.md)
- [Existing integration references](docs/integrations/teams-bot-mcp-auth-contract.md)
