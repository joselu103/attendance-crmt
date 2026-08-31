# Attendance CRMT Non-Production Deployment Readiness

**Status:** Operational handoff; deployment is blocked until the named owners approve
and supply the required environment inputs.

This document operationalizes the accepted
[Teams bot MCP authentication contract](teams-bot-mcp-auth-contract.md) for an
Attendance CRMT contract **1.2.0** non-production deployment. It does not claim
that an endpoint is deployed or that Teams attendance traffic is enabled.

## Boundary and scope

Attendance CRMT remains the authoritative boundary for:

- Entra access-token validation;
- requester-to-employee mapping;
- authorization and read-only tool enforcement;
- the established SQL Server attendance schema; and
- durable MCP audit records.

The Teams bot performs Teams SSO and OBO, then calls the remote `/mcp` endpoint
with token B. It must not access SQL Server, select an employee identity, or
make CRMT authorization decisions.

This handoff covers one non-production, external-HTTPS, **read-only** Container
App deployment. It does not authorize production rollout, attendance writes,
new SQL Server schema, direct bot-to-database access, or an unauthenticated
endpoint.

## Verified starting state

Read-only Azure and Entra inspection on 2026-08-31 found the development Teams
bot Container App, Container Apps environment, Azure Container Registry, and
Azure Bot registration. It did **not** find a separate Attendance CRMT Container
App or an Attendance CRMT API app registration exposing `attendance.access`.

The repository has a Docker image and GitHub Actions publishes it on a push to
`main`. The current source branch is ahead of its tracked remote, so a local
image build is not a published deployment artifact.

## Required owner decisions

Do not provision before these decisions are recorded by the responsible owner.

| Decision | Required owner | Required outcome |
| --- | --- | --- |
| Azure tenancy/resource ownership | Platform owner | Approve reuse or creation of the resource group, Container Apps environment, and registry. |
| DNS and ingress | Platform/network owner | Provide the non-production hostname and TLS/DNS ownership. |
| SQL target and network access | Database owner | Provide a non-production read-only SQL Server target and an approved runtime network path. |
| Runtime secret storage | Platform/security owner | Provide secret-store ownership for `ATTENDANCE_DATABASE_URL`; no secret is stored in Git. |
| Audit persistence | Platform/data owner | Approve a persistent `/app/data` mount, retention/backup policy, and one-replica constraint. |
| Entra API and consent | Entra administrator | Create/approve the CRMT API registration and bot delegated permission/admin consent. |
| Image publication | Repository owner | Approve a push of the reviewed commit and identify its image digest. |
| Production data-quality gate | Database owner | Approve the read-only production aggregate email check and the duplicate-remediation escalation path. |
| Bot OBO credentials | Teams bot/Entra owner | Configure the bot certificate and OBO consent without exposing credential material to this repository. |

Absent approval is a deployment blocker, not permission to choose a resource or
infer a secret value.

## Required Entra API resource

Create or verify a distinct single-tenant **Attendance CRMT MCP API** application.
The Teams Developer Portal app identifier and the Teams bot application are not
substitutes for this resource API.

| Property | Required value |
| --- | --- |
| Application ID URI | `api://<attendance-crmt-api-client-id>` |
| Delegated scope | `attendance.access` |
| Optional app role | `attendance.admin` (not required for the requester-only proof) |
| Accepted tenant | The one approved Attendance CRMT development tenant |
| Approved client | The exact Attendance Teams Bot confidential client application ID |
| Token type | Delegated OBO token B only; never an app-only token |
| Audience | The CRMT API URI or client ID configured in `ATTENDANCE_ENTRA_AUDIENCE` |

The Entra administrator must grant the Teams bot delegated permission to
`attendance.access` and perform required tenant consent. The bot's production
certificate remains only in its approved secret store. Do not place certificate
contents, client secrets, tenant secrets, access tokens, or application
connection strings in this repository, logs, or evidence documents.

## Container App runtime contract

The existing image command is:

```text
uvicorn attendance_crmt.server:create_production_http_app --factory --host 0.0.0.0 --port 8000
```

Configure a separate CRMT Container App with the following minimum properties:

| Property | Required setting |
| --- | --- |
| Image | Reviewed SHA-tagged image and captured immutable digest; never `latest` alone |
| Ingress | External HTTPS only, targeting port `8000` |
| Application environment | `ENVIRONMENT=production` |
| Replicas | One replica maximum while audit storage uses SQLite |
| Audit path | Persistent `/app/data` mount; configure `ATTENDANCE_AUDIT_DATABASE_PATH=/app/data/audit.sqlite3` |
| Database URL | Secret reference for `ATTENDANCE_DATABASE_URL` |
| Secret handling | Container App secret or approved Key Vault reference, never ordinary tracked configuration |
| Public contract | `<approved-https-host>/mcp`; port 8000 is an internal target, not a public API |

The implementation intentionally fails startup validation when `ENVIRONMENT=production`
and the MCP base URL, issuer, or OpenID metadata URL are not HTTPS. Keep the
following non-secret values aligned with the actual Entra API resource:

