# V62 — VRA Prescription Engine Implementation Report

Date: 2026-07-01
Base package: `sahool_v9.1.0_bc42493_v61_5_agent_agronomy_hardened.zip`
Output package: `sahool_v9.1.0_bc42493_v62_vra_prescription_engine.zip`

## Scope

Implemented V62 as a governed, proposal-only VRA prescription engine on top of the v61.5 hardened agent harness.

The design intentionally separates:

1. **Read/compute proposal**: `generate_vra_prescription`
2. **Write/export/persist action**: `create_prescription_map` behind high-risk approval

This preserves the v61.5 governance rule: the LLM may propose and explain, but official map creation or machine export requires human approval and domain execution outside the chat runtime.

## Backend Changes

### Added

- `services/ai_agronomist/vra_prescription_engine.py`
  - `generate_vra_prescription(params, field_id=None, evidence_context=None)`
  - Supports product types:
    - `fertilizer`
    - `lime`
    - `seed`
    - `irrigation`
  - Inputs:
    - productivity zones
    - soil sampling plan
    - optional lab results
    - crop / target yield
    - product type / base rate / unit
    - `allow_estimated`
  - Outputs:
    - `vra_prescription`
    - `prescription_zones`
    - `data_completeness`
    - `readiness_gate`
    - warnings
    - confidence

### Updated

- `shared/ai/tool_registry.py`
  - Added low-risk proposal tool: `generate_vra_prescription`
  - Kept high-risk approval tool: `create_prescription_map`
  - Strengthened `create_prescription_map` params with `prescription_id`

- `services/ai_agronomist/tool_executor.py`
  - Added metadata for `generate_vra_prescription`
  - Preserved fail-closed policy and high-risk approval behavior

- `services/ai_agronomist/main.py`
  - Wired `generate_vra_prescription` into the agent tool fetcher

- `shared/ai/tool_schema.py`
  - Added provider-native schema guidance for VRA
  - Added parameter descriptions for VRA fields
  - Added `object` parameter support
  - Added enum for `product_type`

## Frontend Changes

### Added

- `frontend/src/components/maphub/VraPrescriptionPanel.tsx`
- `frontend/src/components/maphub/VraPrescriptionPanel.static.test.ts`

### Updated

- `frontend/src/sections/ChatbotPage.tsx`
  - Renders VRA prescription proposals from `generate_vra_prescription`

- `frontend/src/sections/ChatbotAgronomyPanels.v615.static.test.ts`
  - Guards VRA panel wiring

## Governance / Safety

V62 does not create an executable prescription map automatically.

Readiness gate behavior:

- No productivity zones → blocked
- No lab results and no explicit `allow_estimated` → blocked
- Estimated prescription → proposal only, not machine exportable
- Lab-supported prescription → still requires agronomist review before export

`create_prescription_map` remains high-risk and approval-gated.

## Tests Run

### Python targeted harness guards

```text
60 passed
```

Included:

- `test_ai_tool_registry_v55.py`
- `test_ai_tool_executor_v55.py`
- `test_ai_tool_loop_v56.py`
- `test_ai_provider_native_tool_calling_v58.py`
- `test_ai_provider_native_multiround_audit_v58.py`
- `test_ai_approval_endpoints_v58.py`
- `test_agent_agronomy_hardening_v615.py`
- `test_field_boundary_ai_v59.py`
- `test_productivity_zones_v60.py`
- `test_soil_sampling_planner_v61.py`
- `test_vra_prescription_engine_v62.py`

### Frontend static guards

```text
5 test files passed
8 tests passed
```

### Frontend typecheck

```text
passed
```

## Honest Limitations

- V62 is a deterministic, map-based proposal engine, not a full agronomic recommendation model.
- It does not export ISOXML/John Deere/Raven/Trimble files yet.
- It does not persist prescription maps in a domain database yet.
- It does not replace agronomist review; output is explicitly gated.

## Recommended Next Step

`v62.1 — Prescription Export Adapters`

- GeoJSON export hardening
- Shapefile/ZIP adapter
- ISOXML adapter scaffold
- equipment profile selection
- final approval workflow into domain service
