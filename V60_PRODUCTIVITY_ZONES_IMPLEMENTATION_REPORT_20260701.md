# V60 — Productivity Zones Implementation Report

Date: 2026-07-01
Base: `sahool_rc16_d5b1918_v59_field_boundary_ai.zip`

## Implemented

### Backend / Agent Harness

- Added deterministic proposal engine:
  - `services/ai_agronomist/productivity_zones.py`
  - `propose_productivity_zones(...)`
- Added Agent tool:
  - `generate_productivity_zones`
  - low risk, read/compute only
  - requires `can_read_historical_imagery`
  - returns confirmable GeoJSON productivity zones
  - never persists zones automatically
- Added approval-gated write tool:
  - `save_productivity_zones`
  - high risk
  - requires `can_manage_productivity_zones`
  - requires human approval
- Extended capability contract:
  - `can_manage_productivity_zones`
- Extended provider-native tool schema:
  - supports optional `boundary` as GeoJSON object
  - supports `bbox` fallback
  - supports `zone_count` and `basis`
- Connected `generate_productivity_zones` to `/api/ai-agronomist/chat` through the existing Harness fetcher.

### Frontend / UI

- Added `ProductivityZonesPanel.tsx`:
  - renders high/medium/low productivity zone proposals
  - shows score, confidence, area, and evidence drivers
  - exposes human actions:
    - accept zones
    - reject zones
    - continue to v61 soil sampling planner
  - displays a non-persistence notice: zones are not saved until confirmed

### Safety model

- `generate_productivity_zones` is proposal-only.
- `save_productivity_zones` is a separate high-risk approval action.
- v59 boundary contracts remain unchanged.
- TrueColor default guards remain unchanged.

## Tests run

### Python targeted V55–V60 Harness guards

Command:

```bash
pytest -q \
  tests_v9/test_ai_tool_registry_v55.py \
  tests_v9/test_ai_tool_executor_v55.py \
  tests_v9/test_ai_tool_loop_v56.py \
  tests_v9/test_ai_provider_native_tool_calling_v58.py \
  tests_v9/test_ai_provider_native_multiround_audit_v58.py \
  tests_v9/test_field_boundary_ai_v59.py \
  tests_v9/test_productivity_zones_v60.py
```

Result:

```text
45 passed
```

### Frontend static guards

Command:

```bash
npx vitest run \
  src/sections/ChatbotProviderToolApproval.v58.static.test.ts \
  src/components/maphub/FieldBoundaryProposalPanel.static.test.ts \
  src/components/maphub/ProductivityZonesPanel.static.test.ts \
  src/sections/MapHubSatelliteDefault.static.test.ts \
  --no-file-parallelism --maxWorkers=1
```

Result:

```text
4 test files passed
9 tests passed
```

### Full tests_v9 attempt

A full `pytest -q tests_v9` was attempted after installing the missing `asyncpg` dependency. It progressed into the larger pre-existing suite but exceeded the execution time budget before completion. During the partial run, pre-existing auth/mobile/database failures appeared before timeout, unrelated to the V60 files touched here.

## Next recommended phase

`v61 — Soil Sampling Planner`

Input should be the confirmed V60 productivity zones. Output should be a confirmable soil sampling plan per zone, with sample points, depth, lab package, priority, and chain-of-custody metadata.
