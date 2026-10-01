# Service Boundary and Invariants

Attendance CRMT owns Entra token validation, requester identity derivation,
employee mapping, authorization, audit records, attendance rules, and SQL Server
access. Clients must not choose an employee, role, location, or authorization
result.

For schema-dependent work, obtain and honor actual SQL Server DDL and constraints;
do not infer models or relationships. Employee identity is server-derived, so
requester-scoped calls must not accept an employee ID, email, role, or another
identity selector from clients.

Use Europe/Ljubljana naive time and enforce the inclusive 31-calendar-day limit
for attendance-event queries. Audit protected REST operations with a
server-derived requester and correlation ID, without logging sensitive values
or attendance records.

Keep liveness separate from readiness: `GET /health` alone does not establish SQL,
Entra, or audit readiness.
