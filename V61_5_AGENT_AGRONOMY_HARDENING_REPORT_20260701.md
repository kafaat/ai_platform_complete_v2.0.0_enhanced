# V61.5 — Agent Agronomy Hardening Report

Date: 2026-07-01
Base: `sahool_v9.1.0_bc42493_v61_agent_tools.zip`
Output: `sahool_v9.1.0_bc42493_v61_5_agent_agronomy_hardened.zip`

## Scope

This patch hardens the v58-v61 agent tool chain before moving to v62 VRA prescriptions.
It keeps v59/v60/v61 as proposal engines, but closes the governance gaps found in review.

## Implemented

### 1. Pending approval audit fidelity

Updated `services/ai_agronomist/tool_loop.py` so pending approvals now preserve:

- `params` before redaction in audit pipeline
- `input_hash`
- `field_id`
- `result_summary`
- `provider`
- `model`

This makes high-risk save tools traceable and replay-linkable.

### 2. Approval persistence callbacks

Added a lightweight in-process approval/audit ledger in `services/ai_agronomist/main.py`:

- `AGENT_TOOL_AUDIT_LOG`
- `PENDING_APPROVAL_STORE`
- `_save_agent_tool_audit`
- `_save_pending_approval`

The Harness now passes these savers into both provider-native tool calls and manual UI-supplied tool calls.
Production can replace these callbacks with DB/event-store writers without changing the contract.

### 3. Approval decision hardening

Approval endpoints now:

- resolve stored pending approval by id when available
- record approve/deny audit envelopes
- return a `resume` envelope for approved actions
- keep `executes_tool: false` to avoid unsafe write execution inside the chat runtime

This is a safer intermediate state: approved actions are ready for domain-service execution, not executed by the LLM service.

### 4. Provider stop/finish reason handling

Updated `services/ai_agronomist/ai_generation.py` to normalize provider stop reasons:

- OpenRouter/OpenAI `finish_reason`
- Anthropic/local `stop_reason`

Incomplete reasons such as `length`, `max_tokens`, `model_context_window_exceeded`, `content_filter`, and `refusal` are surfaced in the generated answer metadata and warning text.

### 5. Tool schema strengthening

Updated `shared/ai/tool_schema.py` with:

- `when_to_use`
- `when_not_to_use`
- `input_examples`
- parameter descriptions
- enums for `source`, `basis`, and `lab_panel`
- explicit approval warning in save-tool descriptions

This gives provider-native tool calling better selection guidance.

### 6. Frontend proposal panel wiring

Updated `frontend/src/sections/ChatbotPage.tsx` to render existing proposal panels from Harness tool results:

- `FieldBoundaryProposalPanel`
- `ProductivityZonesPanel`
- `SoilSamplingPlannerPanel`

Added `ChatbotAgronomyPanels.v615.static.test.ts` to guard the wiring.

## Tests

Python targeted harness guards:

```text
54 passed
```

Frontend static guards:

```text
6 files passed
11 tests passed
```

Frontend TypeScript:

```text
npm run typecheck -- --pretty false
passed
```

## Production note

This patch intentionally does not let `/chat` directly execute write actions. It creates a safe `approved_ready_for_domain_execution` envelope. The next hardening step can wire that envelope to domain services such as field geometry, zone storage, or task creation with tenant/RLS checks.
