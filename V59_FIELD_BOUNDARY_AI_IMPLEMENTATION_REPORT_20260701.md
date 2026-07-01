# V59 — Field Boundary AI Implementation Report

## Scope implemented

V59 builds on v58's provider-native tool calling loop and adds a governed Field Boundary AI capability.

### Backend / Harness

- Added `services/ai_agronomist/field_boundary_ai.py`.
  - Deterministic proposal engine for first-release boundary suggestions.
  - Accepts `bbox`, `source`, optional `date`, optional `crop_hint`.
  - Returns GeoJSON Polygon proposals with `confidence`, `area_ha`, `method`.
  - Never persists geometry; every output is `requires_user_confirmation=true`.
  - Invalid bbox fails closed with an empty proposal list.

- Added tool registry entries:
  - `detect_field_boundaries`
    - read/compute only
    - risk: `low`
    - capability: `can_read_historical_imagery`
    - no approval required
  - `save_detected_boundary`
    - mutating write action
    - risk: `high`
    - capability: `can_manage_field_boundaries`
    - approval required

- Added capability:
  - `can_manage_field_boundaries`
  - wired into shared capability contract and tenant policy normalization.

- Connected `detect_field_boundaries` to `/api/ai-agronomist/chat` via the existing agent tool fetcher.

### Provider-native schema

- Extended tool schema conversion to support `bbox` as a provider-native JSON Schema array:
  - `type=array`
  - `items=number`
  - `minItems=4`
  - `maxItems=4`
  - semantic description `[lon_min, lat_min, lon_max, lat_max]`

### Frontend

- Added `frontend/src/components/maphub/FieldBoundaryProposalPanel.tsx`.
  - Shows proposed boundaries.
  - Displays confidence and area.
  - Explicitly states proposals are not saved until confirmation.
  - Provides Accept / Edit / Reject actions.

### TrueColor guard retained

- Re-ran existing MapHub TrueColor static guards to ensure v59 did not regress the default imagery behavior.

## Tests executed

### Python / Harness

```text
pytest -q \
  tests_v9/test_field_boundary_ai_v59.py \
  tests_v9/test_ai_tool_loop_v56.py \
  tests_v9/test_ai_tool_loop_chat_integration_v57.py \
  tests_v9/test_ai_harness_transparency_v55.py \
  tests_v9/test_ai_approval_audit_v55.py \
  tests_v9/test_ai_tool_registry_v55.py \
  tests_v9/test_ai_tool_executor_v55.py \
  tests_v9/test_ai_provider_native_tool_calling_v58.py \
  tests_v9/test_ai_provider_native_multiround_audit_v58.py
```

Result:

```text
56 passed
```

### Frontend static guards

```text
cd frontend && npm test -- --run \
  src/sections/MapHubSatelliteDefault.static.test.ts \
  src/sections/MapHubTrueColorRuntime.v54.static.test.ts \
  src/components/maphub/FieldBoundaryProposalPanel.static.test.ts \
  src/sections/ChatbotPage.endpoint.test.ts
```

Result:

```text
4 test files passed
11 tests passed
```

## Honest limitation

This v59 release implements the stable Harness/tool contract and a deterministic proposal fallback. It does not yet run a heavy computer-vision model such as SAM/U-Net/Sen2Agri. The contract is intentionally model-ready: the detector implementation can be replaced later without changing the tool schema, approval policy, audit model, or UI confirmation flow.

## Recommended next phase

`v60 — Productivity Zones`

Use confirmed field geometry plus NDVI/timeline/weather/soil context to compute stable productivity zones before soil sampling and VRA prescription generation.
