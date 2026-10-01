# Attendance CRMT REST Core

Attendance CRMT is the protected REST authority for attendance identity,
authorization, audit, rules, and SQL Server access.

**Output Rule:** Wait for operations to finish. On success, output ONLY 3-5 bullet points summarizing results. No diffs, code dumps, or long explanations. (Details: `docs/agent-guidance/response-guide.md`)

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

## Agent skills

### Issue tracker

Issues and specs are tracked in this repository's GitHub Issues. See `docs/agents/issue-tracker.md`.

### Triage labels

Uses the default five-label triage vocabulary. See `docs/agents/triage-labels.md`.

### Domain docs

Uses the single-context domain-doc layout. See `docs/agents/domain.md`.
