# Service Boundary and Invariants

Attendance CRMT owns Entra token validation, requester identity derivation,
employee mapping, authorization, audit records, attendance rules, and SQL Server
access. Clients must not choose an employee, role, location, or authorization
result.

For schema-dependent work, obtain and honor actual SQL Server DDL and constraints;
do not infer models or relationships. Employee identity is server-derived, so
requester-scoped calls must not accept an employee ID, email, role, or another
identity selector from clients.

Use Europe/Ljubljana naive time and inclusive explicit start/end dates for
attendance-event queries, with no maximum date span and future ends permitted.
Preserve date ordering, default 50/limit 1–100/nonnegative offset pagination,
timestamp/event-ID ordering, and database lookahead. Summary, reporting, and
planned-work date caps remain unchanged. Audit protected REST operations with a
server-derived requester and correlation ID, without logging sensitive values
or attendance records.

History pages retain rows with a check-in before the exclusive local end and
either an in-range check-in, an active null checkout, or a checkout after the
local start. This includes active pre-period rows and in-range anomalous rows;
only history items add nullable UTC-elapsed integer `duration_minutes`. The
history root summary separately reports non-null returned-item minutes and
unpaged completed-overlap minutes clipped to the requested period. These are
current-request values, count overlaps independently, and do not imply a
snapshot or change any other event representation.

Keep liveness separate from readiness: `GET /health` alone does not establish SQL,
Entra, or audit readiness.
