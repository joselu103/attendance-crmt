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
