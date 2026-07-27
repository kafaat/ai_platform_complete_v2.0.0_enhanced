# SAHOOL Infrastructure Route Budget Closure

Date: 2026-07-27

## Decision

`GET /runtime-identity` is classified as an infrastructure/provenance endpoint. It remains visible in the raw platform route inventory and ownership map, but does not consume the domain-route ratchet.

## Canonical policy

The exact allowlist is defined in `shared/governance/platform_route_budget.py`:

- `GET /healthz`
- `GET /readyz`
- `GET /metrics`
- `GET /runtime-identity`

Classification is based only on normalized `(HTTP method, path)` equality. Prefix, suffix, substring, descendant, and different-method matches are not excluded.

## Verified inventory

- Raw statically declared routes: 630
- Infrastructure routes: 4
- Domain-budget routes: 626
- Domain budget maximum: 629

The raw count increased through the provenance endpoint while the domain budget remained unchanged.

## Regression coverage

Tests prove that these routes remain counted in the domain budget:

- `GET /fields/runtime-identity`
- `GET /runtime-identity/export`
- `GET /runtime-identity-extra`
- `POST /runtime-identity`

Both the P0 ownership guard and P2.6 budget guard use the central exact classification. Infrastructure routes remain ownership-mapped and cannot bypass documentation.
