# Platform Route Release Binding Closure — 2026-07-28

## Decision

The platform route-governance statement is now bound to both the source release
inventory and the immutable release ZIP. Route governance can no longer be
validated only in the worktree while the published archive remains unbound.

## Source binding

`release/PLATFORM_ROUTE_GOVERNANCE_BINDING.json` records SHA-256 digests for:

- the generated route-governance attestation;
- the generated domain-route budget inventory;
- the generated full ownership inventory.

It also records the canonical route counts. The file is included in
`release/FILE_CHECKSUMS.sha256` and is validated by the release-package gate.

## Archive binding

`scripts/release/platform_route_release_binding.py --archive ...` emits a
sidecar containing the exact archive SHA-256, byte size, source-binding SHA-256,
route-governance statement SHA-256, and canonical route counts. Revalidation
fails after any archive mutation.

## Release CI

The release-attestation workflow now verifies ownership, budget, governance
attestation, and source binding before packaging. After `git archive`, it emits
and verifies the archive sidecar and uploads it beside the ZIP, checksum, source
binding, and CycloneDX SBOM.

## Preserved ratchet

- raw direct routes: 630
- infrastructure routes: 4
- domain-budget routes: 626
- domain maximum: 629
- full ownership surface: 634

No budget increase was introduced.
