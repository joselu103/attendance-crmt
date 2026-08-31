# Attendance Teams Bot ↔ Attendance CRMT MCP Authentication Contract

- **Status:** Accepted for the first authenticated, read-only integration slice
- **Contract version:** 1.2.0
- **Owner:** Attendance CRMT MCP server
- **Consumers:** Attendance Teams Bot and future authorized MCP clients

## 1. Purpose and boundary

The Attendance Teams Bot is a separate Python service and an LLM-powered MCP
client. It receives a Microsoft Teams message, obtains a token representing the
Teams user, and calls this service's MCP tools over HTTPS.

Attendance CRMT is the authoritative security and business boundary. It:

- validates the token presented to its MCP endpoint;
- derives the requester identity and authorization roles;
- maps the authenticated Entra user to an attendance employee;
- enforces requester-scoped and administrator-only tool semantics;
- accesses the established production SQL Server schema; and
- writes the durable audit record.

The Teams bot must not access SQL Server, infer an employee identity, choose a
self-service employee ID, or make an authorization decision.

## 2. Initial scope

Version 1 supports authenticated, read-only, one-to-one Teams conversations.
The first end-to-end operation is a user asking for their own attendance over a
bounded date range. The bot uses a requester-scoped tool such as
`list_my_attendance_events`.

Group chat, channel scope, write tools, delegated administration, and external
Microsoft 365 tenants are out of scope. Teams bot SSO does not support channel
scope, so the initial product must remain personal-chat focused.

## 3. MCP transport and compatibility

| Concern | Decision |
| --- | --- |
| Transport | MCP Streamable HTTP over HTTPS. |
| Endpoint path | `/mcp`. |
| Local development | Contract tests use an in-process fake MCP server. No real Entra token or public endpoint is required locally. |
| Deployed environments | `https://attendance-crmt-dev.<domain>/mcp`, `https://attendance-crmt-staging.<domain>/mcp`, and `https://attendance-crmt.<domain>/mcp`. The real DNS names are deployment configuration, not source code. |
| HTTP security | HTTPS is mandatory outside loopback-only local development. HTTP must be rejected in deployed environments. |
| Client library | The Teams bot uses the official Python `mcp` SDK for Streamable HTTP. It must not call FastMCP internals. |
| Server library | Attendance CRMT continues to use FastMCP. |
| Compatibility rule | The protocol, not either library's private API, is the integration boundary. Before upgrading either dependency, run a compatibility suite that initializes a session, lists tools, calls a requester-scoped tool, handles an authorization failure, and propagates correlation IDs. |

The current container already serves FastMCP Streamable HTTP on port 8000. The
reverse proxy/deployment layer must expose only the HTTPS endpoint; port 8000
is not a public contract.

### 3.1 Canonical requester tool: `list_my_attendance_events`

This is the first client operation. The bot calls it only with the validated
user's delegated access token; it never supplies an employee identity.

| Input | Type | Required | Rule |
| --- | --- | --- | --- |
| `start_date` | ISO 8601 `date` | Yes | Inclusive Europe/Ljubljana calendar date. |
| `end_date` | ISO 8601 `date` | Yes | Inclusive date, not before `start_date`; the range is at most 31 calendar days. |
| `limit` | integer | No | Defaults to 50; must be 1 through 100. |
| `offset` | integer | No | Defaults to 0; must be nonnegative. |

The tool accepts **no** `employee_id`, email, actor ID, tenant/object ID, or
role argument. CRMT derives the employee ID from the validated token and its
unique active-email mapping. The client/LLM must not calculate, override, or
select that identity.

The result is an immutable `AttendanceEventPage` with the following JSON shape:

| Field | Type | Meaning |
| --- | --- | --- |
| `items` | array | Ordered attendance-event summaries for the server-derived employee. |
| `limit` | integer | Applied page size. |
| `offset` | integer | Applied page offset. |
| `next_offset` | integer or `null` | Offset for the next page, or `null` when exhausted. |
| `items[].attendance_event_id` | integer | Established attendance-log identifier. |
| `items[].employee_id` | integer | Server-derived employee identity; informational only. |
| `items[].punch_type`, `items[].location`, `items[].note` | string or `null` | Recorded attendance metadata. |
| `items[].checked_in_at`, `items[].checked_out_at` | RFC 3339 timestamp or `null` | Europe/Ljubljana local wall-clock time with the applicable UTC offset. |

