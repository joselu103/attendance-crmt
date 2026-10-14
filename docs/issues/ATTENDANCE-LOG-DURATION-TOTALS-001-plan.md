# ATTENDANCE-LOG-DURATION-TOTALS-001 — REST owner plan

Status: planning complete in this owner worktree; implementation is not started
or authorized by this report. All three owner plans must be reconciled before
the coordinator dispatches implementation. This report changes no readiness gate.

## Evidence and authority

- Owner: Attendance CRMT REST API only, worktree
  `/home/joselu/orca/workspaces/attendance-crmt/log-duration-totals`, branch
  `joselu103/log-duration-totals`.
- Initial worktree was clean. HEAD, local main, and local origin/main all equal
  `70a4fb54b8389d7436ff490fad7643b384f3fa80`. No remote refresh was performed.
- Read local AGENTS.md, AGENT_STATE.json, active AGENT_INBOX.md, all four
  agent-guidance documents, issue-tracker/domain guidance, REST v1 contract,
  and ADR 0001. Local CONTEXT.md, codex-handoff.md, and next-action.md do not
  exist; root handoff and next-action were read at the shared root instead.
- The shared issue packet in
  `/home/joselu/orca/workspaces/attendance-crmt-master/ribboneel/docs/issues/`
  is copied verbatim beside this report. Root handoff establishes merged history
  pagination and subsequent Teams daily splitting as existing source behavior.
  Historical inbox/state downstream wording does not reopen those merged slices.
- Inspected contracts.py, services.py, models.py, REST routes, OpenAPI examples,
  synthetic fixtures, and existing requester/admin/history/detail/report tests.
- `uv sync --locked --all-groups` created the local Python 3.14.2 environment.
  Baseline clean-environment pytest: **168 passed**. Ruff check passed; format
  check passed for **70 files**. These verify existing source, not new metrics.
- A read-only synthetic Python probe confirmed spring/fallback whole-day UTC
  durations of 1,380/1,500 minutes and 01:30–03:30 intervals of 60/180 minutes
  on 2026-03-29/2026-10-25. A spring gap pair 02:50–03:10 serializes to a
  negative UTC interval despite ascending wall times; it must yield null.
- A synthetic SQLAlchemy MSSQL compilation confirmed the proposed overlap
  predicate and stable timestamp/event-ID order compile with offset/lookahead.
  This is not SQL Server execution or query-plan evidence.

Coordinator reply to the planning question explicitly authorizes checked-in ORM
and synthetic tests for this no-schema-change source task, preserving existing
Europe/Ljubljana serializer/default-fold interpretation. Production DDL absence
is an external verification limitation, not a local implementation blocker.
No different DST policy, schema migration, index/constraint change, SQL Server
access, or secret access is authorized.

## Scope and public interface

Only these existing protected routes change their success body and selection:

- `GET /api/v1/me/attendance-events`
- `GET /api/v1/employees/{employee_id}/attendance-events`

Keep `AttendanceEventPage` as the page type. Introduce immutable
`AttendanceHistoryEvent(AttendanceEventSummary)` with a required nullable
nonnegative integer `duration_minutes`, and immutable
`AttendanceHistorySummary` with required nonnegative integer
`page_duration_minutes` and `period_duration_minutes`. Change page items to
`tuple[AttendanceHistoryEvent, ...]` and add required root `summary` of that
summary type. Null is explicit for unavailable item durations; totals are always
integers, including zero on empty pages. No default or compatibility fallback
should hide a missing metric in downstream contracts.

Existing event fields, timestamp serialization, items ordering, limit, offset,
and next_offset remain. `AttendanceEventSummary`, `AttendanceEventDetail`, latest
event, daily attendance events, current attendance, reports, planned work,
requester aggregate hours, and all other success bodies remain unchanged.
Do not add duration to their common base. In OpenAPI examples construct the
history item by extending a copy of `_EVENT_EXAMPLE`; do not mutate that shared
example or add metrics to detail/daily/latest examples.

