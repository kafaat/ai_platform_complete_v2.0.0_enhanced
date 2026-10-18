# Router extraction plan: the oversize platform routers (for owner approval)

**Gap:** `ROUTER-SIZE-UNGUARDED-AFTER-MAIN-DECOMPOSITION-01`. Its guard already runs
(`tests/architecture/test_router_size_ratchet.py`, `CEILING = 800`); what remains is "an extraction plan per file,
approved by the owner, with the guards and the extraction map adjusted". This document is that plan. **No code moves
until the owner approves it**, and then one slice per PR.

**Measured on `main@1765d73a0`** (line counts by `wc -l` semantics; routes = `@router.<method>(` decorators):

| File | Lines | Routes | Top-level defs | Anchors in `platform_extraction_map.json` | Code guards/tests naming it | GATE-01 |
|---|---|---|---|---|---|---|
| `api/routers/fields.py` | 4199 | 48 | 59 | 96 | 31 | not frozen |
| `api/routers/weather.py` | 3022 | 29 | 105 | 58 | 13 | not frozen |
| `api/routers/farm_operations_ledger.py` | 1029 | 12 | 22 | 24 | 3 | not frozen |
| `api/routers/decision_review.py` | 920 | 16 | 16 | 32 | 13 | not frozen (but see slice D) |
| `raster-service/routers/fields.py` | 1673 | 18 | 21 | n/a | n/a | **out of scope**: owned by the raster plan (`docs/architecture/raster_service_route_migration_plan.md`) |

## Rules every slice follows

1. **Behaviour-preserving move only.** Same paths, methods, dependencies, response models, status codes and
   permission dependencies. No logic edits in the same PR.
2. **Route order is preserved.** `api/router_registry.py` auto-registers every `api/routers/*` module **in
   alphabetical order of module name**, so a split changes registration order. Each slice adds or extends one test
   that snapshots the ordered `(method, path)` list of `app.routes` before the move, and asserts it is unchanged
   afterwards. Where paths overlap (a literal segment next to `{field_id}`), the new module name is chosen so that
   precedence holds, and the test proves it.
3. **`main.py` is not touched.** It is at its line cap (2553). New modules need no registration line: the registry
   picks them up.
4. **Anchors move with the code.** Every anchor in `docs/architecture/platform_extraction_map.json` that points into
   the moved lines is updated in the same PR. That file is a policy document `--fix` does not regenerate, so this is
   done by hand and checked by its guard.
5. **Text guards are retargeted, not weakened.** Every guard or test that names the old file (counts above) is pointed
   at the new file, or made to read both. A guard that becomes vacuous fails the slice.
6. **Ratchet goes down in the same PR.** `FROZEN_OVERSIZE` is lowered to the new line count of the source file. Any new
   module stays under `CEILING`.
7. **Ownership baselines** (`docs/architecture/db_writer_ownership_baseline.json` and `_triage.json`) are updated where
   a writer function moves, so a move does not appear as a new writer.
8. Generated artifacts are regenerated, the release bundle is built last, and `preflight.sh --fast` passes before each push.

## Slices, lowest coupling first

### A. `farm_operations_ledger.py` (1029 → about 550 + 480): 3 guards, 24 anchors

- **Keep in place:** the ledger itself: operations ×2, budgets ×2, revenues, summary.
- **Move to `farm_ledger_projections.py`:** variance, profitability, erp-projection, inventory-projection,
  economic-state, autowrite-preview. These are read-side projections.
- **Retarget:** `tests_v9/test_c4_economics_erp_payment_boundary_guard.py`, and the ownership baseline entries for any
  writer that moves. Autowrite-preview stays a preview (no write); the C4 boundary guard must still see it.

### B. `weather.py` (3022): 13 guards, 58 anchors, 105 top-level defs (most of the weight is helpers, not routes)

- **B1.** Move the pure helpers (interpolation, tile math, provider selection) into `core/weather_*` modules, with no
  route change. This is the bulk of the reduction.
- **B2.** Move `weather_ops.py` (7 diagnostic routes): health, readyz, self-test, wind-source-selftest,
  runtime-contract, env-doctor, runtime-smoke-plan.
- **B3.** Move `weather_tiles.py` (tile-cache ×3).
- **Keep in place:** data routes: current, forecast, historical, alerts.
- **Retarget:**
  - `scripts/ci/public_weather_route_governance_gate.py`
  - `scripts/ci/s5_exec_01_writer_cutover_guard.py`, the weather learning write path, which must still see exactly one
    writer
  - `test_s5_exec_01_weather_learning_cutover.py`
  - `test_gis_tile_math.py`

### C. `fields.py` (4199): 31 guards, 96 anchors, the most coupled. Last, and in several PRs

- **One sub-resource per PR**, each into `fields_<resource>.py`: imagery (4 routes), seasons (3), soil-lab-tests (3),
  geometry (2), wind (2), activities (2), alerts (2), rotations (2), walk-plan (2), state (2), import (1).
- **Keep in place:** the core field CRUD (6 routes).
- **Ordering hazard:** `fields_import` sorts before `fields` alphabetically. The route-order test (rule 2) must show
  that `/fields/import` still wins over `/fields/{field_id}` as it does today.
- **Retarget per PR only the guards that read that sub-resource.** Examples: `field_workspace_production_closure_gate.py`
  and `backfill_ui_sync_gate.py` for imagery; `raster_production_truth_guard.py` and the p2.5 raster sweep tests for the
  raster-facing paths.

### D. `decision_review.py` (920): 7 text boundary gates

- **Move only** `learning/*` (activation-requests ×2, activation-commands ×2, calibration-dataset, evaluation-runs) to
  `learning_activation.py`. Retarget the `model_activation_*` and `model_promotion_*` boundary gates.
- **Do not move** `decisions/*`, `execution-plans/authorize-dispatch`, `dispatch-authorizations/execute` or
  `execution-requests/verify-outcome`. They are on the physical-effect path. Their file is not in the GATE-01 policy,
  but `dispatch_authorization_boundary_gate.py` and `decision_review_boundary_gate.py` pin them by file. Moving them
  needs its own decision.

## What approval covers, and what it does not

- **Approving this plan authorises:** slices A, B (B1 to B3), C (one PR per sub-resource) and D (learning only), each
  merged only after its own CI and your approval on its final head.
- **It does not authorise:**
  - moving the dispatch/execution routes;
  - any change to `main.py`;
  - any change under `migrations/`;
  - touching the raster router.
- **Expected end state:** no platform router over 800 lines except possibly the fields core and the weather data
  routes. The final numbers are measured per slice, not promised here. `FROZEN_OVERSIZE` shrinks with each slice.
