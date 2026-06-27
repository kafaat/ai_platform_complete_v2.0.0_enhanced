# Ponytail / MCP / Streams / KG execution report

Implemented on v13:

## Added

1. `core/recommendation_ponytail.py`
   - Filters excessive recommendations before LLM/RAG calls.
   - Direct answer path for simple irrigation/status questions.
   - Hard lab gate for precise fertilization.
   - Human-review path for pesticide/PHI-sensitive decisions.
   - Explicitly cannot emit a recommendation.

2. `core/field_context_coordinator.py`
   - Renames agent role from decision-making orchestration to context coordination.
   - Normalizes tool/MCP outputs into `ContextSignal`.
   - RAG/KG are annotation-only.
   - Explicitly cannot emit recommendation or prescription.

3. `core/decision_firewall.py`
   - Allows only verified non-annotation signals into recommendation inputs.
   - Keeps RAG/KG as annotations.
   - Raises `InsufficientEvidenceError` for missing verified inputs.

4. `core/resumable_stream.py`
   - Adds resumable stream checkpoint primitive for long Daily Brief / Prescription generation.
   - Current implementation is in-memory; production should replace with Redis.

5. `core/kg_graphql_readonly.py`
   - Adds read-only GraphQL-like facade for agricultural KG exploration.
   - Every edge is `confidence=reference` and `prescriptive=false`.

6. `docs/architecture/decision_authority.md`
   - Decision Authority Matrix preventing RAG/KG/MCP bypass of Field State.

7. `docs/architecture/agentic_rag_mcp_streaming_plan.md`
   - Integration plan for MCP servers, Redis-backed streams, and UI artifacts.

## Tests

- `tests/test_ponytail_guardrails.py`
- `tests/test_context_firewall_and_streams.py`

Executed:

```bash
pytest -q tests/test_ponytail_guardrails.py tests/test_context_firewall_and_streams.py tests/test_guardrails.py tests/test_recommendation_engine.py
python verify_review_fixes.py
```

Result:

- Focused tests: 21/21 passed.
- Review verifier: 23/23 passed.

## Non-negotiable invariant preserved

`MCP / RAG / KG / Artifacts` produce context or annotations only.
The only decision path remains:

`Canonical Field State -> Recommendation Engine -> Human Review -> Prescription/Task`.