Illustrative successful result:

```json
{
  "items": [
    {
      "attendance_event_id": 100,
      "employee_id": 42,
      "punch_type": "Remote work",
      "location": "Home",
      "checked_in_at": "2026-08-10T08:00:00+02:00",
      "checked_out_at": "2026-08-10T16:00:00+02:00",
      "note": null
    }
  ],
  "limit": 50,
  "offset": 0,
  "next_offset": null
}
```

Invalid requester date ranges or pagination values return the MCP tool error
`INVALID_ARGUMENT` with the safe message “Check the attendance date range and
pagination values and try again.” Validation diagnostics and rejected values are
not public contract data.

## 4. Entra application topology

The first release is **single tenant**. All accepted tokens must belong to the
configured Attendance CRMT tenant ID.

Two Entra application registrations are required when the integration is
implemented:

1. **Attendance Teams Bot client application**
   - Represents the Teams bot and its confidential server-side component.
   - Is configured for Teams bot SSO and receives the user assertion for the
     bot audience.
   - Has delegated permission to the Attendance CRMT API scope described below.
   - Uses a certificate in production; a short-lived client secret is allowed
     only for local development.

2. **Attendance CRMT MCP API resource application**
   - Represents the remote MCP server as an Entra-protected API.
   - Exposes exactly one delegated scope for this first release:
     `api://<attendance-crmt-mcp-api-client-id>/attendance.access`.
   - Defines the optional `attendance.admin` app role for privileged users.
   - Is the audience of the access token presented to `/mcp`.

The Teams Developer Portal app ID is Teams package metadata. It is not a secret
and must not be substituted for the Attendance CRMT API's audience.

## 5. Token flow

### Decision: on-behalf-of exchange

The bot performs an OAuth 2.0 **on-behalf-of (OBO)** exchange. It does not
forward the Teams SSO token directly to Attendance CRMT.

```text
Teams user
  → Teams SSO token issued for the bot application (token A)
  → Attendance Teams Bot confidential backend
  → OBO exchange for Attendance CRMT `attendance.access` (token B)
  → Authorization header carrying access-token B
  → Attendance CRMT `/mcp`
```

Token A has the bot application as its audience and is valid only for that
middle tier. The bot exchanges it for token B, whose audience is the Attendance
CRMT MCP API. The MCP server accepts only token B.

This avoids accepting a token intended for a different API and preserves the
user's delegated identity across the bot-to-MCP boundary. OBO uses delegated
scopes; the bot must never use an app-only client-credentials token for a
user-scoped attendance call.

The Teams bot acquires and refreshes token B through Microsoft-supported MSAL
APIs. It never returns token A or B to Teams, stores neither in conversation
state, and never writes either token to logs, audit request JSON, exceptions,
or LLM prompts.

## 6. Required access-token validation at Attendance CRMT

Attendance CRMT validates the bearer token before MCP initialization and before
any tool is exposed or called. It obtains signing keys from the configured
single tenant's OpenID Connect metadata/JWKS endpoint and supports normal key
rotation.

The server rejects a token unless all of the following hold:

| Claim or property | Required validation |
| --- | --- |
| Signature | Valid against the tenant's current Entra signing keys. |
| `iss` | Equals the configured tenant's issuer for the token version in use. |
| `tid` | Equals configured `ATTENDANCE_ENTRA_TENANT_ID`. |
| `aud` | Equals the Attendance CRMT MCP API application ID URI or client ID configured as the accepted audience. |
| `exp`, `nbf`, `iat` | Valid at the server clock with a small configured clock-skew allowance. |
| `scp` | Contains `attendance.access`. |
| `oid` | Present and a valid Entra object ID. It is the user identity key. |
| `preferred_username` | Present and a nonblank Entra sign-in address for the interim email lookup. |
| `azp` (or `appid` where applicable) | Equals an allow-listed Attendance Teams Bot client ID. |
| token subject | Represents a delegated user; an app-only token is rejected. |

