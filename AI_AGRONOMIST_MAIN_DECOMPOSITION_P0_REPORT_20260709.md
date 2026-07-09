# AI Agronomist `main.py` P0 Decomposition Report — 2026-07-09

## Scope

This continuation implements the second P0 item from the `main.py` decomposition queue:

- `services/ai_agronomist/main.py`

The change is intentionally conservative: routes and public endpoint behavior remain in `main.py`, while the evidence/advisory runtime is moved behind a compatibility wrapper.

## Changes

### 1. Extracted evidence/advisory runtime

Created:

```text
services/ai_agronomist/ai_evidence_runtime.py
```

Moved from `main.py`:

```text
_fetch_canonical_field_state
_extract_evidence_ids
_confidence_from_payloads
_record_ai_advice_event
_generation_allowed
_utc_timestamp
_build_agent_tool_fetcher
_extract_ai_context_pack
_source_count
_ai_context_memory_lines
_field_memory_evidence_ids
_evidence_sources
_grounding_context_text
build_evidence_response
```

### 2. Preserved route compatibility

`main.py` still owns the FastAPI routes:

```text
POST /query
POST /chat
POST /explain
POST /recommend
```

Those routes call a thin compatibility wrapper:

```text
_build_evidence_response(...)
```

which delegates to:

```text
ai_evidence_runtime.build_evidence_response(...)
```

The wrapper injects the existing stores:

```text
save_agent_tool_audit=_save_agent_tool_audit
save_pending_approval=_save_pending_approval
```

This avoids creating a second approval/audit ledger and preserves the existing approval workflow.

### 3. Reduced file size

Before:

```text
services/ai_agronomist/main.py = 1179 lines
```

After:

```text
services/ai_agronomist/main.py = 402 lines
services/ai_agronomist/ai_evidence_runtime.py = 822 lines
```

### 4. Added CI guard

Created:

```text
scripts/ci/ai_agronomist_main_decomposition_guard.py
tests_v9/test_ai_agronomist_main_decomposition_guard.py
.github/workflows/ai-agronomist-main-decomposition.yml
```

The guard enforces:

```text
main.py stays below 650 LOC
ai_evidence_runtime.py exists
heavy evidence/advisory helpers stay out of main.py
query/chat/explain/recommend routes remain present
main.py injects the existing audit and approval store callbacks
```

## Verification

### Service/runtime test subset

```text
33 passed, 1 skipped in 2.10s
```

### Guard test subset A

```text
5 passed in 15.28s
```

### Guard test subset B

```text
5 passed in 11.16s
```

### CI guards

Passed:

```text
pip mirror contract
dependency pin guard
dependency inventory
dependency conflict inventory
direct dependency bundle
service inventory
route mount inventory
api versioning policy
internal/graphql security
health alias contract
contract/capabilities schema
health/readiness schema
auth main decomposition
ai-agronomist main decomposition
test requirements inventory
edge model contract
edge production readiness
production honesty
```

## Current decomposition queue status

Done / materially reduced:

```text
P0: auth/main.py — decomposed MFA runtime; guard added
P0: ai_agronomist/main.py — decomposed evidence/advisory runtime; guard added
```

Remaining:

```text
P1: sahool-platform/api/main.py residual bootstrap
P1: odoo-bridge/main.py
P1: vegetation-analysis-service/main.py
P2: actuator-service/main.py
P2: sam2-inference/main.py
P2: weather-service/main.py before ensemble expansion
```

## Honest remaining limitations

- This is not a full domain-router extraction for ai-agronomist; it is a safe P0 decomposition that removes the heaviest evidence/advisory runtime from `main.py`.
- Full branch CI remains the final merge authority.
- Redis live integration and ONNX model provisioning remain operational follow-ups.
