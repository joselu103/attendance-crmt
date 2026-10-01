# REST Migration and Compatibility

Follow the [REST v1 contract](../contracts/attendance-rest-v1.md) for public API
work. Attendance CRMT is REST-only; any external transport adapter belongs to
its owning repository, not this one.

The repository-owned REST v1 contract is the adapter-facing inventory. Keep it
aligned with any REST route added during migration.

Do not add transport-specific runtime dependencies or compatibility endpoints.
Do not treat local migration work as deployment, Entra, SQL Server, or
audit-readiness evidence.

Read the active inbox directive and [next action](../../../docs/next-action.md) for
the current ordered slice.
