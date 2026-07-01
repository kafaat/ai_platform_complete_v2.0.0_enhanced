# V61 — Soil Sampling Planner Implementation Report

Date: 2026-07-01
Base package: `sahool_rc16_d5b1918_v60_productivity_zones.zip`
Output package: `sahool_rc16_d5b1918_v61_soil_sampling_planner.zip`

## Scope Implemented

V61 adds a proposal-only soil sampling planner on top of V60 productivity zones.

### Backend / Agent Harness

Added:

- `services/ai_agronomist/soil_sampling_planner.py`
  - `plan_soil_sampling(...)`
  - Accepts V60 `productivity_zones` as primary input.
  - Falls back to `boundary` / `bbox` with explicit `geometry_seeded_sampling_fallback` method.
  - Returns:
    - `soil_sampling_plan`
    - `sample_points`
    - per-zone strata
    - lab panel/analytes
    - field-time estimate
    - source evidence date count
    - `requires_user_confirmation=true`
    - `persistence=proposal_only_until_user_confirms`
    - `next_step=v62_vra_prescription_engine`

Updated:

- `services/ai_agronomist/main.py`
  - Added `plan_soil_sampling` to the local tool fetcher used by `/api/ai-agronomist/chat`.
- `services/ai_agronomist/tool_executor.py`
  - Added read/proposal tool:
    - `plan_soil_sampling` → `low`, `can_read_historical_imagery`, no approval.
  - Added write/approval tool:
    - `save_soil_sampling_plan` → `high`, `can_manage_soil_sampling`, approval required.
- `shared/ai/capabilities.py`
  - Added `can_manage_soil_sampling`.
- `services/ai_agronomist/tenant_policies.py`
  - Added `can_manage_soil_sampling` to the closed policy capability set.
- `shared/ai/tool_registry.py`
  - Added `plan_soil_sampling` and `save_soil_sampling_plan`.
- `shared/ai/tool_schema.py`
  - Added JSON Schema support for `array` tool inputs.

## Frontend

Added:

- `frontend/src/components/maphub/SoilSamplingPlannerPanel.tsx`
  - Displays proposed sample points.
  - Shows lab panel, analytes, depth, priority, strata count, estimated field hours.
  - Exposes actions:
    - accept plan
    - reject
    - continue to VRA
  - Explicitly states that the plan is not saved and not converted to tasks until confirmation.

Added static guard:

- `frontend/src/components/maphub/SoilSamplingPlannerPanel.static.test.ts`

## Safety / Governance

- `plan_soil_sampling` is a safe proposal tool only.
- It does not persist data or create field tasks.
- `save_soil_sampling_plan` is separated as a high-risk mutating tool.
- Saving requires:
  - `can_manage_soil_sampling`
  - human approval
- This preserves the v58/v59/v60 pattern:
  - AI proposes.
  - Harness gates.
  - User confirms.
  - Mutating action remains pending approval.

## Tests Run

Python targeted V55–V61 Harness guards:

```text
52 passed
```

Command:

```bash
pytest -q \
  tests_v9/test_ai_tool_registry_v55.py \
  tests_v9/test_ai_tool_executor_v55.py \
  tests_v9/test_ai_tool_loop_v56.py \
  tests_v9/test_ai_tool_loop_chat_integration_v57.py \
  tests_v9/test_ai_provider_native_tool_calling_v58.py \
  tests_v9/test_ai_provider_native_multiround_audit_v58.py \
  tests_v9/test_field_boundary_ai_v59.py \
  tests_v9/test_productivity_zones_v60.py \
  tests_v9/test_soil_sampling_planner_v61.py
```

Frontend MapHub static guards:

```text
7 test files passed
24 tests passed
```

Command:

```bash
cd frontend && npx vitest run src/components/maphub/*.static.test.ts
```

## Honest Limitations

- V61 uses deterministic, testable sampling-plan generation. It does not yet optimize sample locations using real road/accessibility, slope, lab logistics, or spatial autocorrelation.
- It does not create tasks or persist sampling plans by itself; that remains intentionally blocked behind the approval action.
- The next logical stage is `v62 — VRA Prescription Engine`, using confirmed productivity zones and soil sampling results as inputs.
