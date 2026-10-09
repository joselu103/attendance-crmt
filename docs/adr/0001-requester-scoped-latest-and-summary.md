# ADR 0001: Requester-Scoped Latest Event and Long-Range Summary

## Status

Accepted.

## Context

Personal attendance chat needs a concise latest-entry answer and an aggregate
personal reporting period. When this ADR was accepted, event history was capped
at 31 calendar days; ATTENDANCE-HISTORY-PAGINATION-001 removes that history cap.
The summary retains its independent 366-calendar-day cap.
The service must preserve CRMT as the only authority for identity derivation,
authorization, audit, attendance rules, and database access.

Current Presence is a separate delegated-user directory/status capability. It
can identify active employees returned by the established current-attendance
view, but it must not become a path to an individual's attendance history.

## Decision

Add two protected requester-scoped REST operations:

- `GET /api/v1/me/attendance-events/latest` returns the requester-derived
  employee's latest event or safe `NOT_FOUND`.
- `GET /api/v1/me/attendance-summary?start_date=&end_date=` accepts an
  inclusive period of at most 366 calendar days and returns total recorded time,
  attendance-day count, and monthly and location breakdowns.

Neither operation accepts an employee ID or any other identity selector. Both
use the existing delegated bearer, correlation, safe-error, and audit boundary.
The summary counts completed positive intervals, clipped to the requested
Europe/Ljubljana calendar period; empty periods return a zero aggregate.

Current Presence remains available to authenticated users under its existing
policy. Individual Attendance Details remain limited to requester-scoped `me`
operations and administrator-authorized employee/event operations.

## Consequences

Teams and the future MCP adapter can expose personal latest-entry and long-range
summary intent without reproducing identity or authorization policy. The
standalone MCP adapter must add only thin read-only mappings after its approved
repository exists; it must preserve bearer/correlation forwarding and safe
errors. Bot wording and glossary updates remain owned by the Teams bot
repository.