Preserve `/api/v1`, header `X-Attendance-API-Contract-Version: 1.0.0`, package
`0.1.0`, and every existing development version label. This pre-release approved
change requires downstream typed consumers to accept the fields, with no legacy
compatibility work. MCP remains a transparent bearer/correlation and response
forwarder; Teams owns only localized presentation and daily segment arithmetic.
No new REST endpoint, argument, identity selector, dependency, or migration.

## Selection and arithmetic decisions

For normal dates let S be start-date local midnight and E be local midnight
after end-date. Bind naive local boundaries to the existing naive database
columns; use the interval [S, E). Do not cast/date-extract timestamps or use
SQL Server timezone conversion or DATEDIFF for metrics.

The page query always restricts `att_user_id` to the authorized employee and
requires non-null `att_in`. Its predicate is:

`att_in < E AND (att_in >= S OR att_out IS NULL OR att_out > S)`.

This retains every formerly eligible in-range check-in, including incomplete,
reversed, zero-length, and UTC-invalid records. It also includes completed
events crossing into the period and active pre-period punches regardless of
age. Do not impose a current-time cutoff. An event ending exactly at S is
excluded unless its check-in itself is in range (for example a zero at S).
An event starting exactly at E is excluded. Missing check-in records were
previously excluded and remain excluded, including out-only records; a generic
history-item duration function still handles either missing endpoint as null.

Keep database ascending `att_in, att_id`, offset, and `limit + 1`; trim the
lookahead before constructing items or page sums. No Python pagination or union
duplicates. Preserve default 50, limit 1–100, nonnegative offset, explicit
inclusive unbounded date periods, future ends, and safe existing validation.

Interpret each endpoint exactly as the existing JSON serializer does:
`replace(tzinfo=ZoneInfo("Europe/Ljubljana"))`, preserving its fold/default
behavior, then convert separately to UTC before subtraction. A missing endpoint,
stored end before stored start, or negative UTC delta yields null. Exact zero
yields 0. For a nonnegative delta use integer timedelta division by one minute,
which avoids floating-point rounding at minute boundaries. No naive wall-time
subtraction or subtraction with the same local-zone tzinfo.

`page_duration_minutes` sums non-null full durations of returned items only,
including independent overlapping events. It is not clipped, grouped by day,
limited to work punch types, or reduced by overlap merging. The lookahead is
excluded. Consequently page sum can exceed period sum and can differ from the
sum of independently truncated Teams daily segments.

The period query has the same employee restriction, no offset/limit, and selects
only `(att_id, att_in, att_out)` with both endpoints present,
`att_in < E`, and `att_out > S`. Do not hydrate relationships, notes, or the
entire unpaged ORM graph. Iterate its result within the same session, using
bounded batches if needed; avoid an unbounded full-period object/cache list.
SQL is a candidate filter; Python applies raw/UTC validity and exact UTC
clipping. For each valid completed event, convert endpoints and calendar
boundaries to UTC, clip to [S_UTC, E_UTC), and truncate that contribution before
summing. Reject negative/empty overlap; zero contributes 0. Count overlaps
independently. Active and invalid intervals contribute nothing, including active
pre-period rows. Never call the existing capped summary/report service: its
hours, daily splitting, and scope are different.

Compute each candidate's full duration once and reuse it if wholly contained;
only boundary-crossing candidates require clipped elapsed arithmetic. For a
wholly contained row also returned on the page, reuse its actual
`duration_minutes` when `(id, in, out)` matches the page cache. A changed row with
the same ID must not reuse stale endpoints. Keep this cache bounded by page size.
Do not aggregate floored sums at SQL level or floor once after adding seconds.

The two reads share the existing service session, but no transaction isolation
or snapshot guarantee is added. Concurrent changes can affect reads within a
request or across pages. Each page recalculates its current full-period total;
clients never accumulate period totals across continuations. A beyond-last page
has no items, page sum 0, next_offset null, and the current period sum.

