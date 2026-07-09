# Field Workspace Production Closure

This document defines the production closure gate for the Sahool Field Workspace line.

## Closed scope

The closed scope covers the UI-5 to UI-35 Field Workspace workstream:

- MapHub shell and clutter control
- Field Workspace route shell
- Field Workspace tab contracts
- Data panels for readiness, timeline, operations, imagery, weather, and irrigation
- Backend façades for imagery, weather, irrigation, priority queue, and unified timeline
- Route ownership cleanup away from `routers/fields.py`
- No frontend-fabricated timeline events, recommendations, reports, irrigation plans, or imagery dates

## Required gates

Run from repository root:

```bash
python scripts/ci/field_workspace_production_closure_gate.py
pytest -q services/sahool-platform/tests/test_ui31_ui35_workspace_completion_guard.py
```

Run from `frontend/`:

```bash
npm ci --ignore-scripts --no-audit --no-fund
npm run typecheck:field-workspace-contract
npm run build
```

## Notes

The full application TypeScript typecheck remains broader than the Field Workspace closure gate. The production build is authoritative for bundle generation, while `typecheck:field-workspace-contract` protects the Field Workspace API contract modules that were added in this line.
