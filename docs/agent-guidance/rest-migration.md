# REST Migration and Compatibility

Follow the root [REST/MCP architecture decision](../../../docs/architecture/0001-rest-core-mcp-adapter.md)
and [REST v1 contract](../../../docs/contracts/attendance-rest-v1.md) for public API
work. The final external MCP transport belongs to the future `attendance-mcp`
adapter, not this repository.

The repository-owned [REST v1 contract](../contracts/attendance-rest-v1.md)
is the adapter-facing inventory for every legacy MCP tool. Keep it aligned with
any REST route added during migration.

Preserve the embedded FastMCP runtime as the rollback bridge until REST and the
approved adapter have verified parity. Do not treat local migration work as
deployment, Entra, SQL Server, or audit-readiness evidence.

Read the active inbox directive and [next action](../../../docs/next-action.md) for
the current ordered slice.
