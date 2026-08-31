# Attendance CRMT Non-Production Integration Readiness Status

**Checked:** 2026-08-31

**Overall status:** **Blocked** — Attendance CRMT contract 1.2.0 source is
verified locally, but the required non-production HTTPS deployment, CRMT Entra
API registration, and authoritative production active-email uniqueness result
are not yet evidenced.

## Verified local evidence

| Check | Result |
| --- | --- |
| Contract implementation | MCP Streamable HTTP `/mcp`, contract `1.2.0`, authenticated production composition, requester-derived identity, read-only attendance tools, and audit middleware are present in the reviewed source. |
| Lint | `ruff check .` passed during readiness planning. |
| Format | `ruff format --check .` passed during readiness planning. |
| Tests | `118 passed` after the readiness command and documentation changes. |
| Container build | The local Docker image built successfully during readiness planning. |
| Source publication | Not verified. The local branch was six commits ahead of `origin/main` when checked, so CI cannot yet have published this exact source revision. |

A local test/build result is not proof of an external deployment.

## Read-only Azure and Entra discovery

Read-only discovery found the existing development Teams bot resources and its
Entra application. It did not find either of the following CRMT prerequisites:

| Required prerequisite | Result |
| --- | --- |
| Separate Attendance CRMT Container App with a public HTTPS `/mcp` endpoint | Not found / unverified. |
| Attendance CRMT Entra API app registration exposing delegated `attendance.access` | Not found / unverified. |

The actual endpoint hostname, resource owner, SQL target, runtime secret store,
audit-volume design, and bot OBO certificate/consent evidence have not been
provided to this repository. No cloud resource, Entra application, deployment,
or public ingress was created or changed by this readiness work.

## Active-email production readiness gate

**Status:** **Blocked — not run against production.**

The repository now provides the read-only aggregate command
`attendance-crmt-check-active-emails`. It must be run only with a
database-owner-approved production read-only connection. Its result must be
recorded as aggregate counts only. No production connection string, email,
employee identifier, or duplicate row detail has been read or recorded here.

Until it exits `0` with `ready: true`, production rollout remains blocked.

## Remaining required inputs and owners

1. **Platform owner:** approve the CRMT Azure resource boundary, runtime secret
   injection, persistent audit mount/backup ownership, and HTTPS hostname/DNS.
2. **Entra administrator:** create or verify the single-tenant CRMT API resource
   with `attendance.access`, grant the bot delegated permission, and complete
   required consent.
3. **Repository owner:** authorize publication of the reviewed source/image and
   capture the source-identifiable image digest.
4. **Database owner:** provide approved non-production runtime access and approve
   the production read-only aggregate identity check plus duplicate-remediation
   escalation.
5. **Teams bot/Entra owner:** provide approved OBO consent and production
   certificate configuration, then perform the mapped non-admin end-to-end test.

## Activation rule

Real Teams attendance traffic remains disabled until all of the following are
verified: the CRMT API registration, deployed HTTPS `/mcp` endpoint, production
active-email uniqueness pass, bot OBO/certificate/consent configuration, and
requester-scoped end-to-end MCP/audit acceptance. The bot must continue to use
only CRMT as the authorization, identity-mapping, audit, and SQL boundary.
