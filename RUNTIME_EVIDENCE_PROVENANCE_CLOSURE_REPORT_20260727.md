# SAHOOL Runtime Evidence Provenance Closure — 2026-07-27

## Scope

This patch closes the repository-side trust gaps identified after the provenance-hardened ARC while deliberately retaining a read-only capability bridge and zero certification state.

## Implemented controls

- Runtime images are built and pushed by a GitHub-hosted builder workflow.
- Each OCI image digest receives GitHub Artifact Attestation provenance.
- PATH-3 accepts an exact image-build workflow run, verifies all OCI attestations, and generates a pull-by-digest Compose override.
- The runtime producer uses a protected GitHub Environment and a dedicated `sahool-path3-trusted` runner label.
- The self-hosted producer has no OIDC or attestation-write permission.
- Evidence bundle signing occurs in a separate GitHub-hosted protected signer job.
- A separate verifier re-downloads and verifies the evidence attestation.
- The verifier issues a provenance receipt bound to repository, source SHA/ref, signer workflow, verification run, and exact evidence bundle SHA-256.
- `runtime_identity_bridge.py` refuses evidence without the receipt and original bundle, recalculates the bundle digest, and enforces one registered environment and the configured signer workflow.
- A GitHub Actions artifact-backed replay guard rejects already-consumed bundle digests and publishes an append-only consumption marker.
- The deployment manifest distinguishes registry distribution digest from Docker config digest and requires the running image RepoDigest to match the externally attested pull-by-digest reference.
- Release manifests and checksums are regenerated after all changes.

## Deliberate safety boundary

- No Step-4 writer exists.
- No tool writes `runtime_verified`.
- No tool writes `production_certified`.
- Live PATH-3 execution was not performed in the packaging environment; the committed workflow is the enforceable execution path.

## Static verification results

- Targeted architecture tests: 71 passed.
- Functional probe plan validation: 3 plans / 6 probes.
- Runtime identity bridge validation: 3 identities / 5 coverage rules.
- PATH-1 static governance closure: 20/20.
- GitHub Actions policy guard: 193 immutable action references.
- Release package validation: 5141 checksums before this report was added; final release regeneration supersedes that count.
