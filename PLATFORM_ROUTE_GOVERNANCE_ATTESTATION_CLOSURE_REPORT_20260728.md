# Platform Route Governance Attestation Closure

Date: 2026-07-28

## Decision

The platform route budget and ownership guards are now cross-bound by a generated, content-addressed governance attestation. The domain-route ratchet remains unchanged at 629.

## Enforced state

- Direct/raw route declarations: 630
- Infrastructure declarations: 4
- Domain-budget declarations: 626
- Domain-route maximum: 629
- Full ownership surface: 634
- Multi-method `api_route` declarations: 4

## Generated evidence

- `docs/architecture/generated/platform_route_budget_inventory.json`
- `docs/architecture/generated/platform_route_ownership_inventory.json`
- `docs/architecture/generated/platform_route_governance_attestation.json`

The attestation binds SHA-256 digests for the canonical classification contract, extraction map, budget inventory, ownership inventory, and the normalized count statement. Drift in any source requires regeneration and fails CI otherwise.

## CI behavior

The dedicated workflow now verifies ownership, budget, and cross-source attestation independently, then uploads all three result documents as a retained artifact.
