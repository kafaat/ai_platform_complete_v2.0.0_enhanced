# Platform Route Ownership and Budget Reconciliation — 2026-07-27

- Domain-budget inventory remains the historical direct decorator unit: 630 raw, 4 infrastructure, 626 domain, budget 629.
- Full ownership surface additionally tracks four literal `api_route(methods=[...])` declarations.
- PLATFORM_EXTRACTION_MAP now exactly matches 634 route declarations, including current source files and line numbers.
- CI executes the ownership guard before the budget/generated-inventory guard.
- Multi-method proxy declarations are visible to governance without silently changing the established P2.6 budget unit.
