# Stale Test Decomposition Compatibility Fix — 2026-07-09

## Context
A local agent run reported stale static tests after the P0 decomposition of:

- `services/auth/main.py` -> `services/auth/mfa_runtime.py`
- `services/ai_agronomist/main.py` -> `services/ai_agronomist/ai_evidence_runtime.py`

Some tests still scanned only `main.py`, so they would fail even though the runtime behavior had intentionally moved into the new modules.

## Changes Applied

### MFA anti-replay guard
Updated:

- `tests_v9/test_mfa_totp_antireplay_v141.py`

The static anti-replay checks now scan:

- `services/auth/main.py`
- `services/auth/mfa_runtime.py`
- `services/auth/routers/mfa.py`

This preserves the intended security assertion while respecting decomposition.

### Advisory contract guard
Updated:

- `tests_v9/test_advisory_contract_m2.py`

The advisory envelope wiring check now scans both:

- `services/ai_agronomist/main.py`
- `services/ai_agronomist/ai_evidence_runtime.py`

### AI tool-loop static guard
Updated:

- `tests_v9/test_ai_tool_loop_chat_integration_v57.py`

The chat/tool-loop wiring check now scans both the shell and runtime module.

### Provider-native tool calling guard
Updated:

- `tests_v9/test_ai_provider_native_tool_calling_v58.py`

The provider/manual tool-call merge check now scans both the shell and runtime module.

## Verification

Executed successfully:

```bash
pytest -q \
  tests_v9/test_advisory_contract_m2.py \
  tests_v9/test_ai_tool_loop_chat_integration_v57.py \
  tests_v9/test_ai_provider_native_tool_calling_v58.py
```

Result:

```text
15 passed in 1.48s
```

Executed successfully:

```bash
python -m py_compile \
  tests_v9/test_mfa_totp_antireplay_v141.py \
  tests_v9/test_advisory_contract_m2.py \
  tests_v9/test_ai_tool_loop_chat_integration_v57.py \
  tests_v9/test_ai_provider_native_tool_calling_v58.py
```

Additional guards:

```text
test_dependency_inventory_check_ok
production honesty guard passed
indicators_container_contract_guard_ok
```

## Honest Note
`tests_v9/test_mfa_totp_antireplay_v141.py` was syntax-checked but not executed in this container because the local interpreter does not currently have `pyotp` installed. The dependency is declared in `tests_v9/requirements-test.txt`; execution should be performed in the project test environment after installing test requirements.

## Decision
These were stale test-scope assumptions, not runtime regressions. The fixes preserve the original assertions across the decomposed module layout.
