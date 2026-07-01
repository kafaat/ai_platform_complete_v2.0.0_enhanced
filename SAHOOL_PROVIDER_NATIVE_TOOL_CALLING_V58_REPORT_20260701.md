# SAHOOL v58 — Provider-Native Tool Calling + Approval UI

## Scope
Implemented the next harness phase after v57: provider-native tool schemas for read-only agricultural tools, provider response parsing, governed execution through the existing `tool_loop`, and web approval controls for pending high-impact actions.

## Key changes

### Backend
- `services/ai_agronomist/provider_tooling.py`
  - Provides provider-native tool schemas for OpenRouter/OpenAI-style `tools` and Anthropic-style `tools`.
  - Exposes read-only tools only:
    - `get_field_state`
    - `get_truecolor_scene`
    - `get_index_timeline`
    - `get_weather_history`
    - `get_operation_windows`
    - `get_alerts`
    - `get_drawings_and_zones`
    - `open_map_layer`
  - Does not expose mutating/high-risk tools such as `request_imagery_backfill`, `send_recommendation`, `create_prescription_map`, or `schedule_irrigation`.
  - Parses OpenRouter/OpenAI `tool_calls` and Anthropic `tool_use` blocks into the internal governed `tool_loop` request shape.

- `services/ai_agronomist/ai_generation.py`
  - Accepts provider-native `provider_tools`.
  - Adds tools to outbound provider payloads.
  - Returns parsed provider-native tool calls in `GenResult.tool_calls`.

- `services/ai_agronomist/main.py`
  - Builds provider-native read-tool schemas when chat generation is enabled.
  - Combines provider-native tool calls with explicit request tool calls.
  - Routes all calls through `tool_loop.run_tool_calls`.
  - Returns:
    - `provider_native_tool_calls`
    - `provider_native_tool_rounds`
    - governed `tool_calls`
    - governed `pending_approvals`
  - Adds `/approvals/approve` and `/approvals/deny` endpoints that normalize human decisions without executing mutating tools directly.

### Frontend
- `frontend/src/sections/ChatbotPage.tsx`
  - Shows approval cards for pending harness approvals.
  - Adds explicit approve/deny buttons.
  - Posts decisions to `/api/ai-agronomist/approvals/approve` or `/api/ai-agronomist/approvals/deny`.

### Tests
- `tests_v9/test_provider_native_tool_calling_v58.py`
- `tests_v9/test_ai_approval_endpoints_v58.py`
- `frontend/src/sections/ChatbotApprovalUi.v58.static.test.ts`

## Guarded product decision
MapHub default remains protected:

`TrueColor raw Sentinel-2 imagery` is the default field view.
Weather and NDVI/NDMI remain explicit overlays only.

## Validation

Backend:
- `tests_v9/test_provider_native_tool_calling_v58.py`
- `tests_v9/test_ai_approval_endpoints_v58.py`
- `tests_v9/test_ai_tool_loop_chat_integration_v57.py`
- `tests_v9/test_ai_tool_loop_v56.py`
- `tests_v9/test_ai_tool_executor_v55.py`

Result: 29 passed.

Frontend:
- `ChatbotApprovalUi.v58.static.test.ts`
- `ChatbotHarnessTransparency.v55.static.test.ts`
- `ChatbotAiEvidenceTransparency.static.test.ts`
- `MapHubTrueColorRuntime.v54.static.test.ts`
- `MapHubSatelliteDefault.static.test.ts`

Result: 14 passed.

TypeScript and build:
- `npm run typecheck` passed.
- `npm run build` passed.
- Existing Vite warning remains: `LeafletDrawAdapter` dynamic import also statically imported. This is not a build failure.

Backend compile:
- `python3 -m compileall -q services/sahool-platform/api services/sahool-platform/core services/ai_agronomist tools` passed.
