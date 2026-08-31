# Directive: CRMT-MCP-001

## Main Objective
Publish the first versioned, requester-scoped **read-only attendance** integration contract from Attendance CRMT. This contract is the prerequisite for the Teams bot's first end-to-end slice.

## Key Context From Other Repositories

- `attendance-teams-bot` is `idle`; it currently publishes no interfaces/events and declares no dependencies or blockers. It cannot safely integrate until CRMT declares the MCP transport, authentication, requester-identity, authorization, audit, and response/error contracts.
- `attendance-crmt-development-notices` has no `AGENT_STATE.json` at the master-discovery point, so its status, exports, and dependencies are unknown. Do not make this CRMT task depend on it.

## Specific Steps

1. Inspect the local CRMT codebase and existing approved product decisions to identify the narrowest viable requester-scoped read-only attendance capability.
2. Define and implement a versioned MCP contract for that capability, including:
   - MCP endpoint/transport and environment configuration surface;
   - a requester-scoped tool name, input schema, and bounded date-range rules;
   - immutable response schema and stable user-safe error categories;
   - cryptographically verifiable Entra token validation requirements, expected audience/claims, and server-derived employee mapping;
   - server-side authorization and audit behavior.
3. Keep the SQL Server schema and all attendance business rules inside CRMT. The client must not supply an authoritative employee ID or choose authorization/location/business-rule outcomes.
4. Add focused tests for the contract, identity/authentication rejection paths, authorization/audit boundary, and response/error behavior. Run the repository's relevant test, lint, format, and type checks.
5. Update local documentation needed for a client to implement against the contract without access to CRMT internals.

## Definition Of Done

- A client can discover a documented, versioned, requester-scoped read-only MCP contract and its transport/authentication requirements.
- The server derives requester identity and employee mapping from a validated token, performs authorization and auditing, and never trusts a client/LLM employee identifier.
- Contract and security-boundary tests pass along with the repository's required quality checks.
- No write/update attendance capability is added in this slice.

## Required `AGENT_STATE.json` Update

After completion, update `AGENT_STATE.json` with:

- `status`: the repository's actual resulting status (for example, `ready` only when the documented contract and verification are complete);
- `provided_exports.interfaces_or_endpoints`: the concrete MCP endpoint/transport and requester-scoped tool contract, including version where applicable;
- `dependencies_needed`: any unresolved external deployment/Entra configuration prerequisites, named precisely;
- `open_issues_or_blockers`: every remaining blocker to a real Teams-bot integration, or an empty list only if none remain.

[COMPLETED] CRMT-MCP-001