Avoid a new overflow for the already accepted `end_date=date.max`: represent the
unrepresentable following local midnight as an open upper sentinel, omit the
SQL upper predicate, and treat every representable stored endpoint as before
that conceptual boundary. With that sentinel no event needs upper clipping;
reuse full duration or clip the lower boundary only. Convert calendar boundaries
to UTC lazily when clipping is needed, so an ancient start date outside SQL
DATETIME's stored domain does not require an overflowing UTC conversion merely
to sum wholly contained events. Do not add a date-span cap or widen SQL Server's
existing representable timestamp domain. Test the max-date empty and normal-row
cases through both public routes.

## Scoped implementation sequence after reconciliation

1. Add behavior-level failing tests at both HTTP routes for new fields, overlap,
   clipped unpaged totals, independent truncation, anomalies, DST, and empty
   beyond-last pages; run the focused tests and record actual RED failures.
   Expected failures are absent summary/duration and missing pre-period rows.
2. Add the history-specific immutable types in
   `src/attendance_crmt/attendance/contracts.py`. Add a narrow history item
   conversion, UTC elapsed helper, calendar-boundary handling, and unpaged scalar
   total query only around `_list_attendance_events_for_employee` in services.py.
   Preserve public service entry points and their authorization checks.
3. Extend only history OpenAPI examples in openapi_responses.py. Existing REST
   response_model references already point to AttendanceEventPage; no route
   execution/authentication/audit restructuring is needed.
4. Run focused GREEN, retaining historical authorization/pagination regressions.
   Add actual wire/OpenAPI absence checks for latest/detail/daily event shapes,
   not only tests against internal model instances. Keep unrelated report
   arithmetic and existing report validation behavior outside this change.
5. Update only the history sections of REST contract and relevant service-boundary
   guidance from check-in-only filtering to overlap/anomaly-preserving selection,
   documenting integer full/clipped totals, DST limitations, and unchanged version.
   After all checks pass, publish factual local evidence and handoff in owner state
   and active inbox/new task report without clearing external readiness gates.

No source or test changes are made by this planning dispatch. No AGENT_STATE.json
or AGENT_INBOX.md status is advanced during planning.

## Verification matrix and exact commands

Extend existing synthetic SQLite/ASGI fixtures; no production database, token,
personal attendance, env file, or external identity provider is needed. Assert
hard-coded expected IDs and minute totals at HTTP boundaries, not only equality
to the service under test.

| Behavior | Required observable evidence |
| --- | --- |
| Authority | Personal list ignores hostile identity selectors and returns/sums only the server-derived employee; admin can target another employee; nonadmin denied; unmapped identity/auth/correlation/safe error regressions and exactly one durable safe audit outcome per request remain. |
| Boundaries | Before/after/touching S and E; wholly inside; crossing start/end/both; active before S/at S/inside/at E; out-only/both missing unchanged exclusion; in-range reversed/zero/invalid retained; zero at S included, zero at E excluded. |
| Duration | Missing endpoint null; raw reversal null; UTC reversal from spring gap null; zero 0; 59.999999 seconds 0, 60 seconds 1, 119.999999 seconds 1; overlapping events add independently; different punch types all count. |
| Clipping | Full 48-hour event spanning a one-day normal period has item/page 2,880 and period 1,440; contained 8-hour event has item/page/period 480; two 59-second contributions give period 0; a crossing partial minute truncates after clipping. |
| DST | Spring day 1,380, fallback day 1,500; spring 01:30–03:30 60, fallback 01:30–03:30 180; ambiguous 02:30 preserves emitted +02:00 default interpretation; crossing midnight and offset change clips against UTC boundaries. |
| Paging/live data | Tie ordering by ID; limit-plus-one never summed; first/intermediate/final/beyond-last pages have independent page sums and identical period sums for unchanged fixtures; period-only rows outside current page counted; a synthetic edit between requests updates the period total rather than accumulating it. |
| Empty/extremes | No rows/all active gives both sums 0; nonzero period beyond last page retained; limits 1/100 and default 50; unbounded/future ranges unchanged; end date.max does not overflow on either route. |
| Other surfaces | Latest/event detail/daily events expose exactly old fields and no duration/summary; reporting/status/planned-work shapes and date caps unchanged; health unchanged; protected headers and safe OpenAPI error schemas retained. |
| SQL portability | Compile page and scalar-period statements with the MSSQL dialect and synthetic binds; verify employee predicate, explicit null handling, half-open normal boundaries, ordering/offset/lookahead, and no unpaged offset/limit or relationship columns. SQLite behavior tests do not prove SQL Server runtime performance. |

