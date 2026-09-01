# Attendance CRMT Non-Production Integration Readiness Status

**Checked:** 2026-09-01

**Overall status:** **Blocked** — repository-owned deployment artifact and local acceptance checks are verified, but no non-production HTTPS `/mcp` deployment, CRMT Entra API registration, approved SQL Server runtime access, or real requester/audit acceptance evidence exists.

## Verified repository-local evidence

| Check | Result |
| --- | --- |
| Source revision | `33f0a3c9d5b719aa84a831bb6402800302359fa3` (`Add Deployment Verification Handoff`) |
| Local image identity | `attendance-crmt@sha256:0f994f5344989ea96fa5ba2dae4fe20066601b0dc24505ee31820a31668e7a0b` |
| OCI source label | `org.opencontainers.image.revision=33f0a3c9d5b719aa84a831bb6402800302359fa3`, inspected after the local build |
| Tests | `130 passed` via `env -u PYTHONPATH -u VIRTUAL_ENV uv run --all-groups python -m pytest -q` |
| Lint and format | `ruff check .` passed; `ruff format --check .` reported `61 files already formatted` |
| Compose validation | `docker compose config --quiet` passed |
| Container liveness | A production-configured local container returned `GET /health` → `200 {"status":"ok"}` |
| Public MCP boundary | The same local container returned unauthenticated `POST /mcp` → `401` with safe `AUTHENTICATION_REQUIRED` |
| Verifier contracts | The deployment/audit verifier tests cover strict contract-version rejection, requester-scoped official-MCP-client calls, safe evidence serialization, and read-only audit lookup. |

The image digest is local-only evidence, not a published registry digest. GitHub Actions has not run for this source revision, and no GHCR pull/push identity has been verified. A local build/test result is not proof of an external deployment.

## Read-only Azure and Entra discovery

No authorized Azure/Entra discovery or mutation was performed for this delivery. The following prerequisites remain unverified:

| Required prerequisite | Result |
| --- | --- |
| Separate Attendance CRMT Container App with a public HTTPS `/mcp` endpoint | Not deployed / unverified |
| Attendance CRMT Entra API app registration exposing delegated `attendance.access` | Not verified |
| Teams bot delegated permission, OBO consent, and certificate configuration | Not verified |
| Approved non-production SQL Server read-only runtime access | Not available to this repository task |
| Persistent production audit volume and backup owner | Not verified |

No cloud resource, Entra application, deployment, public ingress, production database connection, credential, or Teams attendance flow was created or changed.

## Active-email production readiness gate

**Status:** **Blocked — not run against the authoritative production SQL Server database.**

`attendance-crmt-check-active-emails` remains an aggregate-only, read-only readiness command. It must be run with a database-owner-approved production read-only connection. No connection string, email, employee ID, duplicate-row detail, or production query result has been read or recorded here.

## Required owner handoff

1. **Repository owner:** push the reviewed source through CI and capture the GHCR immutable digest emitted by the container job; do not deploy `latest` alone.
2. **Platform owner:** approve the Container App resource boundary, HTTPS hostname/DNS, secret injection, persistent `/app/data` audit mount, backup/retention owner, and rollback path.
3. **Entra administrator:** create or verify the single-tenant CRMT API resource exposing `attendance.access`, then grant the bot delegated permission and required OBO consent.
4. **Database owner:** provide approved non-production SQL Server read-only runtime access and authorize the production aggregate active-email uniqueness check and remediation escalation.
5. **Teams bot/Entra owner:** provide the approved certificate configuration and conduct the mapped non-admin end-to-end test.

After the platform owner deploys the CI-produced digest, run `attendance-crmt-verify-deployment` against the approved HTTPS `/mcp` endpoint with the short-lived token injected outside the command. Use its emitted correlation UUID with `attendance-crmt-verify-audit` only against the authorized persistent audit volume. Record only the safe evidence; do not log tokens, claims, attendance events, employee identities, or audit request bodies.

## Activation rule

Real Teams attendance traffic remains disabled until all of the following are verified: deployed HTTPS `/mcp`, CRMT Entra API registration and approved delegated/OBO/certificate configuration, approved runtime secrets and SQL Server access, persistent audit storage, active-email readiness pass, and requester-scoped end-to-end MCP/audit acceptance. The Teams bot must remain an MCP-only client; Attendance CRMT remains the authorization, identity-mapping, business-rule, audit, and SQL boundary.
