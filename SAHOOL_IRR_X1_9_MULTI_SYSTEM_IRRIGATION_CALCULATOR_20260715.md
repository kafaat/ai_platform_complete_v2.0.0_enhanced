# SAHOOL IRR-X1.9 — Multi-System Irrigation Calculator

## Scope
Extended the reservoir/booster hydraulic calculator from optional center-pivot-only UI semantics to a vendor-neutral optional terminal irrigation system.

Supported terminal modes:
- no machine (reservoir + booster + mainline only)
- center pivot
- linear move
- reel irrigator
- sprinkler
- drip
- valve network

## Backend
Added `IrrigationMachineInput` with system-specific fail-closed validation and retained the IRR-X1.8 `PivotMachineInput` request/result aliases for backward compatibility.

The network runtime now emits:
- `machine_mode`
- `selected_machines`
- per-machine system type and declared hydraulic duty
- drip emitter aggregate flow consistency
- sprinkler aggregate flow consistency
- linear/reel/zone metadata
- single-machine and all-enabled-machine capacity scenarios

The common reservoir, booster, mainline, TDH, power and water-balance calculations remain shared across all systems.

## Frontend
Replaced the pivot checkbox with an optional irrigation-system selector. System-specific fields appear only for the selected type. Selecting “none” preserves pump-only/network-only calculation.

## Compatibility
IRR-X1.8 clients using `pivots` and `requested_pivot_ids` remain accepted. Result aliases `pivot_mode` and `selected_pivots` remain present.

## Verification
- Python compilation: PASS
- CI YAML parse: PASS
- IRR-X1.8 compatibility guard: PASS
- IRR-X1.9 guard: PASS
- Focused engineering/UI tests: 19 passed, 0 failed
- Frontend production build: not executed because `node_modules` is absent in the supplied archive

## Deliberate boundaries
- This is a hydraulic engineering estimate, not execution authorization.
- Multiple machines are supported by the backend contract; the current UI configures one optional machine per calculation.
- Branch-specific hydraulic flow splitting is not yet a graph solver.
- Pump-curve/NPSH and pressure-uniformity solvers remain future increments.
