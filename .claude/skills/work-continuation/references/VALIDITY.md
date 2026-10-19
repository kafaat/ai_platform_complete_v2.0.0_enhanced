# Validity, provenance, recoverable phases

## Evidence levels

- `RECORDED_UNVERIFIED`: a handoff or external claim; cannot authorize action or certify completion.
- `VERIFIED_CURRENT`: direct evidence checked against the relevant current input revision and source-of-truth.
- `STALE`: previous evidence is real but no longer applies to current inputs/time window.
- `INTERRUPTED`: start known, terminal outcome not established.
- `EFFECT_UNKNOWN`: target side effect may have occurred; reconcile before retry.

A SHA-256 digest checks byte identity, **not truth, security, completeness, or authorship**. A URL is a reference, not an immutable input unless its version is pinned or content captured under authorization.

## Minimal validity key

Define `validity_context = {task_kind, operation_or_check, relevant_input_versions, dependency_versions, runtime_or_policy_versions, base_revision_if_relevant}`. Calculate deterministic digest of a canonical serialization when a hashing capability is available. Else save explicit fields and mark digest as `unavailable`.

For Git diff and integration checks: use `head`, `tree`, `base_head`, `merge_base` when relevant, not source tree alone. For documents: source IDs, revision/ETag/checksum. For research: source URL, retrieval timestamp, datedness/freshness expectations; refresh volatile claims before decision. For cloud services: commit or configuration identity and fresh observed state. Record only relevant fields, but do not omit a dependency merely to reuse a pass.

## Safe checkpoints

- Fixed unit IDs and a stable shard manifest for long suites; every result stores scope, evidence reference, exit code if executable, outcome, and validity context.
- Record launch identity/inputs promptly; do not use stale run IDs as liveness proof.
- When filesystem durability is actually available: append an event for a finished unit; then write an atomic snapshot; re-read/check integrity. An interrupted event write remains an interrupted event, never a PASS.
- Recover by replaying verified completed receipts and reconciling incomplete effects; avoid rerunning passing units whose contexts remain valid.
- `SHARDED_VERIFICATION` is never `CONTIGUOUS_PREFLIGHT`. An end-to-end gate is passed only by a complete qualifying execution.
- Do not delete or regenerate historic evidence until retention policy and authorization allow it. Control log size and avoid filling disk.