`name`, `email`, and `upn` are display/contact attributes only. They are never
accepted as proof of identity or authorization. During the interim email
mapping, validated `preferred_username` is used solely to locate an active
employee; the signed token remains the proof of identity.

The server stores no raw access token. It creates a server-derived requester
from validated claims only.

## 7. Entra user to employee mapping

### Decision: interim active-email lookup with no SQL Server changes

Attendance CRMT must not create, alter, or populate any SQL Server table for the
initial Teams integration. Instead, after it validates the token, it normalizes
the token's `preferred_username` by trimming surrounding whitespace and using a
case-insensitive comparison against `dbo.izvajalci.email`.

The lookup succeeds only when exactly one row satisfies all of these conditions:

- `active = 1`;
- `email` is nonblank; and
- normalized `email` equals normalized `preferred_username`.

The existing production schema supports this read-only lookup: `izvajalci` has
the canonical `izvajalec_id` primary key, an `email varchar(50)` column, and an
`active` flag. The existing `UserId` foreign key to `dbo.aspnet_Users` is not an
Entra identifier and is not part of this integration.

The server derives `employee_id` from the unique matching employee. It must not
accept an employee ID, email address, role, or identity claim from the bot, LLM,
or MCP tool arguments.

Email matching is an interim operational policy, not a durable identity model.
It is intentionally conservative:

- no match returns `IDENTITY_UNMAPPED`;
- more than one active employee with the same normalized email returns
  `IDENTITY_AMBIGUOUS`;
- inactive employees are never matched; and
- the server must not fall back to `username`, `domain_username`, the existing
  ASP.NET `UserId`, or fuzzy matching.

The current development database has 62 active employees with a usable email
address and three duplicate normalized active email addresses. Those duplicate
addresses cannot authenticate until an administrator resolves them in the
established employee data; the bot must never choose among them. Before any
production deployment, run the same read-only uniqueness check against the
production database and treat its result as the authoritative readiness gate.

## 8. Requester roles and tool authorization

Attendance CRMT creates this internal requester only after token validation and
identity mapping:

```text
actor_id    = "<tid>:<oid>"
employee_id = mapped dbo.izvajalci.izvajalec_id
roles       = server-derived roles
```

### Roles

- A mapped user receives the `employee` role.
- `admin` is added only when the user has the `attendance.admin` app-role
  assignment in the Attendance CRMT MCP API registration.
- The server does not trust a role sent by the bot, LLM, MCP tool arguments, or
  Teams activity payload.

### Authorization semantics

- A requester-scoped tool, such as `list_my_attendance_events`, obtains the
  employee ID exclusively from the server-derived requester. It must never
  accept a target employee ID argument.
- Administrator-only tools require the server-derived `admin` role and may
  accept a target employee ID where their existing contract requires it.
- Unmapped, invalid, or unauthorized callers must never receive another
  employee's attendance data.

## 9. Correlation, logging, and audit

For each user turn, the Teams bot generates a UUID correlation ID and sends it
in `X-Correlation-ID` on every MCP HTTP request. The value is opaque and must
not contain a token, employee name, email address, or Teams message text.

Attendance CRMT validates the value as a UUID, includes it in structured logs,
and persists it with the MCP audit event. The bot records the same value in its
own structured logs. This enables one request to be traced across both services
without storing sensitive content.

Attendance CRMT audit persistence must be extended before authenticated traffic
is enabled to record, at minimum:

- correlation ID;
- server-derived actor ID;
- mapped employee ID;
- server-derived role set or authorization outcome;
- tool name;
- outcome and stable error code, where applicable;
- duration; and
- timestamp.

Raw bearer tokens, full Teams activity payloads, and LLM prompts/responses are
not audit fields.

## 10. Error contract and backend availability

Errors expose stable machine-readable codes and a safe user-facing message. The
bot may translate the safe message for the Teams user but must not inspect or
invent security details.