Environment preparation, if absent: `env -u PYTHONPATH -u VIRTUAL_ENV uv sync
--locked --all-groups`; verify `.venv/bin/python --version` is Python 3.14.
Focused RED then GREEN command (same test targets, after adding behavior cases):

```bash
env -u PYTHONPATH -u VIRTUAL_ENV .venv/bin/pytest tests/integration/test_requester_attendance_events_rest_route.py tests/integration/test_administrative_event_list_rest_route.py tests/integration/test_attendance_services.py tests/integration/test_my_attendance_service.py tests/unit/test_requester_attendance_contract.py tests/integration/test_requester_attendance_latest_summary_rest_routes.py tests/integration/test_administrative_attendance_rest_routes.py tests/integration/test_openapi_security.py
```

After final source, test, contract, state, and handoff edits:

```bash
env -u PYTHONPATH -u VIRTUAL_ENV .venv/bin/pytest
env -u PYTHONPATH -u VIRTUAL_ENV .venv/bin/ruff check .
env -u PYTHONPATH -u VIRTUAL_ENV .venv/bin/ruff format --check .
env -u PYTHONPATH -u VIRTUAL_ENV .venv/bin/python -m json.tool AGENT_STATE.json
git diff --check
```

Record actual command results and test counts, and separately name any skips or
SQL execution gaps. The synthetic MSSQL compilation probe is not a replacement
for runtime deployment verification. No new broad test framework is necessary.

## Dependencies, blockers, and limits

- Local source design has no unresolved product decision after the coordinator's
  DST/DDL reply. Implementation still depends on reconciliation of all three
  plans and a fresh implementation dispatch with the specified effective model.
  The shared packet selects GPT-5.6 for REST interval arithmetic; downstream
  defaults remain GPT-6 Luna unless their plans establish greater complexity.
- MCP implementation starts only after actual REST RED/GREEN, full-check, and
  contract evidence. Handoff must name required nullable duration, required root
  summary and integer totals, selection boundaries, unchanged REST 1.0.0 and
  pre-release labels, live-page caveat, and fixtures useful for transport tests.
  MCP must calculate neither durations nor totals. Teams starts after verified
  MCP and consumes full item duration/current period total; its existing daily
  splitting/clipping is presentation work owned downstream.
- Naive columns cannot identify the actual fold of ambiguous fallback punches;
  gap wall times may also be invalid. Metrics are consistent with the existing
  emitted offsets, not proof of physical elapsed time for unknowable data. Do
  not invent offsets, infer fold from duration, normalize stored timestamps,
  change serializers, or migrate schema as part of this task.
- SQL ORM currently maps nullable `att_in`/`att_out` as timezone-naive DateTime
  in `dbo.att_attendance_log`. No authoritative production DDL/index/constraint
  or real query-plan evidence was found. The coordinator explicitly keeps this
  external limitation separate from local implementation; do not infer or change
  schema. Unbounded-period aggregation is necessarily proportional to matching
  completed rows; scalar streaming controls memory, not database scan cost.
- Existing Entra, deployed HTTPS/container, approved SQL access, audit policy,
  provider/privacy, secrets, and real-account gates remain exactly as recorded
  in owner state. Baseline tests and the eventual source metrics checks clear
  none of them. No commits/pushes/PRs/merges/deployments, public notices, or external
  resource changes are in scope.
