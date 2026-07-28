# SAHOOL Platform Route Budget — Independent CI Ratchet

Date: 2026-07-27

## Closure

The infrastructure exclusion is now enforced by a dependency-free executable CI guard, not only by a pytest collected inside the platform suite.

- Canonical classification: `scripts/ci/platform_route_classification.py`
- Executable guard: `scripts/ci/platform_route_budget_guard.py`
- Generated transparent inventory: `docs/architecture/generated/platform_route_budget_inventory.json`
- Dedicated workflow: `.github/workflows/platform-route-budget.yml`

## Current verified counts

- Raw routes: 630
- Infrastructure routes: 4
- Domain-budget routes: 626
- Domain maximum: 629
- Headroom: 3

The generated inventory records method, normalized path, source file, line, function and classification for every declaration. CI fails when the generated file is stale, the documented allowlist differs from the canonical allowlist, an allowlist member is unused, a route path is non-literal, or the domain budget is exceeded.
