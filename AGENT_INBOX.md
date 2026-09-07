# Directive: CRMT-REST-CORE-001

> **Status:** Active directive. This is the first reversible REST-migration
> slice. The former `CRMT-NONPROD-MCP-DEPLOY-001` directive below is historical
> and must not be executed as the target architecture.

## Main Objective

Add a minimal FastAPI REST application factory and public liveness route beside
the existing FastMCP runtime, creating the composition seam for the REST core
without changing authorization, tools, audit, SQL behavior, or deployment.

## Required Context

- Read root `docs/architecture/0001-rest-core-mcp-adapter.md`,
  `docs/contracts/attendance-rest-v1.md`, and `docs/next-action.md`.
- The established SQL Server schema, authentication, identity mapping,
  authorization, audit persistence, and attendance behavior remain authoritative
  in this repository; this slice moves none of them.
- Preserve the current branch history and existing embedded FastMCP runtime as
  the rollback bridge. Do not reset, squash, or absorb unrelated work.

## Specific Steps

1. Inspect the current worktree, recent commits, and relevant server/dependency
   composition before editing.
2. Write a failing black-box integration test for `GET /health` returning `200`
   and `{"status":"ok"}` without using database, Entra, or audit dependencies.
3. Add FastAPI as a direct dependency only if absent, then implement the smallest
   injectable `create_app(...) -> FastAPI` composition factory that makes the
   test pass.
4. Keep existing FastMCP tool registration, authentication, audit middleware,
   container entrypoint, and `/mcp` behavior unchanged.
5. Run the focused test, then the full pytest/Ruff/format gates using the local
   Python 3.14 virtual environment without injected Hermes paths.

## Definition Of Done

- A tested REST application factory exposes public liveness only.
- Liveness does not initialize or access SQL Server, Entra metadata/JWKS, or the
  audit store.
- Existing FastMCP tests and behavior remain green as the rollback bridge.
- No external resources, secrets, deployment configuration, git commits, or
  production state are changed.

## Required `AGENT_STATE.json` Update

- Keep `status` as `blocked`; this local slice does not resolve external
  deployment/Entra/SQL/audit prerequisites.
- Add only evidence-backed REST-shell exports after verification.
- Retain all unresolved activation and production-readiness blockers.

---

# Historical Directive: CRMT-NONPROD-MCP-DEPLOY-001

> **Status:** Superseded by `CRMT-REST-CORE-001` and ADR 0001. Retained only as
> historical evidence of external activation gates; do not deploy the embedded
> FastMCP runtime as the target architecture.

## Main Objective
Establish and verify a source-identifiable, authenticated non-production HTTPS `/mcp` deployment of Attendance CRMT contract 1.2.0 so downstream Teams integration can begin controlled end-to-end verification without enabling production traffic.

## Key Context From Other Repositories
- `attendance-teams-bot` is `ready` and declares one-shot authenticated MCP 1.2.0 discovery, bot-approved `list_my_attendance_events` orchestration, and an authenticated Teams personal-chat requester flow. It still requires a deployed non-production HTTPS `/mcp` endpoint implementing contract 1.2.0, an Attendance CRMT Entra API registration exposing `attendance.access`, delegated OBO consent, and production certificate configuration.
- `attendance-crmt-development-notices` is `blocked` and declares public development notice URLs. It also depends on the deployed non-production MCP endpoint and Entra API registration, while publication and organizational approvals remain separate unresolved prerequisites.
- No additional expected repository list is declared by the master coordination protocol; therefore no missing `AGENT_STATE.json` can be identified beyond the three discovered repository states.

## Specific Steps
1. Inspect this repository's local implementation, deployment documentation, and approved infrastructure decisions; preserve the existing MCP contract 1.2.0 and established production SQL Server boundary.
2. Coordinate only with an authorized platform/identity owner to obtain the approved non-production Container App resource boundary, HTTPS hostname, runtime secret injection, persistent audit storage, SQL Server read-only access, and Attendance CRMT Entra API registration exposing `attendance.access`. Do not create, mutate, or claim external resources without explicit authorization and verifiable access.
3. Add or complete the repository-owned CI path that publishes the reviewed source revision as an immutable, source-identifiable container image. Record the registry-qualified digest and verify its revision label against the exact source revision; do not treat the existing local-only digest as deployable registry evidence.
4. Deploy that immutable digest to the approved non-production environment with certificate-based runtime credentials and persistent audit storage. Keep production traffic disabled and do not grant the Teams bot broader permissions than the versioned delegated OBO contract requires.
5. Verify public liveness separately from readiness, then run the repository's safe deployment and audit verification paths against the non-production HTTPS `/mcp` endpoint. Demonstrate authenticated MCP discovery and a requester-scoped `list_my_attendance_events` call with authorization, identity derivation, and audit correlation enforced by Attendance CRMT.
6. Document concrete client-facing evidence: environment URL naming, MCP contract version, token audience/scope, required verified claims, OBO/certificate expectations, immutable image digest, verification commands, results, and any remaining activation gates. Never record tokens, certificates, connection strings, or personal attendance data.
7. Run the repository's relevant tests, lint, formatting, and type checks. If any external prerequisite is unavailable, do not fabricate completion: record the precise owner/action needed and leave the state blocked.

## Definition Of Done
- A registry-qualified immutable image digest is tied to the exact reviewed source revision, and the approved non-production deployment runs that digest.
- The non-production HTTPS `/mcp` endpoint implements contract 1.2.0 and validates Entra tokens for the approved `attendance.access` audience/scope; Attendance CRMT remains the authorization, employee-mapping, audit, and SQL Server boundary.
- Liveness, safe deployment verification, authenticated requester-scoped attendance access, and persistent audit correlation have verifiable results, with repository quality gates passing.
- The client-facing integration evidence is documented without secrets or personal data and is sufficient for `attendance-teams-bot` to perform a separately authorized end-to-end test.
- Production traffic, production rollout, Teams-bot activation, notice publication, write/update attendance tools, and organizational/legal approvals remain explicitly excluded from this task.
- If authorization or infrastructure prerequisites prevent deployment, the completed local/CI work and exact unresolved blocker ownership are documented; the task must not be reported as deployed or ready.

## Required `AGENT_STATE.json` Update
- `status`: set to `ready` only if the immutable non-production deployment and authenticated/audited verification are complete; otherwise keep `blocked` and state the actual partial result.
- `provided_exports`: replace local-only or aspirational claims with concrete versioned evidence, including MCP contract 1.2.0, the verified non-production HTTPS endpoint contract, Entra audience/scope contract, registry-qualified immutable image digest, source revision, and safe verification interfaces that actually exist.
- `dependencies_needed`: retain only precise unresolved prerequisites, naming the external owner or approval category where known; do not remove production active-email readiness or production activation prerequisites merely because non-production verification succeeds.
- `open_issues_or_blockers`: enumerate every remaining deployment, Entra/OBO/certificate, SQL Server, audit-storage, production data-quality, downstream end-to-end, privacy, or authorization blocker; use an empty list only when none actually remain.
