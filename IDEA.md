# Project Vision: Legacy Attendance System MCP Integration

## Context & Goal
We are updating an existing employee attendance system. 
- **Current State:** A legacy .NET monolith web application without a public REST API. Handles check-ins/outs (home, office, custom locations), vacation/sick leave requests, and role-based actions (CEOs/Managers registering hours or viewing team status).
- **Target State:** A Python-based MCP (Model Context Protocol) server using `FastMCP`. This will serve as the backend layer for a future Microsoft Teams Bot, allowing users to interact with the attendance system via conversation.
- **Integration Strategy:** Since there is no API, we will reverse-engineer the underlying database and business logic to execute actions directly against the DB.

---

## Working Methodology (Step-by-Step Discovery)
We do NOT have the exact database schema, business rules, or tool signatures finalized yet. The workflow must be strictly iterative:

1. **Discovery & Exploration:** Analyze legacy behavior, DB tables, and constraints together.
2. **Definition:** Define tool signatures and contracts only after understanding the DB constraints.
3. **Incremental Implementation:** Build and test read-only capabilities first, followed by write operations.

---

## High-Level Capabilities (To Be Defined)
The MCP server will eventually need to cover:
- **Presence & Status:** Checking in/out and viewing current working locations.
- **Leave Management:** Requesting and viewing sick leave / vacation balances.
- **Role-Based Management:** Manager/CEO level actions (viewing team activity, registering hours for others).

---

## Key Technical Concerns to Keep in Mind
- **Data Integrity:** Bypassing the .NET app logic means we must strictly replicate audit trails, foreign keys, and DB constraints.
- **Security & RBAC:** Ensure role-based access rules are enforced by the MCP server before executing queries.

---

## Tool Architecture Goal

Expose a small, domain-oriented MCP API rather than raw database-table CRUD.
Tools should operate on employees, attendance events, current status, planned work, and
attendance reporting; clients must not need to know legacy table names or foreign keys.

### Tool Groups

1. **Catalog and employee discovery (read-only)**
   - List and retrieve employees.
   - List active punch types and reference locations.
2. **Attendance queries (read-only)**
   - List and retrieve attendance events in a bounded date range.
   - Retrieve a daily employee view and the live attendance-status grouping.
3. **Attendance mutations**
   - Record an attendance event.
   - Correct an existing event with a mandatory correction reason.
   - Delete or reverse an event only after the legacy application's supported behavior is confirmed.
4. **Bulk operations**
   - Preview a proposed workday registration before changing data.
   - Apply only the exact reviewed request through a short-lived confirmation token.
5. **Reporting**
   - Retrieve planned work, planned-versus-actual summaries, and attendance exceptions.

### Non-Negotiable Contracts

- Never expose generic raw-SQL or table-level CRUD tools.
- Attendance-event creation and correction accept a punch type, not a location. The
  server derives and persists the location from the approved punch-type-to-location
  mapping so these fields cannot diverge.
- Keep caller identity, audit fields, timestamps, and edit markers server-owned.
- Enforce RBAC in the service layer: employees may act on their own data; elevated
  roles are required for team views, corrections, and bulk operations.
- Bound all list and report queries with date ranges and pagination.
- Use structured JSON outputs, explicit timezone semantics, transactions for writes,
  idempotent duplicate handling for bulk requests, and mutation audit records.
- During discovery, run with a read-only database connection. Enable write tools only
  after their database behavior, legacy rules, authorization, and tests are confirmed.

### Delivery Sequence

1. Employee/punch-type discovery, event history, and live-status reads.
2. Single-event registration with server-side location derivation.
3. Event correction and audit semantics.
4. Planned-versus-actual reporting and exception detection.
5. Preview/apply bulk workday registration.
