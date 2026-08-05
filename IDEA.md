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
