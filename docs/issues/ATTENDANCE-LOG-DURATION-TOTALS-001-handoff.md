# ATTENDANCE-LOG-DURATION-TOTALS-001 — REST handoff

## Readiness

The repository-owned REST source slice is complete and locally verified. MCP may
now forward the history response fields transparently; it must not calculate or
rewrite duration totals. REST remains version `1.0.0`; routes, arguments,
authorization, auditing, pagination shape, and non-history event shapes are
unchanged.

## Wire contract

Both `GET /api/v1/me/attendance-events` and
`GET /api/v1/employees/{employee_id}/attendance-events` now return
`items[].duration_minutes`, `summary.page_duration_minutes`, and
`summary.period_duration_minutes`. `duration_minutes` is required but nullable,
and is full-event elapsed UTC minutes using the emitted Europe/Ljubljana
default-fold timestamp interpretation. Missing endpoints, raw reversal, and UTC
reversal are null; zero is zero. Page totals sum non-null returned-item durations
only, excluding lookahead. Period totals stream valid completed overlaps without
pagination, clip each to the inclusive-date half-open period, truncate each
contribution independently, and count overlaps independently.

## Selection and limits

The page selects `att_in < exclusive_end` plus an in-range check-in, active null
checkout, or checkout after period start. Thus active pre-period punches and
in-range anomalies display, but do not add to period totals if incomplete or
invalid; records without a check-in remain excluded. `end_date=9999-12-31`
uses an open upper sentinel. Totals are recalculated for each live request, not
accumulated across pages. Naive database timestamps cannot recover actual DST
folds; metrics intentionally match the existing serializer rather than proving
physical-time certainty.

## Verification and external limits

Behavior RED: 4 targeted tests failed for intentionally absent overlap
selection, duration/summary fields, and OpenAPI types. GREEN: the same 4 passed;
the focused synthetic REST/contracts/OpenAPI suite passed 57 tests and the full
clean-environment suite passed 173. Ruff check, Ruff format check, state JSON,
and `git diff --check` passed. Synthetic coverage includes 48-hour crossing,
one-day clipping, 480-minute contained rows, active/reversed/zero rows,
59-second truncation, spring/fallback elapsed intervals, beyond-last pages, and
both public routes with `date.max`.

No authoritative SQL Server DDL/index/query-plan or runtime execution, deployed
HTTPS service, Entra configuration, persistent-audit operating policy, real
account, or production attendance-data evidence was used. Those external gates
remain blocked and local source verification clears none of them.
