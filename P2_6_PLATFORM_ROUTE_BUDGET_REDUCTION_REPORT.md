# P2.6 Platform Route Budget Reduction / Freeze

Implemented after Raster, Weather, and Decision extraction boundaries.

## Measurement

- Prior route baseline: `567` AST-detected platform routes.
- Current AST-detected platform route count: `567`.
- Budget policy: no route growth beyond the verified budget without ownership-map review.

## Note

The extraction work primarily moved ownership semantics and transport wiring behind service facades. It did not remove legacy BFF routes yet, so the route budget is frozen rather than reduced. Reduction should happen only when compatibility routes are deleted safely.

## Guard

`services/sahool-platform/tests/test_p2_6_platform_route_budget_reduction.py`
