# SAHOOL RC16 v58 — Provider-Native Tool Calling + Approval UI Completion

Date: 2026-07-01

## Scope completed

This package hardens v58 from a one-pass provider tool call bridge into a production-shaped Agent Harness loop:

1. Provider-native schemas remain available for:
   - OpenRouter / OpenAI-style `tools[].function`
   - Anthropic / local messages-style `tools[].input_schema`

2. The generation loop now supports multi-round provider-native tool use:
   - `LLM -> tool_use`
   - `Harness -> governed execution / pending approval`
   - `LLM <- native tool_result`
   - repeated until final answer or `max_tool_rounds`
   - service default raised to `max_tool_rounds=3`
   - hard cap remains 5 in `ai_generation.generate()`

3. Tool results are returned in native provider format:
   - OpenAI/OpenRouter: assistant `tool_calls` + `role=tool` messages
   - Anthropic/local: `tool_use` + `tool_result` content blocks
   - fallback text payload remains available for provider incompatibility

4. Approval/audit was strengthened:
   - `input_hash` is created from redacted parameters
   - `result_summary` avoids storing full result payloads
   - `field_id`, `provider`, and `model` are attached when available
   - sensitive params such as `api_key`, `token`, `password` remain redacted

5. Chatbot approval UI is still guarded:
   - pending approval cards
   - risk badge
   - approve / reject buttons
   - harness transparency panels

6. TrueColor default guard remains passing:
   - MapHub default stays `truecolor`
   - no fallback to NDVI/weather/null default
   - runtime TrueColor raster-service verification guards still pass

## Files changed

- `services/ai_agronomist/ai_generation.py`
- `services/ai_agronomist/main.py`
- `services/ai_agronomist/tool_loop.py`
- `services/ai_agronomist/tool_executor.py`
- `services/ai_agronomist/approval.py`
- `tests_v9/test_ai_provider_native_multiround_audit_v58.py`

## Verification

### Python unit/contract guards

Command:

```bash
python -m pytest -q \
  tests_v9/test_ai_provider_native_tool_calling_v58.py \
  tests_v9/test_ai_provider_native_multiround_audit_v58.py \
  tests_v9/test_ai_tool_loop_chat_integration_v57.py \
  tests_v9/test_ai_tool_loop_v56.py \
  tests_v9/test_ai_tool_executor_v55.py \
  tests_v9/test_ai_approval_audit_v55.py \
  tests_v9/test_ai_tool_registry_v55.py \
  tests_v9/test_ai_harness_transparency_v55.py
```

Result:

```text
52 passed in 1.48s
```

### Frontend static guards

Command:

```bash
cd frontend
npm ci --no-audit --no-fund
npx vitest run \
  src/sections/ChatbotProviderToolApproval.v58.static.test.ts \
  src/sections/MapHubSatelliteDefault.static.test.ts \
  src/sections/MapHubTrueColorRuntime.v54.static.test.ts
```

Result:

```text
3 test files passed, 9 tests passed
```

## Remaining honest boundary

The approve/reject buttons are rendered and guarded in the UI, but this package does not yet wire those buttons to a persistent approval decision endpoint. That should be a small follow-up if the backend already exposes approval decision APIs; otherwise it belongs at the start of v59 or as `v58.1 Approval Decision API`.