```text
ATTENDANCE_MCP_BASE_URL=https://<approved-https-host>
ATTENDANCE_ENTRA_TENANT_ID=<approved-tenant-uuid>
ATTENDANCE_ENTRA_ISSUER=https://login.microsoftonline.com/<approved-tenant-uuid>/v2.0
ATTENDANCE_ENTRA_OPENID_CONFIGURATION_URL=https://login.microsoftonline.com/<approved-tenant-uuid>/v2.0/.well-known/openid-configuration
ATTENDANCE_ENTRA_AUDIENCE=api://<attendance-crmt-api-client-id>
ATTENDANCE_ENTRA_ALLOWED_CLIENT_IDS=["<approved-teams-bot-client-id>"]
ATTENDANCE_ENTRA_REQUIRED_SCOPE=attendance.access
ATTENDANCE_ENTRA_CLOCK_SKEW_SECONDS=60
ATTENDANCE_ENTRA_ADMIN_ROLE=attendance.admin
```

The app currently has no dedicated health route. Do not configure a liveness
probe against the authenticated MCP endpoint without an explicit health-route
slice, behavior-level test, and separate review.

## Safe deployment sequence

1. Confirm every owner decision above and establish an approved spend/retention
   boundary before creating or reusing cloud resources.
2. Push the reviewed commit through the normal CI path. Capture the registry
   image digest and short source revision without publishing credentials.
3. Create or verify the Entra CRMT API registration and the bot's
   `attendance.access` delegated permission/consent.
4. Create the CRMT Container App sealed from public ingress first. Use a managed
   identity for private registry pull access; keep the registry admin user
   disabled.
5. Add runtime secrets through the approved platform secret store and non-secret
   configuration through the revision environment. Confirm the app starts with
   production validation enabled.
6. Add persistent audit storage and confirm its retention/backup owner.
7. Enable public HTTPS ingress only after the sealed revision is healthy.
8. Record only non-sensitive deployment evidence in
   `nonproduction-readiness-status.md`.
9. Leave real Teams attendance traffic disabled until the endpoint, Entra/OBO,
   production identity gate, and end-to-end requester acceptance all pass.

## Safe verification procedure

Use narrow Azure queries that do not print secret values:

```bash
az ad app show --id <crmt-api-app-id> \
  --query '{identifierUris:identifierUris,scopes:api.oauth2PermissionScopes[].value}' \
  --output json

az containerapp show --name <approved-crmt-app> --resource-group <approved-rg> \
  --query '{fqdn:properties.configuration.ingress.fqdn,external:properties.configuration.ingress.external,runningStatus:properties.runningStatus,image:properties.template.containers[0].image}' \
  --output json
```

The first harmless public protocol probe omits credentials:

```bash
curl --silent --show-error --dump-header /tmp/crmt-headers \
  --output /tmp/crmt-body \
  --request POST 'https://<approved-https-host>/mcp' \
  --header 'Content-Type: application/json' \
  --data '{}'
```

Expected outcome: HTTPS transport, HTTP `401`, safe
`AUTHENTICATION_REQUIRED` response, and
`X-Attendance-MCP-Contract-Version: 1.2.0`. Inspect only the expected headers
and safe body, then remove the temporary files. Never send a bearer token in a
shell command or retain it in shell history.

The approved Teams bot/OBO test must then prove initialization, compatible
contract major version, an employee-scoped `list_my_attendance_events` call,
server-derived identity, and a correlated audit outcome. The client supplies no
employee ID, email, role, or other authority selector.

## Production active-email readiness gate

The runtime checker is installed as:

```bash
env -u PYTHONPATH .venv/bin/attendance-crmt-check-active-emails
```

Run it only with a database-owner-approved **read-only production**
`ATTENDANCE_DATABASE_URL` injected outside the shell command. It emits aggregate
JSON only:

```json
{
  "active_employee_count": 0,
  "active_with_usable_email_count": 0,
  "duplicate_normalized_email_count": 0,
  "duplicate_active_employee_count": 0,
  "ready": true
}
```

Exit codes:

| Code | Meaning |
| --- | --- |
| `0` | No duplicate normalized active email group was found. |
| `1` | Configuration/database check unavailable; safe error text only. |
| `2` | Duplicate normalized active email group exists; rollout remains blocked. |

The grouping matches the server's interim identity policy:
`LOWER(LTRIM(RTRIM(dbo.izvajalci.email)))` for rows where `active = 1` and email
is nonblank. The command does not output employee IDs, email values, connection
URLs, or SQL error details. An authorized employee-data administrator owns any
row-level investigation and remediation; rerun the aggregate check afterward.

## Rollback and incident boundary

If a deployment or acceptance check fails:

1. Keep real Teams attendance traffic disabled.
2. Disable public ingress or deactivate the failing revision through the
   approved platform owner; do not delete audit storage as a rollback shortcut.
3. Retain the source revision, image digest, aggregate results, and safe failure
   code needed for investigation.
4. If Entra consent was granted incorrectly, the Entra owner revokes the bot's
   delegated permission; do not weaken audience/client/scope validation.
5. Do not perform production database mutation, schema changes, credential
   rotation, or resource deletion without separate owner authorization.

## Evidence and coordination update

After a real attempt, update `nonproduction-readiness-status.md` and
`AGENT_STATE.json` with actual evidence only. A verified endpoint may be named
only when it is safely publishable. Unrun production checks, missing consent,
absent certificate/OBO configuration, unavailable SQL access, or no deployment
owner remain explicit blockers. Contract-ready source code is not deployment-ready
integration.