| Condition | HTTP/MCP behavior | Stable code | Safe bot message |
| --- | --- | --- | --- |
| Missing bearer token | Reject before MCP session | `AUTHENTICATION_REQUIRED` | “Please sign in to use Attendance.” |
| Invalid, expired, wrong-tenant, wrong-audience, or app-only token | Reject before MCP session | `TOKEN_INVALID` | “Your sign-in could not be verified. Please try again.” |
| Valid token, no active matching employee email | Reject tool access | `IDENTITY_UNMAPPED` | “Your Teams account is not linked to an active attendance employee. Contact an administrator.” |
| Valid token, more than one active matching employee email | Reject tool access | `IDENTITY_AMBIGUOUS` | “Your Teams account cannot be linked safely. Contact an administrator.” |
| Invalid requester date range or pagination | MCP tool error; no validation diagnostics | `INVALID_ARGUMENT` | “Check the attendance date range and pagination values and try again.” |
| Authenticated caller lacks a required role | Reject tool access | `FORBIDDEN` | “You do not have permission to do that.” |
| Attendance SQL Server or required audit storage unavailable | No partial tool result; retry-safe failure | `BACKEND_UNAVAILABLE` | “Attendance is temporarily unavailable. Please try again shortly.” |
| Unexpected server error | No internals disclosed | `INTERNAL_ERROR` | “Attendance could not complete that request.” |

For authenticated `/mcp` HTTP requests, the bot sends exactly one
UUID-valued `X-Correlation-ID` header on initialization, tool, and
session-management requests. Attendance CRMT normalizes valid UUIDs to their
canonical lowercase form. Missing, malformed, or duplicate values return HTTP
`400` with `CORRELATION_ID_INVALID` only after bearer authentication succeeds;
missing or invalid bearer authentication retains HTTP `401` precedence.

The server publishes `X-Attendance-MCP-Contract-Version: 1.2.0` on MCP HTTP
responses. After an MCP session is established, authorization, mapping, and
availability failures are MCP tool errors (`isError=true`) containing the stable
code and safe message—not transport-level HTTP `403` or `503` rewrites. No
public error or general structured log includes tokens, claims, emails,
identities, request values, SQL details, or stack traces.

## 11. Contract versioning

This document follows semantic versioning.

- A patch version clarifies wording without changing client behavior.
- A minor version adds optional fields, tools, or error codes compatibly.
- A major version changes authentication, authorization, existing tool schemas,
  or error semantics incompatibly.

The server publishes `X-Attendance-MCP-Contract-Version: 1.2.0` on MCP HTTP
responses. The bot sends `X-Attendance-MCP-Contract-Version: 1` and refuses an
incompatible major version before tool use.

Existing tool schemas remain backward compatible within major version 1. An
incompatible MCP contract receives a separately versioned endpoint; it must not
silently change `/mcp` behavior.

## 12. Implementation sequence

1. Preserve the existing SQL Server schema. Do not add an Entra mapping table,
   modify `izvajalci`, or modify the existing ASP.NET membership tables.
2. Add Attendance CRMT settings and a tested Entra JWT validation component.
3. Implement a read-only, active-email employee lookup and test the unique,
   missing, inactive, and duplicate-email outcomes against SQL Server-compatible
   fixtures.
4. Replace the static MVP requester resolver for authenticated Streamable HTTP
   MCP requests while retaining explicit development-test fakes.
5. Extend audit storage and middleware for correlation and authenticated actor
   fields.
6. Add HTTP/MCP integration tests for every error code and authorization path.
7. In the Teams bot repository, add the real Teams identity adapter and MSAL OBO
   client against this contract, first with a fake MCP server.
8. Create the two Entra application registrations and configure consent only
   after the tested code requires their concrete IDs, redirect configuration,
   and credentials.
9. Deploy a non-production HTTPS MCP endpoint, then test a one-to-one Teams
   conversation with a non-administrator mapped user.

## 13. Sources

- [Microsoft Teams: Enable SSO for your app](https://learn.microsoft.com/en-us/microsoftteams/platform/bots/how-to/authentication/bot-sso-overview?tabs=personal)
- [Microsoft identity platform: OAuth 2.0 on-behalf-of flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-on-behalf-of-flow)
