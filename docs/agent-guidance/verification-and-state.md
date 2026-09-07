# Verification and State

Add behavior-level tests; do not test documentation or configuration prose. Run
the focused test and the full pytest/Ruff/format gates after the final edit. For
public or deployment behavior, read the relevant contract and readiness document
before editing.

Do not commit, push, deploy, provision infrastructure, or use secrets without
explicit user approval. Update `AGENT_STATE.json` only with direct evidence, and
mark an inbox directive completed only after all repository-owned work and
required verification pass.
