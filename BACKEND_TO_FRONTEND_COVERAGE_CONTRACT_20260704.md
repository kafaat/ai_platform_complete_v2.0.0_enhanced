# SAHOOL — Backend-to-Frontend Coverage Contract

Date: 2026-07-04
Base: `sahool_main_5015796_coverage_71_endpoints_green.zip`
Output: `sahool_main_5015796_backend_coverage_contract_final.zip`

## Purpose

This patch closes the governance gap discovered after the 71-endpoint exposure work: advanced backend layers can no longer remain ambiguous. Each important backend capability now has an explicit frontend coverage contract:

- user/admin/expert visibility role
- coverage state
- route/page/card/panel surface
- hook names
- endpoint patterns
- explicit waiver or next action when not fully exposed

The goal is not to expose every backend endpoint to normal users. The goal is to prevent silent drift: every material backend layer must be either surfaced, intentionally internal, or explicitly not-ready.

## Added

### `frontend/src/config/backendCoverageRegistry.ts`

Adds a typed registry for backend-to-frontend coverage:

- `BACKEND_COVERAGE_REGISTRY`
- `coverageSummary()`
- `criticalCoverageGaps()`
- `endpointCoverageMap()`
- `layerForEndpoint()`

### `frontend/src/config/backendCoverageRegistry.test.ts`

Adds static guards that verify:

1. every registered layer has endpoint patterns, owner, role, priority, and coverage state;
2. P0/P1 layers cannot silently stay partial/not-ready;
3. exposed layers must have hooks and a real UI surface;
4. internal layers require a waiver reason;
5. route-backed surfaces are synchronized with `ALL_ROUTES`;
6. hook/component references are grounded in the source tree;
7. endpoint pattern lookup maps back to the owning layer.

## Registered backend layers

| Layer | State | Role | Priority |
|---|---|---|---|
| Admin Runtime Ops | covered | admin_console | P0 |
| Decision Runtime | covered | manager_console | P0 |
| Yemen Calendar Local Knowledge | covered | fieldview_user | P1 |
| Crop Cards / Variety Intelligence | covered | fieldview_user | P1 |
| Boundary Governance | covered | expert_console | P1 |
| Farm Ledger / Economics | covered | manager_console | P1 |
| Traceability / Harvest Lots | covered | manager_console | P2 |
| Crop Planning / Rotation / Planting | partial | fieldview_user | P1 |
| Climate Risk / Analogs | covered | expert_console | P1 |
| Water Harvesting / Irrigation Methods | covered | expert_console | P2 |
| Propagation / Postharvest / Coffee | covered | fieldview_user | P2 |
| Advanced GIS / OGC / STAC / COG | partial | expert_console | P2 |
| Soil / Lab / Salinity / IPM | partial | expert_console | P2 |
| Simulation / Crop Twin / Scenarios | partial | manager_console | P2 |
| Zones / VRA / Soil Sampling | covered | expert_console | P1 |
| Collaboration / Approvals / Sharing / RBAC | partial | manager_console | P2 |
| Phase Runtime / Registry / Sync | waived_internal | internal_only | P2 |
| Marketplace / Plugins / Ecosystem | not_ready | manager_console | P3 |

## Intentional remaining gaps

The registry makes these gaps explicit instead of hidden:

1. `crop-planning-rotation-planting`: still needs dedicated Objective Engine targets for planting window, rotation, and GDD tracking.
2. `advanced-gis-ogc-stac-cog`: needs expert source browser for STAC/COG/OGC capabilities.
3. `soil-lab-salinity-ipm`: needs unified diagnostics workbench to combine lab/soil/IPM evidence.
4. `simulation-crop-twin-scenarios`: needs scenario assumption and uncertainty gates.
5. `collaboration-approvals-sharing-rbac`: needs approvals console and Objective Engine approval binding.
6. `marketplace-plugins-ecosystem`: kept not-ready until sandbox, billing, and tenant-isolation policies are finished.
7. `phase-runtime-registry-sync`: intentionally internal-only; only aggregated health belongs in Admin Runtime.

## Verification actually run

Frontend:

```bash
cd frontend
npm ci --legacy-peer-deps --ignore-scripts
npm audit --audit-level=moderate
npx vitest run src/config/backendCoverageRegistry.test.ts src/config/endpoints.test.ts --no-file-parallelism --maxWorkers=1
timeout 360 npm run typecheck
timeout 360 npm run build:docker
```

Results:

- `npm ci`: passed
- `npm audit --audit-level=moderate`: passed, 0 vulnerabilities
- coverage registry + endpoint tests: 2 files passed / 10 tests passed
- `typecheck`: passed
- `build:docker`: passed

Field segmentation:

```bash
cd services/field-segmentation
pytest -q
```

Result: 29 passed.

## Limits

This is source/build/static-contract verification. It is not a full Docker Compose boot, live backend smoke test, or Playwright E2E run.
