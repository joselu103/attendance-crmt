# Directive: CRMT-DEPLOY-001

## Main Objective
Resolve the CRMT-owned operational prerequisites for real non-production Teams integration: obtain a deployed non-production HTTPS `/mcp` endpoint implementing contract 1.2.0 and complete the authoritative production active-email uniqueness readiness check, with evidence recorded as integration status rather than inferred readiness.

## Key Context From Other Repositories

- `attendance-teams-bot` is `ready` and supports a requester-scoped personal-chat read-only flow against CRMT contract 1.2.0. It is blocked until CRMT provides a deployed non-production HTTPS `/mcp` endpoint, a Microsoft Entra API registration exposing `attendance.access`, and approved OBO consent/certificate configuration.
- `attendance-crmt-development-notices` is `blocked` but has public development privacy/terms/inventory exports. It depends on the same deployed CRMT endpoint, Entra API registration, and production active-email uniqueness readiness check; notice publication also has separate organizational approval blockers.
- CRMT currently publishes contract 1.2.0 but declares the non-production endpoint, concrete Entra configuration, and production active-email uniqueness check as unresolved dependencies. Do not treat contract readiness as deployment readiness.

## Specific Steps

1. Inspect the local CRMT deployment/configuration and approved operational process to identify the authorized owner and exact inputs required for a non-production HTTPS `/mcp` deployment and Entra API registration.
2. Produce an executable, environment-specific integration handoff for the platform/Entra owner: required endpoint hostname, transport, `attendance.access` scope, audience/claims configuration, certificate/secret handling expectations, and a non-sensitive verification procedure. Do not place credentials or tenant-specific secrets in source control or public documentation.
3. Where authorization and access are available, deploy or configure the non-production CRMT `/mcp` endpoint for contract 1.2.0 and verify it is reachable only through the intended HTTPS and authentication boundary. If external authorization is absent, record the precise owner/input needed instead of simulating deployment success.
4. Run the authoritative read-only active-email uniqueness readiness check against the production SQL Server schema using the approved access path. Capture only aggregate/non-sensitive evidence and remediate or escalate any duplicate active-email findings before marking the check complete.
5. Verify that the deployed integration remains read-only, derives employee identity server-side from validated Entra tokens, and retains authorization/audit behavior. Run applicable repository checks and publish a safe client-facing integration readiness summary.

## Definition Of Done

- A non-production HTTPS `/mcp` integration target implementing CRMT contract 1.2.0 is either verified with recorded non-sensitive evidence or blocked with the exact missing authorization/owner/configuration input.
- The Entra API registration requirements for `attendance.access` are concretely handed off or verified; no secrets are committed or exposed.
- The production active-email uniqueness readiness check is completed against the authoritative SQL Server database with an evidence-backed pass/fail result, or is explicitly blocked by the required approved access.
- Any actual integration verification preserves CRMT as the token-validation, employee-mapping, authorization, and audit boundary.
- No production rollout, attendance write capability, or unapproved infrastructure change is claimed or performed solely from this directive.

## Required `AGENT_STATE.json` Update

After completion, update `AGENT_STATE.json` with:

- `status`: the actual resulting status; keep or change to `blocked` when any deployment, Entra, authorization, or readiness prerequisite remains unresolved;
- `provided_exports.interfaces_or_endpoints`: the verified non-production HTTPS `/mcp` target and contract version only when actually deployed and safely publishable;
- `dependencies_needed`: precise remaining external Entra, platform, certificate, or approved-access inputs;
- `open_issues_or_blockers`: the current evidence-backed blockers, including failed or unrun active-email uniqueness checks and any unverified deployment condition.

## [COMPLETED] CRMT-DEPLOY-001

The repository-safe readiness command, secret-free deployment handoff, and
blocker status are verified. Real non-production deployment, Entra API
registration, approved production uniqueness check, and Teams OBO acceptance
remain explicitly blocked in `AGENT_STATE.json`.
