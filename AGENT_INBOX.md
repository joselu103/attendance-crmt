# Directive: ATTENDANCE-LOG-DURATION-TOTALS-001

> **Status:** Completed repository-owned REST source slice; MCP may proceed.

Both history pages now emit `items[].duration_minutes` and root
`summary.page_duration_minutes` / `summary.period_duration_minutes`; this is an
approved additive history-only wire change under REST `1.0.0`. Item durations
are integer UTC elapsed minutes under the existing Europe/Ljubljana serializer
interpretation (missing/reversed intervals are null); page totals sum returned
non-null full durations, while period totals stream valid completed overlaps,
clip each independently, and truncate each contribution before summing.

Personal and administrator selection now includes check-ins before the exclusive
period end that are in-range, active, or completed after the local period start.
This preserves in-range anomalies and active pre-period punches; out-only rows
remain excluded. Pagination, ordering, limits, authorization, correlation-linked
audits, REST version, and non-history event shapes are unchanged. `end_date`
`9999-12-31` uses an open upper sentinel without overflow; pages remain live and
their current period total is recalculated on every request.

Evidence: behavior RED 4 failed as expected for missing overlap items and new
wire/OpenAPI fields, then GREEN 4 passed. Synthetic focused suites passed 57
tests; full clean-environment pytest passed 173; Ruff check/format, JSON, and
diff checks passed. The synthetic packet includes 48-hour/one-day clipping
(2,880 item vs 1,440 period minutes), contained 480-minute rows, active/reversed/
zero cases, 59-second truncation, spring/fallback elapsed duration, beyond-last
pages, and both public routes at `date.max`. No real SQL Server execution,
authoritative DDL/query plan, deployment, Entra, audit-policy, or real-account
verification occurred; these external blockers remain.

## Historical completed directive

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
