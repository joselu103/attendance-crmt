# Attendance CRMT REST v1 Contract

**Status:** Accepted adapter-facing contract

Attendance CRMT is the authority for bearer validation, requester derivation,
employee mapping, authorization, audit, attendance rules, and SQL Server access.
The standalone Attendance MCP adapter consumes these REST operations; it does
not reproduce those decisions or access SQL Server.

## Common protected-route requirements

Every route in this inventory except `GET /health` requires exactly one
delegated `Authorization: Bearer <token>` header and exactly one UUID
`X-Correlation-ID` header. CRMT derives the principal from the validated token,
requires `attendance.access`, and records a correlation-linked audit outcome
with no request values. Protected responses publish
`X-Attendance-API-Contract-Version: 1.0.0`. This pre-release contract version
remains unchanged for the pilot visibility slice.

The OpenAPI document publishes the delegated bearer security scheme and the
required correlation header for every protected operation. Swagger UI users
enter a delegated token through **Authorize** and provide a UUID correlation ID
when trying an operation; the token is never a documented value. Every
operation publishes its concrete success schema and a synthetic response
example. Protected operations also document the safe error envelope rather
than FastAPI's default validation response.

Safe failures use `{ "code": "...", "message": "..." }`. Authentication
failures return `401`; invalid correlation or arguments return `400`; identity
mapping and authorization failures return `403`; absence returns `404`; and
unavailable audit or database dependencies return `503`. Request values and
diagnostics are never response or audit data.

All attendance dates and database-local timestamps use Europe/Ljubljana local
calendar semantics. Event timestamps are RFC 3339 values with the applicable
Europe/Ljubljana offset. Page `limit` defaults to 50, is 1 through 100, and
`offset` defaults to 0 and is nonnegative.

## REST operation inventory

| Adapter operation | REST v1 operation | Access and input semantics |
| --- | --- | --- |
| `list_employees` | `GET /api/v1/employees?limit=&offset=` | Delegated requester; active directory page. |
| `get_employee` | `GET /api/v1/employees/{employee_id}` | Delegated requester; directory-safe employee record. |
| `resolve_employee` | `GET /api/v1/employees/resolve?employee_id=&username=&email=` | Administrator only; exactly one identifier is required and matches exactly; returns one directory-safe employee. |
| `list_punch_types` | `GET /api/v1/punch-types?active_only=true` | Delegated requester; configured reference data. |
| `list_locations` | `GET /api/v1/locations` | Delegated requester; location reference data. |
| `list_attendance_events` | `GET /api/v1/employees/{employee_id}/attendance-events?start_date=&end_date=&limit=&offset=` | Administrator only; inclusive range is at most 31 calendar days and pagination is bounded. |
| `list_my_attendance_events` | `GET /api/v1/me/attendance-events?start_date=&end_date=&limit=&offset=` | Server-derived employee only; inclusive range is at most 31 calendar days. |
| — | `GET /api/v1/me/attendance-events/latest` | Server-derived employee only; returns the most recent recorded event or safe `NOT_FOUND`. |
| — | `GET /api/v1/me/attendance-summary?start_date=&end_date=` | Server-derived employee only; inclusive range is at most 366 calendar days; returns aggregate recorded time and monthly/location breakdowns. |
| `get_attendance_event` | `GET /api/v1/attendance-events/{attendance_event_id}` | Administrator only; includes recorded audit metadata. |
| `get_daily_attendance` | `GET /api/v1/employees/{employee_id}/daily-attendance?day=` | Administrator only; daily events and calculated outcome. |
| `get_planned_work` | `GET /api/v1/employees/{employee_id}/planned-work?start_date=&end_date=` | Administrator only; inclusive range is at most 31 calendar days. |
| `get_current_work_status` (new pilot mapping) | `GET /api/v1/attendance/current-status?status=&status=&limit=&offset=` | Any mapped delegated employee; server samples the current Europe/Ljubljana time, with no client `as_of` or identity selector. Rows contain only `first_name`, `last_name`, and a recognized status category; `unknown` is omitted. |
| `get_current_attendance` (legacy detailed mapping) | `GET /api/v1/attendance/current?as_of=&status=&status=&limit=&offset=` | Administrator only; retains the historical detailed response and arbitrary local `as_of`. |
| `get_employee_attendance_analysis` | `GET /api/v1/employees/{employee_id}/attendance-analysis?start_date=&end_date=` | Administrator only; inclusive range is at most 31 calendar days. |
| `get_employee_attendance_summary` | `GET /api/v1/employees/{employee_id}/attendance-summary?start_date=&end_date=` | Administrator only; inclusive range is at most 31 calendar days. |
| `get_exceptions` | `GET /api/v1/attendance/exceptions?start_date=&end_date=&employee_ids=&limit=&offset=` | Administrator only; bounded operational exception report. |
| `get_organization_attendance_analysis` | `GET /api/v1/attendance/organization-analysis?start_date=&end_date=&limit=&offset=` | Administrator only; inclusive range is at most 31 calendar days. |

`GET /health` is public liveness only and returns `200 {"status":"ok"}`. It
does not establish database, Entra, or audit readiness.

## Requester-scoped attendance extensions

`GET /api/v1/me/attendance-events/latest` has no employee selector. It returns
the requester-derived employee's most recent event, ordered by check-in time and
then event ID; an empty history returns the standard safe `NOT_FOUND` response.

`GET /api/v1/me/attendance-summary` accepts required inclusive `start_date` and
`end_date` parameters for no more than 366 calendar days. Its response contains
the requested period, `total_recorded_hours`, `attendance_day_count`, and
`monthly` and `locations` breakdowns. Only completed positive intervals are
counted, with intervals clipped to the requested local-calendar period. The
summary contains no employee selector or individual event list.

The pilot workforce view is `GET /api/v1/attendance/current-status`. It evaluates
active employees at one server-sampled instant on the current Europe/Ljubljana
day; it accepts zero or more repeated `status` filters from `office`, `remote`,
`customer_site`, `break`, `absence`, and `no_status`, applies their union before
pagination, and omits unknown states. Its page contains only `items` with
`first_name`, `last_name`, and `status`, plus `limit`, `offset`, and `next_offset`.
It rejects `as_of` and all other unsupported query keys with a safe
`INVALID_ARGUMENT` response. Individual attendance histories remain scoped to
the requester or administrator.

The pilot source slice changes the existing
`GET /api/v1/attendance/current` detailed route from delegated-user access to
administrator-only access. Its input, response, and administrator behavior
otherwise remain unchanged. MCP 1.3.0's existing `get_current_attendance`
mapping cannot serve ordinary employees under this contract. The MCP owner
must add `get_current_work_status` mapped to the new REST route, retain the
legacy mapping for administrators, publish the successor MCP contract and
migration expectation, and update Teams to use the new tool before pilot
traffic. This adds a tool but changes the legacy tool's effective authorization;
the MCP owner must version that compatibility change explicitly. Existing
non-administrator clients of the detailed route receive safe `FORBIDDEN`.

## Adapter boundary

Attendance CRMT exposes REST only. It has no `/mcp` compatibility endpoint and
no session-admission endpoint. An external adapter may map its public contract
to this inventory, but every protected REST request is independently validated
by CRMT and must forward the delegated bearer and correlation ID unchanged.
