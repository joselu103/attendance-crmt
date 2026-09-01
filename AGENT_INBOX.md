# Directive: ACRMT-NONPROD-MCP-DEPLOY-001

## Main Objective
Advance the upstream Attendance CRMT security boundary from a source-only MCP 1.2.0 contract toward a verifiable non-production HTTPS deployment by producing the repository-owned, source-identifiable deployment artifact and an executable verification handoff, while leaving real Teams attendance traffic disabled until every declared identity, database, deployment, and audit prerequisite passes.

## Key Context From Other Repositories
- `attendance-crmt` is `blocked`; it declares the MCP 1.2.0 `list_my_attendance_events` contract and an active-email readiness command, but no verified non-production HTTPS `/mcp` deployment or Entra API registration exists. It also declares unresolved deployment, database-access, and production data-quality dependencies.
- `attendance-teams-bot` is `ready`; it declares authenticated MCP 1.2.0 discovery and requester-scoped `list_my_attendance_events` orchestration. It still requires the deployed non-production HTTPS `/mcp` endpoint, the Entra API registration exposing `attendance.access`, delegated OBO consent, production certificate configuration, operational/privacy approval, and end-to-end identity and data verification.
- `attendance-crmt-development-notices` is `blocked`; it declares public development notice URLs but still requires the deployed MCP endpoint, Entra registration, active-email readiness result, publication approvals, and end-to-end traffic-gating verification. Its reviewed local notice revisions are explicitly not declared published.
- No expected repository is known to be missing an `AGENT_STATE.json`; the root coordination protocol does not provide a separate authoritative repository inventory, so discovery is limited to the three state files present.

## Specific Steps
1. Inspect the local Attendance CRMT codebase, tests, deployment assets, and approved integration decisions to identify the exact repository-owned work still needed for a non-production MCP 1.2.0 deployment; do not infer that external Azure, Entra, SQL Server, hostname, certificate, or secret-manager resources already exist.
2. Build and verify a source-identifiable, immutable Attendance CRMT deployment artifact for the existing authenticated and auditable MCP 1.2.0 boundary. Record the source revision and artifact identity without committing credentials or environment-specific secrets.
3. Make the non-production deployment and verification procedure executable for an authorized platform owner: enumerate required runtime configuration and secret injection, persistent audit storage, SQL Server read-only connectivity, HTTPS `/mcp` exposure, and the Entra `attendance.access` audience/permission inputs. Preserve Attendance CRMT as the sole authorization, identity-to-employee mapping, business-rule, audit, and SQL boundary.
4. Exercise the repository's relevant tests, linting, type checks, artifact build, and local/container health checks. If authorized non-production resources and credentials are actually available, deploy and verify authenticated MCP discovery plus a requester-scoped `list_my_attendance_events` call and its audit correlation; otherwise stop before external changes and produce a precise owner handoff with the unresolved prerequisites.
5. Document the concrete client-facing deployment result: artifact identity, endpoint and contract version only if verified, authentication audience and required scope only if approved, verification evidence, rollback procedure, and explicit remaining activation gates. Do not enable real Teams attendance traffic or claim end-to-end readiness from local or mocked verification.

## Definition Of Done
- A source-identifiable Attendance CRMT deployment artifact is built and verified, with reproducible repository-owned build and health-check instructions.
- An authorized owner can execute the non-production HTTPS `/mcp` deployment and verification handoff without guessing required identity, secret, database, audit-storage, or rollback inputs.
- Relevant repository tests, linting, type checks, artifact build, and container/local verification pass, with actual command results recorded by the repository agent.
- If deployment prerequisites are available, the non-production endpoint is verified for authenticated MCP 1.2.0 discovery, requester-derived authorization, `list_my_attendance_events`, and audit correlation. If they are unavailable, no deployment or readiness is fabricated and each missing prerequisite remains an explicit blocker.
- The Teams bot remains an MCP-only client with no SQL access or attendance authorization policy, and real Teams attendance traffic remains disabled until Entra, OBO, certificate, database-readiness, privacy/operational approval, and end-to-end verification gates pass.
- Production deployment, production writes, notice publication, Teams-client activation, and bypassing external approvals are excluded from this slice.

## Required `AGENT_STATE.json` Update
- `status`: set to the actual result (`ready` only if the declared non-production boundary and required verification are genuinely complete; otherwise retain `blocked` or use the repository's supported in-progress status).
- `provided_exports`: declare only concrete verified outputs, including the immutable artifact identity and reproducible build contract; add the non-production HTTPS `/mcp` endpoint, MCP 1.2.0 deployment contract, approved authentication audience/scope, and verification evidence only if they were actually deployed and verified.
- `dependencies_needed`: retain every unresolved Entra, delegated OBO/certificate, platform authorization/hostname/resource, secret injection, persistent audit storage, SQL Server access, data-quality, or approval prerequisite with precise ownership.
- `open_issues_or_blockers`: list every remaining integration and activation blocker; clear an item only when backed by real deployment or verification evidence, and keep real Teams attendance traffic disabled while any required gate remains unresolved.

## [COMPLETED] ACRMT-NONPROD-MCP-DEPLOY-001

Repository-owned delivery is complete: the source-revision-labeled local OCI artifact,
container liveness/authentication probe, safe deployment/audit verification handoff,
and repository quality gates are recorded in `AGENT_STATE.json` and the non-production
readiness status. External HTTPS deployment, Entra/OBO approval, published registry
digest, SQL Server readiness, persistent audit storage, and Teams activation remain
explicitly blocked; no external resource or real Teams attendance traffic was enabled.
