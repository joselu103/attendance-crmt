# Directive: ATTENDANCE-HISTORY-PAGINATION-001

> **Status:** Completed repository-owned REST source slice; MCP source ready.

Both personal and administrator attendance-event listings accept explicit inclusive
Europe/Ljubljana start/end dates without a maximum span, including future ends.
REST `1.0.0`, routes, arguments, fields, default 50, limit 1–100, nonnegative
offset, `next_offset`, inclusive SQL filtering, timestamp/event-ID ordering,
offset/limit-plus-one lookahead, requester isolation, admin authorization, and
durable correlation-linked auditing are preserved. Requester model validation
now translates reversed dates and invalid pagination into safe `INVALID_ARGUMENT`
instead of the existing dependency-construction 500. Summary/report/planned-work
caps remain unchanged. Pages read live data without a snapshot guarantee.

Evidence: clean worktree at `4f36403`, branch `joselu103/history-pagination`;
`uv sync --locked --all-groups`, Python 3.14.2; wider-period route RED 4 failed,
minimal GREEN 4 passed; requester invalid-bound RED 4 failed, safe validation
GREEN passed. Focused history/contracts/latest-summary tests: 42 passed. Full
clean-environment pytest: 168 passed. Ruff check and format check passed; state
JSON validation and `git diff --check` passed after the final edit.

MCP and Teams have now completed their local history slices with 57 and 247
passing tests respectively, consuming this unchanged interface/version;
no deployed end-to-end readiness is claimed. Existing deployment, Entra, database,
audit-policy, privacy, and secret gates remain. Synthetic unrelated long-range
probes found existing report/planned-work validation errors returning 500; their
caps remain enforced at the public contract seam and those routes were not changed.
No secrets/env files or personal data read; no external changes, commits, pushes,
PRs, merges, or subagents used.

## Historical completed directive

# Directive: CRMT-MCP-BOUNDARY-CLEANUP-001

> **Status:** Completed repository-owned cleanup.

Attendance CRMT is a protected REST-only authority. It owns delegated Entra
validation, client-application allow-list enforcement, server-derived
principals, authorization, correlation-linked audit outcomes, rules, and SQL
Server access. The REST v1 contract is `1.0.0`; the full operation inventory is
in `docs/contracts/attendance-rest-v1.md`.

The embedded MCP bridge, its dependencies, session-admission route, verifier
commands, tests, and transport-specific documentation were removed. Direct
requests to `/mcp` have no compatibility endpoint. External transport adapters
must use the documented REST surface and forward the delegated bearer and UUID
correlation ID; CRMT validates each protected REST request independently.

This local work does not establish a deployment, Entra registration or consent,
SQL Server runtime access, persistent audit storage, or production readiness.
